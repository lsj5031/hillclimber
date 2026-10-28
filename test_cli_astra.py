"""Focused CLI regressions. Run: python3 -m unittest -v test_cli_astra"""
import json
import math
import os
import signal
import subprocess
import time
import unittest

import integration

BIN, SCRATCH = integration.BIN, integration.SCRATCH


class CliAstra(unittest.TestCase):
    setUp = integration.Integration.setUp
    git = integration.Integration.git
    cli = integration.Integration.cli
    init = integration.Integration.init

    def test_astra_missing_option_values_preserve_json(self):
        for option in ("--project", "--repeat", "--timeout", "--history",
                       "--name", "--scope", "--reason", "--tolerance"):
            for following in ("--json", "--help", "--version", "--baseline",
                              "--context", "--repeat"):
                for json_first in (False, True):
                    with self.subTest(option=option, following=following,
                                      json_first=json_first):
                        args = ["--project", str(self.repo)]
                        if json_first:
                            args.append("--json")
                        args += ["--help", option, following]
                        if not json_first and following != "--json":
                            args.append("--json")
                        result = subprocess.run(
                            [str(BIN), *args], cwd=self.repo,
                            text=True, capture_output=True, timeout=5)
                        self.assertEqual(result.returncode, 2,
                                         (args, result.stdout, result.stderr))
                        self.assertEqual(result.stderr, "")
                        response = json.loads(result.stdout)
                        self.assertEqual((response["v"], response["kind"],
                                          response["data"]["code"]),
                                         (1, "error", "arguments"))
        self.assertFalse((self.repo / ".auto").exists())

    def test_astra_negative_numeric_and_flag_looking_text(self):
        # Negative tokens are values, not options. Domain validation still
        # applies to repeat/timeout/history when executing rather than helping.
        for option in ("--repeat", "--timeout", "--history", "--tolerance"):
            result = subprocess.run(
                [str(BIN), "--project", str(self.repo), "--help", option,
                 "-1", "--json"], cwd=self.repo, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
            self.assertEqual(json.loads(result.stdout)["kind"], "help")
        self.cli("init", "--name", "-demo", "--metric", "elapsed_ms",
                 "--direction", "lower", "--scope", "src", "--max-runs", "12",
                 "--benchmark", "bench.sh", "--tolerance", "-0")
        self.cli("run", "--baseline")
        self.cli("begin", "--hypothesis", "-try this")
        self.assertEqual(self.cli("status")["candidate"]["hypothesis"], "-try this")
        for command, option in (("run", "--repeat"), ("run", "--timeout"),
                                ("status", "--history")):
            self.assertEqual(self.cli(command, option, "-1", expected=2)["code"],
                             "arguments")

    def test_astra_sigterm_cleans_benchmark_and_check(self):
        evidence = []
        for stage, json_requested in (("benchmark", True), ("checks", True),
                                      ("benchmark", False)):
            with self.subTest(stage=stage, json_requested=json_requested):
                fixture = integration.Integration(methodName="runTest")
                fixture.setUp()
                try:
                    slow = ("echo $$ > .auto/shell.pid\n"
                            "sleep 60 &\necho $! > .auto/child.pid\nwait\n")
                    (fixture.repo / "bench.sh").write_text(
                        slow + "echo METRIC elapsed_ms=10\n" if stage == "benchmark"
                        else "echo METRIC elapsed_ms=10\n")
                    (fixture.repo / "checks.sh").write_text(
                        slow if stage == "checks" else "exit 0\n")
                    fixture.git("add", "bench.sh", "checks.sh")
                    fixture.git("commit", "-qm", "Slow cancellation fixture")
                    fixture.init(budget=2)
                    head = fixture.git("rev-parse", "HEAD")
                    argv = [str(BIN), "--project", str(fixture.repo), "run",
                            "--baseline", "--timeout", "30"]
                    if json_requested:
                        argv.append("--json")
                    child = subprocess.Popen(argv, cwd=fixture.repo, text=True,
                                             stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE)
                    try:
                        marker = fixture.repo / ".auto/child.pid"
                        deadline = time.monotonic() + 5
                        while not marker.exists() or not marker.read_text().strip():
                            self.assertLess(time.monotonic(), deadline)
                            time.sleep(.01)
                        pids = [int((fixture.repo / ".auto" / name).read_text())
                                for name in ("shell.pid", "child.pid")]
                        os.kill(child.pid, signal.SIGTERM)
                        out, err = child.communicate(timeout=5)
                        deadline = time.monotonic() + 3
                        alive = list(pids)
                        while alive and time.monotonic() < deadline:
                            alive = []
                            for pid in pids:
                                try:
                                    os.kill(pid, 0)
                                    alive.append(pid)
                                except ProcessLookupError:
                                    pass
                            if alive:
                                time.sleep(.02)
                        evidence.append(dict(stage=stage, argv=argv,
                                             json_requested=json_requested,
                                             cwd=str(fixture.repo),
                                             exit=child.returncode,
                                             stdout=out, stderr=err,
                                             pids=pids, surviving=alive))
                        (SCRATCH / "astra-sigterm-evidence.json").write_text(
                            json.dumps(evidence, indent=2) + "\n")
                        self.assertEqual(alive, [])
                        self.assertEqual(child.returncode, 143, (out, err))
                        if json_requested:
                            self.assertEqual(err, "")
                            response = json.loads(out)
                            self.assertEqual((response["kind"], response["data"]["code"]),
                                             ("error", "terminated"))
                            self.assertIn("recover", response["data"]["next"])
                        else:
                            self.assertEqual(out, "")
                            self.assertIn("terminated: Terminated by SIGTERM", err)
                            self.assertIn("recover", err)
                        before = fixture.cli("status")
                        self.assertEqual((before["executions"], before["remaining"],
                                          before["next"]), (1, 1, "recover"))
                        fixture.cli("recover")
                        journal = fixture.repo / ".auto/events.jsonl"
                        recovered = journal.read_bytes()
                        fixture.cli("recover")
                        self.assertEqual(journal.read_bytes(), recovered)
                        after = fixture.cli("status")
                        self.assertIsNone(after["last_attempt"]["score"])
                        self.assertEqual(after["executions"], 1)
                        self.assertEqual(fixture.git("rev-parse", "HEAD"), head)
                        self.assertEqual(fixture.git("status", "--porcelain"), "")
                    finally:
                        if child.poll() is None:
                            child.terminate()
                            child.communicate(timeout=5)
                        if child.stdout:
                            child.stdout.close()
                        if child.stderr:
                            child.stderr.close()
                finally:
                    fixture.doCleanups()

    def test_astra_finite_median_samples(self):
        cases = [
            (["1e308", "1e308"], 1e308, 0.0),
            (["-1e308", "-1e308"], -1e308, 0.0),
            (["-1e308", "1e308"], 0.0, 1e308),
            (["-1.7976931348623157e308", "1.7976931348623157e308"],
             0.0, float.fromhex("0x1.fffffffffffffp+1023")),
            (["1e308", "1.6e308"], 1.3e308, 3e307),
            (["-1.6e308", "-1e308"], -1.3e308, 3e307),
            (["1e-308", "1e-308"], 1e-308, 0.0),
            (["1", "5", "3"], 3.0, 2.0),
            (["2", "4", "6", "8"], 5.0, 2.0),
        ]
        for samples, score, mad in cases:
            with self.subTest(samples=samples):
                fixture = integration.Integration(methodName="runTest")
                fixture.setUp()
                try:
                    cases_sh = "\n".join(
                        f"{i}) echo METRIC elapsed_ms={sample};;"
                        for i, sample in enumerate(samples, 1))
                    (fixture.repo / "bench.sh").write_text(
                        "case $(ls .auto/runs | wc -l | tr -d ' ') in\n"
                        + cases_sh + "\nesac\necho METRIC aux=1e308\n")
                    fixture.git("add", "bench.sh")
                    fixture.git("commit", "-qm", "Finite score fixture")
                    fixture.init()
                    result = fixture.cli("run", "--baseline", "--repeat",
                                         str(len(samples)))
                    self.assertTrue(math.isfinite(result["score"]))
                    self.assertTrue(math.isfinite(result["mad"]))
                    self.assertTrue(math.isclose(result["score"], score,
                                                 rel_tol=1e-15, abs_tol=0))
                    self.assertTrue(math.isclose(result["mad"], mad,
                                                 rel_tol=1e-15, abs_tol=0))
                    status = fixture.cli("status")
                    self.assertEqual(status["baseline"]["score"], result["score"])
                    self.assertEqual(status["baseline"]["metrics"]["aux"], 1e308)
                    self.assertEqual(status["executions"], len(samples))
                finally:
                    fixture.doCleanups()


if __name__ == "__main__":
    unittest.main()
