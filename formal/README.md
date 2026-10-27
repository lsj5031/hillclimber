# Finite-state verification

From the checkout root, run `sh formal/run.sh`. It runs SANY, two
exhaustive TLC configurations and two expected-failing mutation controls.
Logs, state fingerprints and counterexample traces go to ignored
`scratch/formal/run.*/`, with a new directory per invocation so an
interrupted Java child cannot corrupt another run's metadata. The script
prints its log directory. It requires the pinned TLA+ 1.7.4 launchers,
Java 21 and `rg`; it caps the JVM at 2 GiB, TLC at two workers, and uses
disk-backed fingerprint/state queues. A passing run checks the **model**,
not the executable. `Workflow.cfg` checks safety without fairness;
`Recovery.cfg` checks liveness only under the conditions below.

## State and source correspondence

| Model | Implementation |
| --- | --- |
| `log`, `Last`, `Starts`, `Accepted`, `OpenIntent` | `core.lisp:186-251`: fsynced `append-event`, complete-record `journal`, replayed `state`; `workflow.lisp:439-470`: `recover-session` |
| `holders`, `Acquire`, `Release`, `Crash` | `core.lisp:252-261`: nonblocking OS `lockf` around CLI mutation; process exit releases the lock |
| `Begin`, `Edit`, `NewFile` | `workflow.lisp:226-241`: `begin-candidate`; `core.lisp:108-143`: scoped path and byte/mode fingerprints |
| `StartRun`, `FinishRun`, `Aggregate`, `RecoverRun` | `workflow.lisp:136-225,439-470`: durable `attempt-start` reserves one execution, failed/pass `attempt` and aggregate, interrupted attempt recovery; `process.lisp:77-143`: script outcomes |
| `Drift`, `RestoreEvaluator`, `DecideKeep`, `DecideDiscard` | `core.lisp:143-165`: protected fingerprint; `workflow.lisp:243-283`: improved-score, current-source, budget and protected-input guards |
| `HookFailure`, `Commit`, `RecordApplied`, `Resolve` | `workflow.lisp:287-337,338-438`: cancel only after failed commit with unchanged HEAD; verify committed tree, append applied then resolved; `recover-session` re-enters `apply-decision` |
| `MoveNew`, `RestoreTracked`, `saved` | `workflow.lisp:384-417`: checked new-file rename to recovery storage and idempotent tracked-file restore |

`log` is an ordered durable sequence, rather than a derived mutable counter:
`Starts` counts its `attempt-start` events even when no result was written.
`Accepted` is replayed from the last baseline or resolved decision, not copied
from Git HEAD. `head` and `commits` are independent of the journal, so the
invariants can detect a Git commit without journal resolution and an
unintended second commit. `file` and `saved` are independent locations; moving
a new file changes both. Score labels encode baseline 10, passing improved 5,
flat 10, or failed/missing evidence. A keep needs the *latest* passing
aggregate with the current source and protected-input fingerprint; a failed
later attempt invalidates that selection. An interrupted recovery attempt has
source `unknown`, representing the absent `source` field in the actual
`attempt` event; it may be discarded but can never justify keep. A failed
measured attempt with a source fingerprint requires it to match on discard.
`BadEvidence` removes the keep guard;
`BadCommitRetry` permits a second Git commit **after a crash following the
first commit**. Both must produce real TLC traces, not merely parse failures.

## Boundaries and assumptions

- One already persisted, passing baseline consumes one execution. One candidate
  can consume at most two further starts (total budget 3). Up to two decision
  intents allow a Git-hook failure followed by a retry. Two CLI clients contend
  for one atomic OS lock. Tracked source has three byte identities (`s0`, `s1`,
  `s2`); one new file has two possible byte identities (`b1`, `b2`) or is absent.
  Absolute tolerance is zero; `improved` stands for score 5 against baseline
  10, `flat` for 10. This is a finite abstraction of paths and scores, not a
  file-count limit in the CLI.
- Log append/fsync, Git's completed commit, and the new-file rename are modeled
  as separate atomic durable operations. A process crash can occur between any
  modeled steps and releases the lock without altering journal, HEAD or file
  bytes. The model does not establish power-loss durability, partial-byte
  writes, atomicity of Git's internal objects, concurrent hostile writers, or
  behavior on other operating systems.
- `"h1"` denotes a commit with the intended parent, candidate marker and
  verified tree; Git index staging, hooks that alter files and external HEAD
  changes are not modeled. Recovery refuses rather than repairs ambiguous
  commits in the implementation.
- Benchmark/check failure, score flatness and Git-hook refusal are
  nondeterministic. External source and evaluator drift may block actions,
  including after decision intent; recovery never assumes they are eventually
  repaired. HEAD, identity and foreign index/worktree drift are *not* generated:
  the code rejects them rather than repairing them. Full JSON schema validation,
  truncated/corrupt journal handling, exact Git pathspecs/modes, scope checks,
  fingerprint collisions, numeric median/MAD and multi-sample aggregation,
  concurrent edits during an evaluator invocation, output parsing and
  timeouts require implementation tests or a finer model.
  The model assumes a score marked improved was produced by the declared
  evaluator and that source fingerprints faithfully represent the bytes/mode.
- `Recovery.tla` starts at three pending-intent boundaries: keep before commit,
  keep after commit, and discard with a new file. Its next-state relation rules
  out further crashes, edits, evaluator drift and Git-hook failures; the
  recovered writer retains its lock. Weak fairness for lock acquisition and
  **each** enabled Git/file/journal recovery step then checks eventual
  resolution. This is not a claim of eventual recovery under infinite crashes,
  permanent hook failure, or continued drift. Terminal resolved states are
  expected, so only the recovery configuration disables TLC's deadlock check.

Safety invariants check writer exclusion, budget reservation, at most one Git
commit per modeled decision, improved persistent evidence matched to intent
and resolution, intact moved-file bytes, and either reconciled accepted HEAD
or an open intent. These are nontrivial implications over independently updated
journal, Git and file states. They do **not** establish implementation/model
trace conformance. To prove that connection would require a refinement map
from each real CLI/Git/fsync step and independent executable traces at every
model boundary. Existing `integration.py` exercises several crash boundaries,
hook failure, concurrent lock contention, budget recovery, drift and new-file
preservation, but is not an exhaustive refinement proof.

## Results

The executable checks passed: `./bootstrap.sh` (existing ASDF assertions)
and `python3 integration.py` (34 tests in 103.424s, including the new
interrupted-attempt regression). The regression failed before the
`workflow.lisp` fix with `source-drift`, then passed after rebuilding.

The exact formal run is `sh formal/run.sh` at the checkout root; from
`formal/`, its commands are (the script creates a unique `out` directory):

```sh
export JAVA_TOOL_OPTIONS=-Xmx2048m
mkdir -p ../scratch/formal
out=$(mktemp -d ../scratch/formal/run.XXXXXXXX)
/Users/liu/.local/bin/sany Workflow.tla
/Users/liu/.local/bin/sany Recovery.tla
/Users/liu/.local/bin/tlc -workers 2 -fpmem 0.1 -metadir "$out/Workflow" -config Workflow.cfg Workflow.tla
/Users/liu/.local/bin/tlc -workers 2 -fpmem 0.1 -metadir "$out/Recovery" -config Recovery.cfg Recovery.tla
/Users/liu/.local/bin/tlc -workers 2 -fpmem 0.1 -metadir "$out/BadEvidence" -config BadEvidence.cfg Workflow.tla
/Users/liu/.local/bin/tlc -workers 2 -fpmem 0.1 -metadir "$out/BadCommitRetry" -config BadCommitRetry.cfg Workflow.tla
```

The pinned official 1.7.4 jar has SHA-256
`936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88`;
the included TLC identifies itself as 2.19 (rev `5a47802`), SANY2 as
2.1. On 2026-10-27, `sh formal/run.sh` exited 0. Both SANY parses passed.
The exact retained log directory is `scratch/formal/run.ectpJjbf/`. Each
configuration used two workers, `-fpmem 0.1`, a 2 GiB JVM cap, and the
constants shown in its `.cfg` (`Clients = {"w1","w2"}`, `Budget = 3`).

| Config | Outcome (TLC exit) | Generated / distinct / queued | Depth; duration | Fingerprint index; seed |
| --- | --- | --- | --- | --- |
| `Workflow.cfg` | All safety invariants hold (0) | 7,049,145 / 1,188,426 / 0 | 24; 04min 27s | 34; 7788207685151531514 |
| `Recovery.cfg` | Fair eventual resolution holds (0) | 32 / 27 / 0 | 6; 00s | 46; -7523435235475986134 |
| `BadEvidence.cfg` | `EvidenceSafe` violated (expected 12) | 46 / 35 / 25 | 5; 00s | 85; -7993712879700596870 |
| `BadCommitRetry.cfg` | `CommitOnce` violated (expected 12) | 192,388 / 66,894 / 38,941 | 12; 01s | 50; 4478145355309578992 |

`BadEvidence` reaches an intent to keep `s1` with **no candidate aggregate**
(state 5). `BadCommitRetry` reaches one commit at state 9, a crash releasing
the lock at state 10, and a second commit at state 12. The failing runs stop
at their first counterexample, so their nonzero queue counts are expected,
not exhaustive negative searches. TLC's actual-fingerprint collision
estimate for the complete safety run was `2.8E-8`, not zero. These results
are exhaustive only for the stated finite transition systems and
fingerprinting method, not a proof of the implementation.

An earlier safety run was stopped because an obsolete wrapper left an
overlapping Java child writing the same metadata and log. Those partial
counts are **not** results; the interrupted artifacts were archived under
ignored `scratch/formal/interrupted-shared-metadata/`. The final runner uses
unique per-invocation paths to prevent that interference. Per-run logs and
state files remain ignored and are not committed.
