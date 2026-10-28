"""F4 review regressions. Run: python3 -m unittest -v journal_regressions.JournalRegressions"""
import copy
import json
import os
import subprocess
import unittest

import integration


class JournalRegressions(unittest.TestCase):
    git = integration.Integration.git
    begin = integration.Integration.begin

    def setUp(self):
        integration.Integration.setUp(self)
        self.commands = []
        self.addCleanup(self.save_evidence)

    def save_evidence(self):
        prefix = os.environ.get("JOURNAL_EVIDENCE_PREFIX", "journal")
        (integration.SCRATCH / f"{prefix}-{self._testMethodName}.json").write_text(
            json.dumps(self.commands, indent=2) + "\n")

    def cli(self, *args, expected=0):
        argv = [str(integration.BIN), "--project", str(self.repo), *args, "--json"]
        result = subprocess.run(argv, cwd=self.repo, text=True, capture_output=True,
                                timeout=10)
        self.commands.append(dict(argv=argv, cwd=str(self.repo),
                                  exit=result.returncode, stdout=result.stdout,
                                  stderr=result.stderr))
        self.assertEqual(result.returncode, expected, (result.stdout, result.stderr))
        self.assertEqual(result.stderr, "")
        response = json.loads(result.stdout)
        self.assertEqual(response["kind"], "error" if expected else "result")
        return response["data"]

    def init(self, *extra):
        return self.cli("init", "--name", "Journal", "--metric", "elapsed_ms",
                        "--direction", "lower", "--scope", "src", "--max-runs", "20",
                        "--benchmark", "bench.sh", "--check", "checks.sh", *extra)

    def records(self):
        return [json.loads(line) for line in
                (self.repo / ".auto/events.jsonl").read_bytes().splitlines()]

    def protected_duplicates(self, *extra):
        self.init(*extra)
        self.cli("run", "--baseline")
        self.cli("begin", "--hypothesis", "Protected duplicates")
        protected = self.records()[-1]["protected"]
        self.assertLess(len({e["path"] for e in protected}), len(protected))
        journal = self.repo / ".auto/events.jsonl"
        before = journal.read_bytes()
        self.assertEqual(self.cli("status")["best"], 10)
        self.cli("recover")
        self.assertEqual(journal.read_bytes(), before)
        (self.repo / "src/value").write_text("fast\n")
        self.assertEqual(self.cli("run")["score"], 5)
        self.cli("decide", "discard", "--reason", "Valid duplicate protected paths")
        self.cli("recover")
        self.assertIsNone(self.cli("status")["candidate"])
        self.assertEqual((self.repo / "src/value").read_text(), "slow\n")
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_journal_overlapping_benchmark_input(self):
        self.protected_duplicates("--input", "bench.sh")

    def test_journal_repeated_check_input(self):
        self.protected_duplicates("--input", "checks.sh", "--input", "checks.sh")

    def assert_corrupt(self, records):
        journal = self.repo / ".auto/events.jsonl"
        head = self.git("rev-parse", "HEAD")
        backups = list((self.repo / ".auto/recovery").glob("journal-*"))
        for tail in (b"", b'{"v":1,"type":'):
            with self.subTest(tail=bool(tail)):
                before = b"".join(json.dumps(e).encode() + b"\n" for e in records) + tail
                journal.write_bytes(before)
                for command in (("status",), ("recover",), ("run",),
                                ("decide", "keep", "--reason", "Must not accept"),
                                ("decide", "discard", "--reason", "Must not mutate")):
                    self.assertEqual(self.cli(*command, expected=5)["code"],
                                     "journal-corrupt")
                    self.assertEqual(journal.read_bytes(), before)
                    self.assertEqual(self.git("rev-parse", "HEAD"), head)
                self.assertEqual(list((self.repo / ".auto/recovery").glob("journal-*")),
                                 backups)

    def test_journal_conflicting_protected_duplicates_and_duplicate_source(self):
        self.init()
        self.cli("run", "--baseline")
        self.begin()
        self.cli("run")
        records = self.records()
        for key, value in (("hash", "f" * 40), ("mode", "executable")):
            with self.subTest(conflict=key):
                changed = copy.deepcopy(records)
                begin = next(e for e in changed if e["type"] == "begin")
                duplicate = dict(begin["protected"][-1])
                duplicate[key] = value
                begin["protected"].append(duplicate)
                self.assert_corrupt(changed)
        changed = copy.deepcopy(records)
        attempt = next(e for e in changed if e["type"] == "attempt" and e["source"])
        attempt["source"].append(dict(attempt["source"][0]))
        self.assert_corrupt(changed)

    def noisy_candidate(self):
        (self.repo / "bench.sh").write_text(
            "case $(ls .auto/runs | wc -l | tr -d ' ') in\n"
            "1) n=10;; 2) n=30;; 3) n=20;; *) n=5;; esac\n"
            "echo METRIC elapsed_ms=$n\n"
            "echo METRIC aux=$n\n"
            "test \"$n\" = 20 || echo METRIC intermittent=7\n"
            "test \"$n\" = 30 || echo METRIC occasional=9\n")
        self.git("add", "bench.sh")
        self.git("commit", "-qm", "Scored journal fixture")
        self.init()
        self.cli("run", "--baseline")
        self.begin()
        self.assertEqual(self.cli("run", "--repeat", "3")["score"], 20)
        self.assertEqual(self.cli("decide", "keep", "--reason", "Real regression",
                                  expected=3)["code"], "not-improved")

    def test_journal_one_field_aggregate_score_cannot_authorize_regression(self):
        self.noisy_candidate()
        records = self.records()
        self.assertEqual(records[-1]["samples"], [30, 20, 5])
        records[-1]["score"] = 5
        self.assert_corrupt(records)

    def test_journal_derived_baseline_and_aggregate_fields(self):
        self.noisy_candidate()
        original = self.records()
        for kind in ("baseline", "aggregate"):
            for field in ("score", "mad", "primary", "secondary", "missing_metric",
                          "extra_metric", "missing", "extra_missing"):
                with self.subTest(kind=kind, field=field):
                    records = copy.deepcopy(original)
                    event = next(e for e in records if e["type"] == kind)
                    if field in ("score", "mad"):
                        event[field] += 1
                    elif field in ("primary", "secondary"):
                        event["metrics"]["elapsed_ms" if field == "primary" else "aux"] += 1
                    elif field == "missing_metric":
                        del event["metrics"]["aux"]
                    elif field == "extra_metric":
                        event["metrics"]["invented"] = 1
                    elif field == "missing":
                        event["secondary_missing"] = []
                        if kind == "baseline":
                            event["secondary_missing"] = ["aux"]
                    else:
                        event["secondary_missing"].append("invented")
                    self.assert_corrupt(records)

    def test_journal_raw_primary_score_matches_selected_metric(self):
        self.noisy_candidate()
        original = self.records()
        for which in ("baseline", "candidate"):
            for field in ("score", "primary", "absent_primary"):
                with self.subTest(which=which, field=field):
                    records = copy.deepcopy(original)
                    index = next(i for i, e in enumerate(records)
                                 if e["type"] == "attempt" and
                                 (e["candidate"] is None) == (which == "baseline"))
                    event = records[index]
                    if field == "score":
                        event["score"] += 1
                    elif field == "primary":
                        event["metrics"]["elapsed_ms"] += 1
                    else:
                        del event["metrics"]["elapsed_ms"]
                    # Even a durable raw-attempt prefix must reject scalar drift.
                    self.assert_corrupt(records[:index + 1])

    def test_journal_metric_object_order_is_not_evidence(self):
        self.noisy_candidate()
        records = self.records()
        for event in records:
            if "metrics" in event:
                event["metrics"] = dict(reversed(list(event["metrics"].items())))
            if "secondary_missing" in event:
                event["secondary_missing"].reverse()
        journal = self.repo / ".auto/events.jsonl"
        journal.write_text("".join(json.dumps(e) + "\n" for e in records))
        before = journal.read_bytes()
        self.assertEqual(self.cli("status")["last_attempt"]["score"], 20)
        self.cli("recover")
        self.assertEqual(journal.read_bytes(), before)
        self.cli("decide", "discard", "--reason", "JSON object ordering is irrelevant")

    def test_journal_legacy_v1_rounded_mad_remains_readable(self):
        samples = [-9.582186852612564, -9.778937170569266,
                   8.260920199751453, 9.968944594601425]
        cases = "\n".join(f"{i}) n={value};;"
                          for i, value in enumerate(samples, 1))
        (self.repo / "bench.sh").write_text(
            "i=$(ls .auto/runs | wc -l | tr -d ' ')\n"
            "case $(( (i - 1) % 4 + 1 )) in\n" + cases +
            "\nesac\necho METRIC elapsed_ms=$n\necho METRIC aux=$n\n")
        self.git("add", "bench.sh")
        self.git("commit", "-qm", "Legacy v1 MAD rounding control")
        self.init()
        self.assertEqual(self.cli("run", "--baseline", "--repeat", "4")["mad"],
                         9.019928685160359)
        self.begin()
        self.cli("run", "--repeat", "4")
        records = self.records()
        for event in records:
            if event["type"] in ("baseline", "aggregate"):
                event["mad"] = 9.01992868516036  # Actual pre-F8 double-distance result.
        journal = self.repo / ".auto/events.jsonl"
        journal.write_text("".join(json.dumps(e) + "\n" for e in records))
        before = journal.read_bytes()
        status = self.cli("status")
        self.assertEqual(status["baseline"]["mad"], 9.01992868516036)
        self.assertEqual(status["last_attempt"]["mad"], 9.01992868516036)
        self.cli("recover")
        self.assertEqual(journal.read_bytes(), before)
        self.cli("decide", "discard", "--reason", "Legacy arithmetic is valid v1")

    def test_journal_session_metric_selects_raw_primary(self):
        (self.repo / "bench.sh").write_text(
            "echo METRIC latency=0\necho METRIC elapsed_ms=123\n")
        self.git("add", "bench.sh")
        self.git("commit", "-qm", "Nondefault zero primary metric")
        self.cli("init", "--name", "Other metric", "--metric", "latency",
                 "--direction", "higher", "--scope", "src", "--max-runs", "12",
                 "--benchmark", "bench.sh", "--check", "checks.sh")
        self.assertEqual(self.cli("run", "--baseline")["score"], 0)
        self.begin()
        self.cli("run")
        self.assertEqual(self.cli("status")["last_attempt"]["score"], 0)
        self.cli("decide", "discard", "--reason", "Zero selected metric is valid")


if __name__ == "__main__":
    unittest.main()
