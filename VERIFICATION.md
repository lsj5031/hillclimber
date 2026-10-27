# Verification log

## 1. Contract and SBCL spike (passed on macOS)

- Host: Darwin 27.0.0 arm64, SBCL 2.6.9, Git 2.54.0. Six commands, JSON
  response version 1, exit codes, budget policy and help precedence are
  specified in executable `--help` and each `COMMAND --help`.
- `./bootstrap.sh` checks exact dependency revisions and SBCL version, runs
  ASDF load/test and `program-op`. Pinned sources/licenses: `DEPENDENCIES.md`.
  Runtime never fetches dependencies or loads user Lisp initialization.
- POSIX advisory `lockf(F_TLOCK)` writer contention verified with two actual
  CLI processes in disposable Git fixtures. An initial fork+`run-program`
  attempt **failed** process-group cleanup; it was replaced with fork,
  `setsid`, `dup2`, native `execv` and bounded concurrent pipe readers.
  Timeout and Ctrl-C now reap ordinary shell descendants, for benchmarks
  and checks. This is cooperative execution, not a sandbox.
- ASDF assertions cover strict finite decimal parsing, zero, negative,
  exponents, Unicode names, last duplicate, null/boolean/Unicode JSON
  round-trip and median. The Lisp reader is never applied to METRIC lines.

## 2. Durable measurement (passed on macOS)

- `python3 integration.py` creates **new project-owned disposable repos** for
  each test. Three-sample baseline/candidate and a separate process's status
  replay agree. Budget counts every started benchmark even on failure/crash.
- Passing checks, failing checks, nonzero benchmark, missing primary, NaN,
  zero/higher direction, strict tolerance, medians/MAD, inconsistent secondary
  metrics, 64 KiB per-stream flood truncation, timeout/interrupt cleanup and
  missing-score `null` are exercised. Scripts run from project root under
  `/bin/sh` with standard input closed. Logs are retained per run.

## 3. Git decisions and recovery (passed on macOS)

- Keep commits only literal in-scope pathspecs after comparing committed
  content/modes with measured fingerprints; discard restores tracked files
  and preserves new bytes in `.auto/recovery/`. Tests cover executable mode,
  Unicode/metacharacter filenames, linked worktree administration, protected
  inputs, evaluator/HEAD/source drift, unrelated paths, staged foreign data,
  Git hook rejection and retry without bypass.
- Journal events distinguish candidate, run and decision IDs. Decision intent
  precedes Git mutation. Disposable crash injections cover after-run-start,
  after-intent, after-Git-commit, during-new-file-move, after-file-restoration
  and after-applied, followed by repeated `recover`. No duplicate commit or
  resolution. Incomplete final journal bytes are copied unchanged to
  `.auto/recovery/` before truncation; corrupt complete records block
  mutation. Status reads the complete prefix with an explicit warning.
- Session, journal, log and recovery-backup files are flushed/fsynced; newly
  created directories and recovery rename parents are fsynced on tested macOS.
  Git owns its own commit/checkout durability. This verifies process
  interruption, **not** arbitrary power-loss durability or hostile writers.

## 4. Help-only handoff (passed scripted check)

- The existing `test_help_quickstart_verbatim_outside_checkout` extracts the
  top-level executable help and executes its quickstart **verbatim** in a
  fresh disposable repo. Baseline, keep, discard and resumed JSON status pass.
  `test_readme_quickstart_matches_executable` guards documentation drift.
- Retained transcript: `scratch/onboarding-evidence/transcript.txt`. Resulting
  state: `scratch/onboarding-evidence/demo/.auto/events.jsonl`. The scripted
  result has best score 5, seven executions, five remaining and no pending
  candidate. This is **not** a fresh independent agent test.
- Coordinator's independent agent scenario: give only the executable path
  `/Users/liu/Code/hillclimber/build/hillclimber` and the objective
  "Improve a synthetic text-gate elapsed_ms score in a new dedicated
  disposable Git worktree; complete one decision and resume from status."
  The agent must use `--help` and command help without private instructions.

## 5. Release candidate (macOS passed; Linux blocked/unverified)

- Exact checks: `./bootstrap.sh`, `python3 integration.py` (33 passing
  disposable-repository tests), `sh -n bootstrap.sh`, `git diff --check`,
  JSON help/errors with no repository and an executable invoked outside the
  checkout with an empty HOME/PATH containing no SBCL or Quicklisp.
- Native artifact: `build/hillclimber` (Mach-O arm64), source commit
  `29a47cacf6db26c1e80f8789b3271b92ba3d2e16`, 41,162,824 bytes,
  SHA-256 `11b18da5884830c8f4bca6c3aae7718c947ef3b743c0f0376bb58d5457e7a96f`.
  Thirty isolated `--version --json` launches outside checkout: median
  10.896 ms, minimum 10.064 ms, maximum 21.881 ms, including process start.
  Raw summary: `build/release-measurements.json`. No performance threshold
  was assumed.
- `otool -L` lists macOS libSystem and Homebrew zstd 1.5.7. A foreign Mac
  without that library is **not** verified as runnable. Linux was **not**
  built/tested: there is no project-owned Linux environment with SBCL 2.6.9.
  A Docker daemon exists, but creating/installing into its global storage
  would exceed the project's allowed write boundary. Linux/other architectures,
  WSL and Windows are unverified; no claim of cross-platform behavior.
- No external publication/push, global application install, server,
  dashboard, SDK or supervision. The historic plan footer is superseded by
  the implementation authorization; `PLAN.md` was preserved unchanged.

## 6. Independent coordinator verification (2026-10-27)

- Coordinator inspected process handling, journal replay, scope and decision
  code, and the final bootstrap/test/documentation diff. A separate bootstrap
  run passed ASDF assertions and produced the same SHA-256 recorded above.
- Independent full integration suite: 33 tests passed in 65.410 seconds,
  exit 0. Log: build/coordinator-tests.log. Shell syntax and diff checks passed.
- Outside checkout, with an empty temporary HOME and PATH=/usr/bin:/bin,
  version/help returned clean versioned JSON and status returned the expected
  no-session error (exit 3), with no stderr contamination.
- Fresh Droid session 360ae31e-ad56-4de5-8c7d-fbe54b61eb28 received only the
  executable path, optimization objective and isolated scratch boundary. It
  discovered top-level/subcommand help, created a new linked worktree, measured
  baseline [10,10,10], measured candidate [5,5,5], kept one improvement and
  resumed status in separate invocations. Coordinator independently verified
  baseline 10, best 5, six executions, one resolved keep, matching accepted HEAD
  and a clean worktree. Agent exit 0; no onboarding obstacles reported.
- Transcript: scratch/independent-onboarding/events.jsonl; concise report:
  scratch/independent-onboarding/REPORT.md; resulting journal:
  scratch/independent-onboarding/text-gate-worktree/.auto/events.jsonl.
- Initial implementation worker exited 1 when its attempt to remove diagnostic
  scratch repositories was denied by its tool policy. Those fixtures were
  preserved; implementation and onboarding did not require their deletion.
