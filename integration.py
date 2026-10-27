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
                         "hillclimber candidate 000001: Lower median")
        self.cli("begin", "--hypothesis", "Try slow")
        (self.repo / "src/value").write_text("slow\n")
        (self.repo / "src/new file").write_bytes(b"preserved\n")
        self.cli("run")
        self.cli("decide", "discard", "--reason", "Regression")
        self.assertEqual((self.repo / "src/value").read_text(), "fast\n")
        self.assertEqual((self.repo / ".auto/recovery/000002/src/new file").read_bytes(), b"preserved\n")
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
        self.assertEqual(self.cli("status")["candidate"]["id"], "000001")
        hook.unlink()
        self.cli("decide", "keep", "--reason", "Hook passed")
        self.assertEqual(self.cli("status")["best"], 5.0)

    def test_journal_corruption_preserved(self):
        self.init()
        journal = self.repo / ".auto/events.jsonl"
        journal.write_bytes(b'{"v":1,"type":"begin"\n')
        before = journal.read_bytes()
        self.cli("status", expected=5)
        self.cli("run", "--baseline", expected=5)
        self.assertEqual(journal.read_bytes(), before)

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
            self.cli("run", "--baseline", expected=3)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
