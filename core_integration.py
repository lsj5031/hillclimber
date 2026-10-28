"""Core resource/replay regressions. Run: python3 core_integration.py."""
import copy
import json
import subprocess
import unittest

from integration import BIN, Integration


class CoreIntegration(Integration):
    def test_core_low_descriptor_candidate(self):
        self.init()
        self.cli("run", "--baseline")
        self.begin()
        for i in range(100):
            (self.repo / "src" / f"new-{i:03}").write_text("fixture\n")
        result = subprocess.run(
            ["/bin/sh", "-c", 'ulimit -n 128; exec "$@"', "core-limit",
             str(BIN), "--project", str(self.repo), "run", "--json"],
            cwd=self.repo, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertEqual(json.loads(result.stdout)["data"]["score"], 5)
        self.assertEqual(self.cli("status")["executions"], 2)

    def test_core_semantic_corruption_preserves_evidence(self):
        self.init()
        self.cli("run", "--baseline")
        journal = self.repo / ".auto/events.jsonl"
        original = journal.read_bytes()
        invalid = {"v": 1, "type": "resolved", "action": "keep",
                   "head": "invalid", "score": 0}
        journal.write_bytes(original + json.dumps(invalid).encode() + b"\n")
        before = journal.read_bytes()
        for command in (("status",), ("recover",), ("begin", "--hypothesis", "blocked")):
            self.assertEqual(self.cli(*command, expected=5)["code"], "journal-corrupt")
            self.assertEqual(journal.read_bytes(), before)

    def test_core_shapes_and_transitions(self):
        self.init()
        self.cli("run", "--baseline", "--repeat", "3")
        self.begin()
        self.cli("run", "--repeat", "2")
        self.cli("decide", "keep", "--reason", "passing")
        self.cli("begin", "--hypothesis", "discard")
        (self.repo / "src/value").write_text("slow\n")
        self.cli("run")
        self.cli("decide", "discard", "--reason", "regression")
        journal = self.repo / ".auto/events.jsonl"
        events = [json.loads(line) for line in journal.read_text().splitlines()]
        indices = {e["type"]: i for i, e in reversed(list(enumerate(events)))}
        cases = {}
        required = {"baseline": "samples", "begin": "scope",
                    "attempt-start": "candidate", "attempt": "score",
                    "aggregate": "source", "intent": "reason",
                    "applied": "decision", "resolved": "head"}
        for kind, key in required.items():
            changed = copy.deepcopy(events)
            del changed[indices[kind]][key]
            cases[f"missing {kind}.{key}"] = changed
        wrong = [("baseline", "score", "0"), ("baseline", "count", 1),
                 ("baseline", "mad", -1), ("baseline", "samples", []),
                 ("begin", "scope", "src"), ("begin", "id", "c-000999"),
                 ("attempt-start", "candidate", "c-000999"),
                 ("attempt", "id", "r-000999"), ("attempt", "score", True),
                 ("aggregate", "id", "r-000999"),
                 ("aggregate", "candidate", "c-000999"),
                 ("aggregate", "samples", [123]),
                 ("intent", "decision", "d-000999"),
                 ("applied", "head", "invalid"),
                 ("resolved", "id", "c-000999"),
                 ("resolved", "decision", "d-000999"),
                 ("resolved", "action", "discard"),
                 ("resolved", "head", "f" * 40),
                 ("resolved", "score", 0)]
        for kind, key, value in wrong:
            changed = copy.deepcopy(events)
            changed[indices[kind]][key] = value
            cases[f"wrong {kind}.{key}"] = changed
        for kind in ("baseline", "begin", "attempt", "aggregate", "applied", "resolved"):
            i = indices[kind]
            cases[f"duplicate {kind}"] = events[:i + 1] + [events[i]] + events[i + 1:]
        baseline_end = indices["baseline"] + 1
        for kind in ("applied", "resolved", "aggregate"):
            cases[f"unpaired {kind}"] = events[:baseline_end] + [events[indices[kind]]]
        for kind, key, value in (("attempt", "hash", "invalid"),
                                 ("aggregate", "path", "../escape"),
                                 ("intent", "path", "outside"),
                                 ("intent", "mode", "directory")):
            changed = copy.deepcopy(events)
            i = next(i for i, e in enumerate(events)
                     if e["type"] == kind and e.get("source"))
            changed[i]["source"][0][key] = value
            cases[f"source {kind}.{key}"] = changed
        changed = copy.deepcopy(events)
        discard = next(e for e in changed if e["type"] == "intent" and e["action"] == "discard")
        discard["source"][0]["hash"] = "f" * 40
        cases["discard source differs from measurement"] = changed
        changed = copy.deepcopy(events)
        sample = next(e for e in changed if e["type"] == "attempt" and e.get("source"))
        sample["benchmark"]["exit"] = 1
        cases["passing score with failed benchmark"] = changed
        changed = copy.deepcopy(events)
        sample = next(e for e in changed if e["type"] == "attempt" and e.get("source"))
        sample["benchmark"]["stdout"]["saved"] = -1
        cases["invalid captured output evidence"] = changed
        i = indices["intent"]
        cases["resolution before applied"] = events[:i + 1] + [events[indices["resolved"]]]
        cases["cancel without intent"] = events[:baseline_end] + [
            {"v": 1, "type": "cancel-intent", "id": "c-000001", "at": 0}]
        backups = list((self.repo / ".auto/recovery").glob("journal-*"))
        for name, records in cases.items():
            for tail in (b"", b'{"v":1,"type":'):
                with self.subTest(case=name, tail=bool(tail)):
                    before = b"".join(json.dumps(e).encode() + b"\n" for e in records) + tail
                    journal.write_bytes(before)
                    for command in (("status",), ("recover",),
                                    ("begin", "--hypothesis", "blocked")):
                        self.assertEqual(self.cli(*command, expected=5)["code"], "journal-corrupt")
                        self.assertEqual(journal.read_bytes(), before)
                    self.assertEqual(list((self.repo / ".auto/recovery").glob("journal-*")), backups)

    def test_core_interrupted_prefixes_and_retry(self):
        self.init()
        # Retrying before recover legitimately supersedes a reservation.
        self.crash("after-run-start", "run", "--baseline")
        self.cli("run", "--baseline")
        self.begin()
        self.crash("after-run-start", "run")
        self.cli("recover")
        self.cli("recover")
        self.cli("run")
        self.cli("decide", "discard", "--reason", "exercise recovery")
        self.assertEqual(self.cli("status")["executions"], 4)
        journal = self.repo / ".auto/events.jsonl"
        original = journal.read_bytes()
        records = original.splitlines(keepends=True)
        # Every durable writer boundary remains readable. This is a status
        # replay check only, not a claim to reproduce a power failure.
        for n in range(len(records) + 1):
            with self.subTest(prefix=n):
                journal.write_bytes(b"".join(records[:n]))
                self.cli("status")
        journal.write_bytes(original)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        CoreIntegration(name) for name in loader.getTestCaseNames(CoreIntegration)
        if name.startswith("test_core_"))


if __name__ == "__main__":
    unittest.main()
