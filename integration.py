"""Disposable-repository acceptance tests. Run: python3 integration.py"""
import json
import os
import pathlib
import re
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
BIN = ROOT / "build/hillclimber"
SCRATCH = ROOT / "scratch"


class Integration(unittest.TestCase):
    def setUp(self):
        SCRATCH.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="integration-", dir=SCRATCH)
        self.addCleanup(self.temp.cleanup)
        self.repo = pathlib.Path(self.temp.name) / "repo"
        self.repo.mkdir()
        (self.repo / "src").mkdir()
        (self.repo / "src/value").write_text("slow\n")
        (self.repo / "bench.sh").write_text(
            "#!/bin/sh\n"
            "if grep -q fast src/value; then echo METRIC elapsed_ms=5; "
            "else echo METRIC elapsed_ms=10; fi\n"
        )
        (self.repo / "checks.sh").write_text("#!/bin/sh\ntest -s src/value\n")
        self.git("init", "-q")
        self.git("add", ".")
        self.git("commit", "-qm", "Set up experiment")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, check=True,
                              text=True, capture_output=True).stdout.strip()

    def cli(self, *args, expected=0, cwd=None):
        result = subprocess.run([str(BIN), "--project", str(self.repo), *args, "--json"],
                                cwd=cwd or self.repo, text=True, capture_output=True)
        self.assertEqual(result.returncode, expected, (result.stdout, result.stderr))
        self.assertEqual(result.stderr, "")
        value = json.loads(result.stdout)
        self.assertEqual(value["v"], 1)
        self.assertEqual(value["kind"], "error" if expected else "result")
        return value["data"]

    def crash(self, point, *args):
        env = os.environ.copy()
        env["HILLCLIMBER_TEST_CRASH"] = point
        result = subprocess.run([str(BIN), "--project", str(self.repo),
                                 *args, "--json"], cwd=self.repo,
                                env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 86, (result.stdout, result.stderr))

    def init(self, budget=12):
        return self.cli("init", "--name", "Demo", "--metric", "elapsed_ms",
                        "--direction", "lower", "--unit", "ms", "--scope", "src",
                        "--max-runs", str(budget), "--benchmark", "bench.sh",
                        "--check", "checks.sh")

    def begin(self):
        self.cli("begin", "--hypothesis", "Try fast")
        (self.repo / "src/value").write_text("fast\n")

    def test_quickstart_keep_discard_restart_and_new_file(self):
        self.init()
        self.cli("run", "--baseline", "--repeat", "3")
        self.begin()
        self.cli("run", "--repeat", "3")
        self.cli("decide", "keep", "--reason", "Lower median")
        self.assertEqual(self.git("log", "-1", "--format=%s"),
                         "hillclimber candidate c-000001: Lower median")
        self.cli("begin", "--hypothesis", "Try slow")
        (self.repo / "src/value").write_text("slow\n")
        (self.repo / "src/new file").write_bytes(b"preserved\n")
        self.cli("run")
        self.cli("decide", "discard", "--reason", "Regression")
        self.assertEqual((self.repo / "src/value").read_text(), "fast\n")
        self.assertEqual((self.repo / ".auto/recovery/c-000002/src/new file").read_bytes(), b"preserved\n")
        self.assertFalse((self.repo / "src/new file").exists())
        s = self.cli("status", "--context", "--history", "3", cwd=ROOT)
        self.assertEqual((s["best"], s["executions"], s["remaining"]), (5.0, 7, 5))
        self.assertEqual(s["candidate"], None)
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.cli("recover")

    def test_failures_budget_and_parser(self):
        (self.repo / "bench.sh").write_text("#!/bin/sh\necho METRIC elapsed_ms=NaN\n")
        self.git("add", "bench.sh")
        self.git("commit", "-qm", "Invalid benchmark")
        self.init(budget=2)
        self.cli("run", "--baseline", expected=4)
        s = self.cli("status")
        self.assertIsNone(s["last_attempt"]["score"])
        self.assertEqual(s["executions"], 1)
        self.cli("run", "--baseline", expected=4)
        self.cli("run", "--baseline", expected=3)
        self.assertEqual(self.cli("status")["remaining"], 0)

    def test_failed_checks_source_drift_protected_drift_and_scope(self):
        self.init()
        self.cli("run", "--baseline")
        self.begin()
        self.cli("run")
        (self.repo / "src/value").write_text("slow\n")
        self.cli("decide", "keep", "--reason", "Changed after measurement", expected=3)
        (self.repo / "src/value").write_text("fast\n")
        (self.repo / "checks.sh").write_text("exit 1\n")
        self.cli("run", expected=3)
        (self.repo / "checks.sh").write_text("#!/bin/sh\ntest -s src/value\n")
        (self.repo / "outside").write_text("foreign")
        self.cli("run", expected=3)
        (self.repo / "outside").unlink()
        (self.repo / "src/value").write_text("")
        self.cli("run", expected=4)
        self.assertIsNone(self.cli("status")["last_attempt"]["score"])
        self.cli("decide", "discard", "--reason", "Checks failed")

    def test_git_hook_failure_and_retry(self):
        self.init()
        self.cli("run", "--baseline")
        self.begin()
        self.cli("run")
        hook = self.repo / ".git/hooks/pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        self.cli("decide", "keep", "--reason", "Hook should run", expected=5)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")
        self.assertEqual(self.cli("status")["candidate"]["id"], "c-000001")
        hook.unlink()
        self.cli("decide", "keep", "--reason", "Hook passed")
        self.assertEqual(self.cli("status")["best"], 5.0)
        events = [json.loads(line) for line in
                  (self.repo / ".auto/events.jsonl").read_text().splitlines()]
        self.assertEqual([event["decision"] for event in events
                          if event["type"] == "intent"], ["d-000001", "d-000002"])

    def test_journal_corruption_preserved(self):
        self.init()
        journal = self.repo / ".auto/events.jsonl"
        journal.write_bytes(b'{"v":1,"type":"begin"\n')
        before = journal.read_bytes()
        self.cli("status", expected=5)
        self.cli("run", "--baseline", expected=5)
        self.cli("recover", expected=5)
        self.assertEqual(journal.read_bytes(), before)

    def test_truncated_journal_repair_preserves_original_bytes(self):
        self.init()
        self.cli("run", "--baseline")
        journal = self.repo / ".auto/events.jsonl"
        with journal.open("ab") as f:
            f.write(b'{"v":1,"type":"beg')
        before = journal.read_bytes()
        s = self.cli("status")
        self.assertEqual(s["next"], "recover")
        self.cli("begin", "--hypothesis", "Blocked until repair", expected=5)
        self.cli("recover")
        backups = list((self.repo / ".auto/recovery").glob("journal-*.jsonl"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), before)
        self.assertTrue(journal.read_bytes().endswith(b"\n"))
        self.cli("begin", "--hypothesis", "Now repaired")

    def test_timeout_descendant_lock_and_recovery(self):
        (self.repo / "bench.sh").write_text(
            "#!/bin/sh\nsleep 60 &\necho $! > child.pid\nwait\n"
        )
        self.git("add", "bench.sh")
        self.git("commit", "-qm", "Long benchmark")
        self.init(budget=2)
        p = subprocess.Popen([str(BIN), "--project", str(self.repo),
                              "run", "--baseline", "--timeout", "1", "--json"],
                             cwd=self.repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True)
        try:
            for _ in range(100):
                if (self.repo / "child.pid").exists():
                    break
                time.sleep(.02)
            self.assertTrue((self.repo / "child.pid").exists())
            self.assertEqual(self.cli("run", "--baseline", expected=3)["code"], "locked")
            out, err = p.communicate(timeout=10)
            self.assertEqual(p.returncode, 4, (out, err))
            pid = int((self.repo / "child.pid").read_text())
            time.sleep(.1)
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)
            self.assertEqual(self.cli("status")["executions"], 1)
        finally:
            if p.poll() is None:
                p.kill()
                p.wait()
            if p.stdout:
                p.stdout.close()
            if p.stderr:
                p.stderr.close()

    def test_crashed_attempt_consumes_budget_and_recover(self):
        self.init(budget=3)
        self.crash("after-run-start", "run", "--baseline")
        self.assertEqual(self.cli("status")["next"], "recover")
        self.cli("recover")
        self.assertIsNone(self.cli("status")["last_attempt"]["score"])
        self.assertEqual(self.cli("status")["executions"], 1)
        self.cli("run", "--baseline")
        self.assertEqual(self.cli("status")["remaining"], 1)

    def _check_crash_keep(self, point):
        self.init()
        self.cli("run", "--baseline")
        self.begin()
        self.cli("run")
        self.crash(point, "decide", "keep", "--reason", "Crash fixture")
        self.assertEqual(self.cli("status")["next"], "recover")
        self.cli("recover")
        self.assertEqual(self.cli("status")["best"], 5.0)
        self.assertIsNone(self.cli("status")["candidate"])
        self.cli("recover")
        self.assertEqual(len(self.git("log", "--format=%s").splitlines()), 2)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_keep_crash_after_intent(self):
        self._check_crash_keep("after-intent")

    def test_keep_crash_after_git_commit(self):
        self._check_crash_keep("after-git")

    def test_keep_crash_after_applied(self):
        self._check_crash_keep("after-applied")

    def test_discard_crash_during_file_move(self):
        self.init()
        self.cli("run", "--baseline")
        self.begin()
        (self.repo / "src/new µ file").write_bytes(b"disposable bytes\n")
        self.cli("run")
        self.crash("after-discard-move", "decide", "discard", "--reason", "Crash fixture")
        self.cli("recover")
        self.cli("recover")
        self.assertFalse((self.repo / "src/new µ file").exists())
        self.assertEqual((self.repo / ".auto/recovery/c-000001/src/new µ file").read_bytes(),
                         b"disposable bytes\n")
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_recover_refuses_new_edits_after_discard_intent(self):
        self.init()
        self.cli("run", "--baseline")
        self.begin()
        self.cli("run")
        self.crash("after-intent", "decide", "discard", "--reason", "Crash fixture")
        (self.repo / "src/value").write_text("third edit\n")
        self.assertEqual(self.cli("recover", expected=3)["code"], "source-drift")
        self.assertEqual((self.repo / "src/value").read_text(), "third edit\n")

    def test_recover_keeps_foreign_staged_content(self):
        self.init()
        self.cli("run", "--baseline")
        self.begin()
        self.cli("run")
        self.crash("after-intent", "decide", "keep", "--reason", "Crash fixture")
        (self.repo / "src/value").write_text("foreign staged\n")
        self.git("add", "src/value")
        (self.repo / "src/value").write_text("fast\n")
        self.assertEqual(self.cli("recover", expected=5)["code"], "foreign-index")
        self.assertEqual(self.git("show", ":src/value"), "foreign staged")
        self.git("restore", "--staged", "--", "src/value")
        self.cli("recover")
        self.assertEqual(self.cli("status")["best"], 5.0)

    def test_discard_recovery_rejects_staged_change(self):
        self.init()
        self.cli("run", "--baseline")
        self.begin()
        self.cli("run")
        self.crash("after-intent", "decide", "discard", "--reason", "Crash fixture")
        self.git("add", "src/value")
        self.assertEqual(self.cli("recover", expected=5)["code"], "foreign-index")
        self.git("restore", "--staged", "--", "src/value")
        self.cli("recover")
        self.assertEqual((self.repo / "src/value").read_text(), "slow\n")

    def test_interrupt_reaps_descendant_and_recovers(self):
        (self.repo / "bench.sh").write_text(
            "#!/bin/sh\nsleep 60 &\necho $! > child.pid\nwait\n"
        )
        self.git("add", "bench.sh")
        self.git("commit", "-qm", "Interrupt fixture")
        self.init()
        p = subprocess.Popen([str(BIN), "--project", str(self.repo), "run", "--baseline",
                              "--json"], cwd=self.repo, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        try:
            for _ in range(100):
                if (self.repo / "child.pid").exists():
                    break
                time.sleep(.02)
            self.assertTrue((self.repo / "child.pid").exists())
            child = int((self.repo / "child.pid").read_text())
            os.kill(p.pid, signal.SIGINT)
            out, err = p.communicate(timeout=8)
            self.assertEqual(p.returncode, 130, (out, err))
            with self.assertRaises(ProcessLookupError):
                os.kill(child, 0)
            self.cli("recover")
            self.assertEqual(self.cli("status")["executions"], 1)
        finally:
            if p.poll() is None:
                p.kill()
                p.wait()
            if p.stdout:
                p.stdout.close()
            if p.stderr:
                p.stderr.close()

    def test_concurrent_stream_flood_is_bounded(self):
        (self.repo / "bench.sh").write_text(
            "#!/bin/sh\n"
            "dd if=/dev/zero bs=65536 count=2 2>/dev/null\n"
            "dd if=/dev/zero bs=65536 count=2 1>&2 2>/dev/null\n"
            "echo METRIC elapsed_ms=8\n"
        )
        self.git("add", "bench.sh")
        self.git("commit", "-qm", "Flood fixture")
        self.init()
        self.cli("run", "--baseline", expected=4)
        attempt = self.cli("status")["last_attempt"]
        self.assertIsNone(attempt["score"])
        for stream in ("stdout", "stderr"):
            self.assertEqual(attempt["benchmark"][stream]["saved"], 65536)
            self.assertTrue(attempt["benchmark"][stream]["truncated"])
            self.assertEqual((self.repo / ".auto/runs/r-000001" /
                              ("benchmark." + stream)).stat().st_size, 65536)

    def test_repeat_median_mad_and_secondary_missing(self):
        (self.repo / "bench.sh").write_text(
            "#!/bin/sh\n"
            "case $(ls .auto/runs | wc -l | tr -d ' ') in\n"
            "  1) echo METRIC elapsed_ms=1; echo METRIC µs=3;;\n"
            "  2) echo METRIC elapsed_ms=10;;\n"
            "  3) echo METRIC elapsed_ms=3; echo METRIC µs=7;;\n"
            "esac\n"
        )
        self.git("add", "bench.sh")
        self.git("commit", "-qm", "Repeated fixtures")
        self.init(budget=3)
        self.cli("run", "--baseline", "--repeat", "3")
        baseline = self.cli("status")["baseline"]
        self.assertEqual((baseline["score"], baseline["mad"], baseline["samples"]),
                         (3.0, 2.0, [1.0, 10.0, 3.0]))
        self.assertEqual(baseline["secondary_missing"], ["µs"])
        self.assertNotIn("µs", baseline["metrics"])

    def test_higher_zero_baseline_and_absolute_tolerance(self):
        (self.repo / "bench.sh").write_text(
            "#!/bin/sh\n"
            "if grep -q fast src/value; then echo METRIC elapsed_ms=1; "
            "else echo METRIC elapsed_ms=0; fi\n"
        )
        self.git("add", "bench.sh")
        self.git("commit", "-qm", "Zero score fixture")
        self.cli("init", "--name", "Higher", "--metric", "elapsed_ms",
                 "--direction", "higher", "--scope", "src", "--max-runs", "3",
                 "--tolerance", "1", "--benchmark", "bench.sh")
        self.cli("run", "--baseline")
        self.begin()
        self.cli("run")
        self.assertEqual(self.cli("decide", "keep", "--reason", "At tolerance",
                                  expected=3)["code"], "not-improved")
        self.cli("decide", "discard", "--reason", "No strict improvement")
        self.assertEqual(self.cli("status")["best"], 0.0)

    def test_help_json_and_error_no_side_effects(self):
        empty = pathlib.Path(self.temp.name) / "empty"
        empty.mkdir()
        before = list(empty.iterdir())
        for command in (None, "init", "run", "begin", "decide", "status", "recover"):
            argv = [str(BIN), "--json", "--help"]
            if command:
                argv.insert(1, command)
            result = subprocess.run(argv, cwd=empty, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            parsed = json.loads(result.stdout)
            self.assertEqual(parsed["kind"], "help")
            if command:
                self.assertIn("Exit:", parsed["data"]["text"])
        self.assertEqual(list(empty.iterdir()), before)
        result = subprocess.run([str(BIN), "status", "--json"], cwd=empty,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads(result.stdout)["kind"], "error")
        self.assertEqual(result.stderr, "")

    def test_binary_with_empty_home_and_no_lisp_setup(self):
        empty_home = pathlib.Path(self.temp.name) / "new-home"
        empty_home.mkdir()
        env = {"HOME": str(empty_home), "PATH": "/usr/bin:/bin"}
        help_result = subprocess.run([str(BIN), "--json", "--help"], cwd=empty_home,
                                     env=env, text=True, capture_output=True)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertEqual(json.loads(help_result.stdout)["kind"], "help")
        self.init()
        status = subprocess.run([str(BIN), "--project", str(self.repo),
                                 "status", "--json"], cwd=empty_home,
                                env=env, text=True, capture_output=True)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(json.loads(status.stdout)["data"]["remaining"], 12)
        self.assertEqual(list(empty_home.iterdir()), [])

    def test_protected_input_must_be_tracked_and_scope_cannot_escape(self):
        with (self.repo / ".git/info/exclude").open("a") as f:
            f.write("\nextra\n")
        (self.repo / "extra").write_text("private")
        invalid = self.cli("init", "--name", "Bad", "--metric", "elapsed_ms",
                           "--direction", "lower", "--scope", "src", "--max-runs", "2",
                           "--benchmark", "bench.sh", "--input", "extra", expected=2)
        self.assertEqual(invalid["code"], "untracked-evaluator")
        self.assertFalse((self.repo / ".auto").exists())
        (self.repo / "extra").unlink()
        outside = pathlib.Path(self.temp.name) / "external"
        outside.write_text("external")
        (self.repo / "src/link").symlink_to(outside)
        self.git("add", "src/link")
        self.git("commit", "-qm", "External symlink fixture")
        invalid = self.cli("init", "--name", "Bad", "--metric", "elapsed_ms",
                           "--direction", "lower", "--scope", "src/link", "--max-runs", "2",
                           "--benchmark", "bench.sh", expected=2)
        self.assertEqual(invalid["code"], "path-escape")
        self.assertFalse((self.repo / ".auto").exists())

    def test_linked_worktree_admin_and_project_from_elsewhere(self):
        linked = pathlib.Path(self.temp.name) / "linked"
        self.git("worktree", "add", "-qb", "experiment", str(linked))
        self.repo = linked
        self.init()
        self.cli("run", "--baseline", cwd=ROOT)
        self.assertEqual(self.cli("status", cwd=ROOT)["best"], 10.0)

    def test_literal_pathspec_and_executable_mode(self):
        self.init()
        self.cli("run", "--baseline")
        self.begin()
        unusual = "src/:(top)[?]* µ.sh"
        file = self.repo / unusual
        file.write_text("#!/bin/sh\necho valid\n")
        file.chmod(0o755)
        self.cli("run")
        self.cli("decide", "keep", "--reason", "Literal unusual filename")
        self.assertIn(unusual, self.git("ls-files", "-z").split("\x00"))
        self.assertTrue(self.git("--literal-pathspecs", "ls-tree", "HEAD", "--",
                                 unusual).startswith("100755 blob "))
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_symlink_candidate_rejected_before_execution(self):
        self.init()
        self.cli("run", "--baseline")
        self.cli("begin", "--hypothesis", "Try symlink")
        (self.repo / "src/link").symlink_to("value")
        self.cli("run", expected=3)
        self.assertEqual(self.cli("status")["executions"], 1)
        (self.repo / "src/link").unlink()
        self.cli("decide", "discard", "--reason", "Unsupported file type")

    def test_nonzero_benchmark_is_null(self):
        (self.repo / "bench.sh").write_text(
            "#!/bin/sh\necho METRIC other=9\necho METRIC elapsed_ms=5\nexit 7\n"
        )
        self.git("add", "bench.sh")
        self.git("commit", "-qm", "Nonzero benchmark")
        self.init(budget=2)
        self.cli("run", "--baseline", expected=4)
        self.assertIsNone(self.cli("status")["last_attempt"]["score"])
        self.assertEqual(self.cli("status")["last_attempt"]["benchmark"]["exit"], 7)
        self.assertEqual(self.cli("status")["remaining"], 1)

    def test_missing_primary_is_null(self):
        (self.repo / "bench.sh").write_text("#!/bin/sh\necho METRIC other=9\n")
        self.git("add", "bench.sh")
        self.git("commit", "-qm", "Missing primary")
        self.init(budget=2)
        self.cli("run", "--baseline", expected=4)
        attempt = self.cli("status")["last_attempt"]
        self.assertIsNone(attempt["score"])
        self.assertEqual(attempt["metrics"]["other"], 9.0)
        self.assertEqual(attempt["benchmark"]["exit"], 0)

    def test_help_quickstart_verbatim_outside_checkout(self):
        help_text = subprocess.run([str(BIN), "--help"], cwd=self.temp.name,
                                   text=True, capture_output=True, check=True).stdout
        script = help_text.split("One-time setup", 1)[1].split("Commands:", 1)[0]
        script = "\n".join(line[2:] for line in script.splitlines()
                           if line.startswith("  "))
        env = os.environ.copy()
        env["PATH"] = str(BIN.parent) + os.pathsep + env["PATH"]
        result = subprocess.run(["/bin/sh", "-eu", "-c", script],
                                cwd=self.temp.name, env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertIn('"best":5.0', result.stdout)
        self.assertEqual((pathlib.Path(self.temp.name) / "demo/src/value").read_text(), "fast\n")

    def test_readme_quickstart_matches_executable(self):
        text = subprocess.run([str(BIN), "--help"], cwd=self.temp.name,
                              text=True, capture_output=True, check=True).stdout
        from_help = [line[2:] for line in
                     text.split("One-time setup", 1)[1].split("Commands:", 1)[0].splitlines()
                     if line.startswith("  ")]
        from_readme = (ROOT / "README.md").read_text().split("```sh", 2)[2].split("```", 1)[0]
        self.assertEqual(from_readme.strip().splitlines(), from_help)


if __name__ == "__main__":
    unittest.main(verbosity=2)
