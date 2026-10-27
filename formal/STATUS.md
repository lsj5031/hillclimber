# Formal verification status

- 2026-10-27: Mapped journal replay, attempt reservation, keep/discard and
  recover boundaries in `core.lisp` and `workflow.lisp`. Added `Workflow.tla`
  with two writers and finite durable event history.
- Initial SANY parse passed; initial budget-3 safety exploration completed
  (822,159 distinct states, depth 23). This was before explicit score classes
  and the post-crash mutation refinement, so it is **not** the final result.
- Evidence-guard and duplicate-commit mutations produced TLC safety
  counterexamples; the latter is being refined to require a crash before retry.
- Refined the duplicate-commit control to require a crash; the trace includes
  `Crash` between two commits. Added distinct running/ready/idle states so a
  crashed attempt cannot be completed by a different invocation. A first
  complete-run attempt exposed a TLC type mismatch (mixed boolean/string
  values); corrected it before rerunning.
- Existing `./bootstrap.sh` passed ASDF assertions; `python3 integration.py`
  passed all 33 pre-existing tests in 93.883s using local pinned dependencies.
- Found and reproduced an implementation dead end: a recovered interrupted
  attempt has no source fingerprint, so `decide discard` failed with no budget
  left. Added an executable regression (red before the fix, green after) and
  skipped the drift comparison only for attempts with no recorded source;
  passing keep evidence still requires a matching source. Updated the model
  so interrupted recovery is not treated as measured evidence.
- Final `./bootstrap.sh` passed ASDF assertions; full `python3 integration.py`
  passed 34 tests in 103.424s. The new regression also passed independently
  after the fix (4.323s, including a rejected keep).
- Two overlapping TLC processes were found writing the same `Workflow` log
  and metadata after an obsolete wrapper was stopped without its Java child.
  Both processes were stopped; interrupted counts are invalid. Archived the
  shared artifacts in ignored scratch. `run.sh` now uses a unique run
  directory on every invocation.
- Uncontended `sh formal/run.sh` passed: 1,188,426 distinct safety states,
  depth 24; 27 distinct fair-recovery states, depth 6. Both expected mutation
  failures produced traces. Details and fingerprint data:
  `formal/README.md`; ignored logs: `scratch/formal/run.ectpJjbf/`.
  Verification is complete; no external publication was performed.
