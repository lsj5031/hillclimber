"""Workflow regressions using the existing disposable CLI fixture.

Run after bootstrap: python3 workflow_regressions.py
"""
import json
import subprocess
import unittest

import integration


class WorkflowRegressions(unittest.TestCase):
    setUp = integration.Integration.setUp
    git = integration.Integration.git
    cli = integration.Integration.cli
    crash = integration.Integration.crash
    init = integration.Integration.init
    begin = integration.Integration.begin

    def events(self):
        return [json.loads(line) for line in
                (self.repo / ".auto/events.jsonl").read_bytes().splitlines()]

    def assert_resolved_once(self, action):
        events = self.events()
        self.assertEqual([e["type"] for e in events if e["type"] in
                          ("intent", "applied", "resolved")],
                         ["intent", "applied", "resolved"])
        self.assertEqual([e["action"] for e in events if e["type"] == "resolved"],
                         [action])
        self.assertIsNone(self.cli("status")["candidate"])

    def aggregate_prefix(self, tail, retry=True):
        (self.repo / "bench.sh").write_text(
            "case $(ls .auto/runs | wc -l | tr -d ' ') in\n"
            "1) n=10;; 2) n=30;; 3) n=20;; *) n=5;; esac\n"
            "echo METRIC elapsed_ms=$n\n")
        self.git("add", "bench.sh")
        self.git("commit", "-qm", "Noisy benchmark fixture")
        self.init(budget=12 if retry else 4)
        self.cli("run", "--baseline")
        self.begin()
        self.assertEqual(self.cli("run", "--repeat", "3")["score"], 20)
        journal = self.repo / ".auto/events.jsonl"
        records = journal.read_bytes().splitlines(keepends=True)
        self.assertEqual(json.loads(records[-1])["type"], "aggregate")
        self.cli("decide", "keep", "--reason", "Median is worse", expected=3)
        journal.write_bytes(b"".join(records[:-1]) + records[-1][:tail])
        damaged = journal.read_bytes()
        head = self.git("rev-parse", "HEAD")
        self.cli("status")
        self.cli("recover")
        if tail:
            backups = list((self.repo / ".auto/recovery").glob("journal-*.jsonl"))
            self.assertEqual([p.read_bytes() for p in backups], [damaged])
        before = journal.read_bytes()
        self.cli("recover")
        self.assertEqual(journal.read_bytes(), before)
        self.assertEqual(self.cli("status")["executions"], 4)
        self.cli("decide", "keep", "--reason", "Raw sample must not count", expected=3)
        self.assertEqual(journal.read_bytes(), before)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        self.assertEqual(self.cli("status")["best"], 10)
        if not retry:
            self.assertEqual(self.cli("status")["remaining"], 0)
            self.cli("decide", "discard", "--reason", "Incomplete batch, no budget")
            self.cli("recover")
            self.cli("recover")
            self.assertEqual((self.repo / "src/value").read_text(), "slow\n")
            self.assertEqual(self.git("rev-parse", "HEAD"), head)
            self.assert_resolved_once("discard")
            self.cli("begin", "--hypothesis", "Fresh candidate after incomplete batch")
            (self.repo / "src/value").write_text("fast\n")
            self.cli("decide", "keep", "--reason", "No fresh evidence", expected=3)
            self.cli("decide", "discard", "--reason", "No budget remains")
            return
        self.cli("run")
        self.cli("decide", "keep", "--reason", "Completed replacement batch")
        self.assertEqual(self.cli("status")["best"], 5)
        self.cli("recover")
        self.assert_resolved_once("keep")
        self.cli("begin", "--hypothesis", "Fresh candidate has no evidence")
        (self.repo / "src/value").write_text("other\n")
        self.cli("decide", "keep", "--reason", "Do not reuse old aggregate", expected=3)
        self.cli("decide", "discard", "--reason", "Unmeasured fresh candidate")
        self.assertEqual((self.repo / "src/value").read_text(), "fast\n")

    def test_workflow_preaggregate_prefix_cannot_keep_raw_sample(self):
        self.aggregate_prefix(0)

    def test_workflow_torn_aggregate_cannot_keep_raw_sample(self):
        self.aggregate_prefix(40)

    def test_workflow_incomplete_aggregate_discard_at_exhausted_budget(self):
        self.aggregate_prefix(40, retry=False)

    def test_workflow_new_interrupted_batch_invalidates_old_aggregate(self):
        self.init()
        self.cli("run", "--baseline")
        self.begin()
        self.cli("run")
        self.crash("after-run-start", "run")
        self.cli("recover")
        self.cli("recover")
        self.cli("decide", "keep", "--reason", "Old aggregate is stale", expected=3)
        self.assertEqual(self.cli("status")["executions"], 3)
        self.cli("run")
        self.cli("decide", "keep", "--reason", "Fresh completed batch")
        self.assertEqual(self.cli("status")["best"], 5)

    def test_workflow_keep_requires_pending_candidate_identity(self):
        self.init()
        self.cli("run", "--baseline")
        self.begin()
        self.cli("run")
        journal = self.repo / ".auto/events.jsonl"
        events = self.events()
        events[-1]["candidate"] = "c-999999"
        journal.write_text("".join(json.dumps(e) + "\n" for e in events))
        before = journal.read_bytes()
        result = subprocess.run(
            [str(integration.BIN), "--project", str(self.repo), "decide", "keep",
             "--reason", "Wrong candidate", "--json"],
            cwd=self.repo, text=True, capture_output=True)
        # The workflow guard or stricter journal ingress must reject this.
        self.assertIn(result.returncode, (3, 5), (result.stdout, result.stderr))
        self.assertEqual(result.stderr, "")
        self.assertEqual(json.loads(result.stdout)["kind"], "error")
        self.assertEqual(journal.read_bytes(), before)

    def test_workflow_completed_aggregate_does_not_bypass_evaluator_or_head(self):
        self.init()
        self.cli("run", "--baseline")
        self.begin()
        self.cli("run")
        journal = self.repo / ".auto/events.jsonl"
        before = journal.read_bytes()
        evaluator = self.repo / ".auto/measure.sh"
        original = evaluator.read_bytes()
        evaluator.write_bytes(b"echo METRIC elapsed_ms=1\n")
        self.assertEqual(self.cli("decide", "keep", "--reason", "Changed evaluator",
                                  expected=3)["code"], "evaluator-drift")
        self.assertEqual(journal.read_bytes(), before)
        evaluator.write_bytes(original)
        self.git("commit", "--allow-empty", "-qm", "External HEAD drift")
        self.assertEqual(self.cli("decide", "keep", "--reason", "Changed HEAD",
                                  expected=3)["code"], "head-drift")
        self.assertEqual(journal.read_bytes(), before)
        self.assertEqual((self.repo / "src/value").read_text(), "fast\n")

    def deletion_candidate(self, measured):
        (self.repo / "src/remove").write_bytes(b"restore me\n")
        self.git("add", "src/remove")
        self.git("commit", "-qm", "Tracked deletion fixture")
        self.init()
        self.cli("run", "--baseline")
        self.begin()
        (self.repo / "src/remove").unlink()
        (self.repo / "src/new").write_bytes(b"save new bytes\n")
        if measured:
            self.cli("run")

    def check_discarded_deletion(self):
        self.cli("recover")
        self.cli("recover")
        self.assertEqual((self.repo / "src/remove").read_bytes(), b"restore me\n")
        self.assertEqual((self.repo / "src/value").read_text(), "slow\n")
        self.assertFalse((self.repo / "src/new").exists())
        self.assertEqual((self.repo / ".auto/recovery/c-000001/src/new").read_bytes(),
                         b"save new bytes\n")
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assert_resolved_once("discard")
        self.cli("begin", "--hypothesis", "Fresh candidate after restored deletion")
        self.cli("decide", "discard", "--reason", "No changes")

    def test_workflow_deleted_tracked_discard_without_measurement(self):
        self.deletion_candidate(False)
        self.cli("decide", "discard", "--reason", "Restore deleted tracked file")
        self.check_discarded_deletion()

    def test_workflow_deleted_tracked_discard_after_measurement(self):
        self.deletion_candidate(True)
        self.cli("decide", "discard", "--reason", "Restore measured deletion")
        self.check_discarded_deletion()

    def test_workflow_deleted_tracked_recover_after_intent(self):
        self.deletion_candidate(True)
        self.crash("after-intent", "decide", "discard", "--reason", "Crash before restore")
        self.check_discarded_deletion()

    def test_workflow_deleted_tracked_recover_after_files(self):
        self.deletion_candidate(True)
        self.crash("after-files", "decide", "discard", "--reason", "Crash after restore")
        self.check_discarded_deletion()

    def test_workflow_deleted_tracked_recover_after_applied(self):
        self.deletion_candidate(True)
        self.crash("after-applied", "decide", "discard", "--reason", "Crash before resolve")
        self.check_discarded_deletion()

    def test_workflow_deleted_tracked_recovery_preserves_new_edits(self):
        self.deletion_candidate(True)
        self.crash("after-intent", "decide", "discard", "--reason", "Crash fixture")
        deleted = self.repo / "src/remove"
        deleted.write_bytes(b"new user edit\n")
        journal = self.repo / ".auto/events.jsonl"
        before = journal.read_bytes()
        self.assertEqual(self.cli("recover", expected=3)["code"], "source-drift")
        self.assertEqual(deleted.read_bytes(), b"new user edit\n")
        self.assertEqual(journal.read_bytes(), before)
        deleted.unlink()
        self.check_discarded_deletion()

    def test_workflow_deleted_tracked_keep_still_commits_exact_paths(self):
        self.deletion_candidate(True)
        self.cli("decide", "keep", "--reason", "Deletion is a measured improvement")
        self.cli("recover")
        self.assertFalse((self.repo / "src/remove").exists())
        self.assertEqual(self.git("diff", "--name-only", "HEAD^", "HEAD").splitlines(),
                         ["src/new", "src/remove", "src/value"])
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assert_resolved_once("keep")

    def test_workflow_detached_init_is_write_free_and_retryable(self):
        branch = self.git("symbolic-ref", "--short", "HEAD")
        exclude = self.repo / self.git("rev-parse", "--git-path", "info/exclude")
        before = exclude.read_bytes()
        head = self.git("rev-parse", "HEAD")
        self.git("checkout", "--detach")
        self.assertEqual(self.init_detached_error()["code"], "detached-head")
        self.assertFalse((self.repo / ".auto").exists())
        self.assertEqual(exclude.read_bytes(), before)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.git("checkout", branch)
        self.init()
        self.cli("run", "--baseline")

    def init_detached_error(self):
        return self.cli("init", "--name", "Demo", "--metric", "elapsed_ms",
                        "--direction", "lower", "--scope", "src", "--max-runs", "12",
                        "--benchmark", "bench.sh", "--check", "checks.sh", expected=3)


if __name__ == "__main__":
    unittest.main()
