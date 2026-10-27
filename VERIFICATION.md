# Verification log

## Milestone 1, executable and OS spike

- Host: macOS Darwin 27.0.0 arm64, SBCL 2.6.9, Git 2.54.0.
- `sbcl --no-userinit --no-sysinit --non-interactive --load build.lisp`:
  ASDF load, assertions and `program-op` image succeed; executable help and
  version work outside any repository, JSON stdout parses cleanly.
- POSIX `lockf(F_TLOCK)` contention verified by concurrent CLI writers in a
  disposable repository. Initial fork+`run-program` test **failed** descendant
  cleanup (the spawned shell made another group); replaced with `fork`,
  `setsid`, `dup2`, native `execv`. `integration.py` now confirms the timeout
  kills the ordinary shell descendant. This is not a sandbox.
- Decimal Unicode, null, boolean and JSON object round-trip assertions pass.
  Git root/branch and `--git-path info/exclude` use a synthetic worktree.
- Dependency pins and licenses: `DEPENDENCIES.md`; no Quicklisp runtime fetch.
  No Linux execution yet.

## Milestone 2, measurement

- Built artifact `build/hillclimber`. Three-sample baseline and candidate
  measurement persisted, with new-process `status --context --json` replay.
- `python3 integration.py`: failure/null primary, strict NaN rejection, budget
  exhaustion, protected evaluator drift, outside-scope drift and failing
  checks verified in newly created repositories. Raw per-invocation logs and
  recorded MAD inspected in quickstart run.
- Remaining at this checkpoint: interrupt and flood regression cases.

## Milestone 3, Git decisions

- Disposable keep and discard validated, including preserved new-file bytes,
  Git hook rejection and retry, changed source rejection, journal corruption
  blocking writes. No Git hook bypass.
- Remaining at this checkpoint: automated interruption at each decision
  boundary, linked worktree and unusual filename cases.

## Milestone 4, onboarding

- `integration.py` extracts the executable's top-level quickstart and executes
  it **verbatim** with the binary on PATH, in a fresh disposable repository
  outside the source checkout. Baseline, keep, discard and resumed JSON status
  pass. Command-specific help exists for all six commands. A fresh independent
  agent onboarding check remains for the coordinator.

## Milestone 5, release checks

- Pending final fingerprint, size/startup measurements and platform inventory.
  Linux has not been tested. Arbitrary power-loss guarantees are not claimed.
