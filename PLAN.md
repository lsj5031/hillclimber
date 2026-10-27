# Universal autoresearch CLI — SBCL implementation plan

Historical implementation plan. The CLI is now implemented; README.md and
STATUS.md describe current release scope. Platform targets below are planning
goals, not support claims.

## Goal

Port the useful behavior of davebcn87/pi-autoresearch into a standalone Common Lisp executable built with SBCL. Any human or agent with shell access can drive it. No agent SDK, model API, Node runtime, or server is required at runtime.

Source inspected: https://github.com/davebcn87/pi-autoresearch at 04b8a50dac7efe80ffc91648bd00ed9b022e24c2. This is a behavior port of TypeScript code, not a mechanical extraction. Preserve MIT attribution for translated code or reused assets.

The CLI owns measurement, persistent state, validation and Git decisions. The caller owns hypotheses, source edits, interpretation and choosing the next experiment. Automatic agent continuation is outside this boundary.

Working command name: autoresearch; check collisions before installation. Initial platform target: Linux and macOS with SBCL. Other Lisp implementations, Windows and WSL require separate verification and are not initial support claims.

## First-release scope

Complete workflow: initialize a clean dedicated experiment worktree; measure baseline; begin candidate; edit; measure; inspect; keep/discard; repeat; resume from another caller.

Retain primary/secondary metrics, lower/higher direction, METRIC output, benchmark/check scripts, hypothesis and diagnostic memory, append-only results and portable context. Every command is a separate invocation; nothing essential can live only in process memory.

Bare-bones v1: six commands (init, begin, run, decide, status, recover), one executable and local files. Status includes optional bounded history and handoff context. Exclude dashboards, static report generation, pi-format exports/imports, MCP, agent-specific adapters, agent supervision, hooks, automatic ideas and branch finalization. Supply a short generic usage guide; no integration framework.

## Proposed CLI contract

Global options: --project PATH, --json, --help, --version. Default project is cwd; avoid silently selecting an unrelated ancestor repository. Resolve canonical worktree identity before mutations.

| Command | Responsibility |
| --- | --- |
| init | Set goal, metric/unit/direction, editable scope and finite run budget; validate clean dedicated Git worktree; create missing session templates without overwriting existing files. |
| run --baseline | Measure accepted source and establish baseline after successful benchmark/checks. No synthetic code commit. |
| begin --hypothesis TEXT | Reserve candidate ID before editing; snapshot accepted HEAD, scope and protected evaluator identities; require no pending candidate and clean source/index. |
| run | Measure pending candidate, capture finite metrics, source fingerprint, raw logs, exit status and checks. Support explicit repeats and timeouts. |
| decide keep / discard --reason TEXT | Resolve candidate using persisted evidence; keep commits only owned in-scope changes; discard restores owned changes and preserves new files in recovery storage. |
| status | Show baseline/best, current candidate, accepted revision, remaining budget and next valid action. |
| status --history N / --context | Optional bounded measurements/decisions or compact agent handoff, using the same state and output path. |
| recover | Inspect incomplete operations and reconcile established outcomes; ambiguous recovery requires explicit selected action. |

Illustrative flow; freeze exact flags in milestone 1:

    autoresearch init --name "Test runtime" --metric elapsed_ms --direction lower --unit ms --scope src --scope tests --max-runs 20
    autoresearch run --baseline --repeat 3
    autoresearch begin --hypothesis "Reuse the parser fixture"
    # Human or agent edits the declared source paths.
    autoresearch run --repeat 3 --timeout 120
    autoresearch decide keep --reason "Lower median runtime; checks passed"
    autoresearch status --context --json

Default output is readable text. --json produces one versioned response on stdout, including structured errors; child logs and Lisp startup/build messages must never contaminate it. Errors carry stable code, message and next action. Proposed exit codes: 0 completed, 2 invalid arguments, 3 state/precondition, 4 persisted benchmark/check failure, 5 Git/storage/internal failure, 130 interrupt. Discard is a successful decision and exits 0. Ordinary errors must never open the interactive Lisp debugger.

No replacement metric supplied to decide: evidence comes from the measured run. Keep requires passing checks, successful finite primary measurement, current source identical to measured source, and improvement beyond an explicit absolute tolerance. Secondary metrics are recorded for inspection; configurable secondary guardrails are deferred. Failure is represented as an outcome with missing score, never a fabricated native zero.

## Built-in help is the onboarding interface

An unfamiliar agent must be able to start correctly from autoresearch --help alone, then use command-specific --help for exact options. No installed skill, external website, repository browsing or agent-specific instructions should be required. This is part of the bare-bones product, not optional documentation polish.

Top-level --help includes:

- One-sentence purpose and division of responsibility: caller edits/thinks; CLI measures, records and applies Git decisions.
- Six commands and the complete sequence: init -> baseline -> begin -> edit -> run -> decide -> repeat; status for resumption, recover for interruption.
- Copyable quickstart, including a clean Git worktree setup, metric configuration, a minimal working benchmark script that prints METRIC name=value, an optional checks script, a real candidate edit, and both keep and discard paths. Use synthetic files/data so the example is safe and repeatable. Clearly distinguish one-time setup from repeated experiments.
- Script working directory, shell/interpreter, metric grammar and primary direction; explain that units are labels and do not convert values.
- --project and --json usage, where state/logs live, and how to discover current state with status --context --json instead of guessing or reinitializing.
- Essential constraints: declared editable scope, protected evaluator, no editing between measurement and keep, no manual commit/reset during a pending candidate, and who owns keep/discard.
- Compact exit-code reference and explicit links within the CLI to command-specific help. No pager, network, ANSI dependency or interactive prompts required.

Each command's --help gives exact syntax, required/optional arguments and actual defaults/units; prerequisites and valid states; filesystem/Git side effects; successful and failed outcomes; exit codes; and at least one runnable example. Errors name the unmet precondition and next valid command. Generated option tables and manually written workflow examples must use the same command definitions, avoiding conflicting defaults.

Top-level help stays compact enough to read in one agent tool response: put the quickstart first, advanced options in subcommand help. Help is available without a Git repository, a session, network access or writable cwd, and performs no mutations. --help exits 0. If --json is also present, return a versioned structured help object, not prose mixed into a JSON response. Define these precedence rules in the contract spike.

Acceptance: run the documented quickstart against the built executable in a disposable repository and exercise keep, discard and restart. Give a fresh agent only the executable path and an optimization objective; it must discover --help, set up the benchmark, complete one candidate decision and resume from status without private instructions. Retain its transcript and resulting state as onboarding evidence; deterministic tests separately catch stale options/defaults and help-side effects. This agent-assisted check is a later verification task, not an agent-specific runtime dependency.

## Durable state

Keep familiar .auto/ files but use a native event journal for lifecycle correctness:

    .auto/
      prompt.md                  human-authored objective/context
      measure.sh                 protected benchmark script
      checks.sh                  optional protected checks
      session.json               initial identity/settings
      events.jsonl               authoritative versioned lifecycle events
      runs/<run-id>/             logs, measurements, diagnostics
      recovery/<operation-id>/   recovery evidence and discarded new files
      session.lock               OS advisory lock location

There is no report/projection subsystem in v1. Status is reconstructed directly from the journal, using a deterministic reducer. Candidate IDs, measurement-attempt IDs and decision IDs are distinct. Candidate lifecycle: editing -> running -> measured -> finalizing -> resolved. Failed/interrupted runs remain inspectable; retry creates another attempt instead of erasing evidence. Decisions are idempotent by candidate ID and cannot duplicate commits on retry.

Protect one writer per session, including the benchmark duration, with an OS advisory lock via SBCL/POSIX. Read-only status reads committed journal prefixes. A truncated final record is diagnosed; repair preserves original bytes. Interior corruption blocks mutation. Do not invent stale PID-lock recovery when OS locks can release on process exit.

Journal decision intent before Git mutation; record resulting Git/file identities before final resolution. Recovery compares recorded evidence with actual HEAD and file state. Git and journal updates are not one atomic transaction, so interruption tests cover every boundary. Specify flushing, file fsync and directory synchronization where needed; distinguish tested process-crash recovery from unproven arbitrary power-loss durability.

Changing benchmark, metric definition or protected inputs requires a fresh baseline. For v1, prefer a new session over introducing a segment-management subsystem; legacy segment migration is outside v1.

## Git boundaries

Require a clean dedicated worktree and explicit editable scope. Creating the worktree can remain an ordinary Git operation performed before init; the CLI need not own worktree management. Refuse dirty/shared initialization rather than automatically stashing user work. Preserve and merge the repository's local exclude entries when excluding .auto/; verify the worktree administration path and that artifacts remain untracked.

Before each mutation verify repository/worktree identity, branch, accepted HEAD, candidate ownership and scope. Reject staged/foreign changes, branch drift and source changes since measurement. Keep stages only declared candidate paths, never broad git add -A. Use argv and safe pathspec handling; do not interpolate paths or descriptions into shell scripts.

Discard restores owned tracked changes and moves owned new files to recovery storage before removing their working copies. Never use broad git clean. Preserve session metadata, logs and diagnostics. Define handling for renames, deleted files, executable bits, symlinks, submodules, nested repositories and unusual filenames; unsupported cases fail before mutation. Validate scope cannot escape project root or include Git/session/scorer internals.

Protected evaluator hashes include benchmark/check scripts plus explicitly declared scorer/config/data inputs. Hash scripts before/after runs; a changed scorer invalidates comparison. Hashing two scripts alone cannot establish integrity of their dependencies. This is cooperative integrity checking, not a sandbox against a malicious caller.

A dedicated worktree is the ownership contract: advisory locks cannot prevent an unrelated editor changing files. Detected drift aborts; do not claim protection from hostile concurrent writers. Git hooks/signing failures are real failures and must not result in a successful keep record. Never silently bypass user Git configuration.

## Measurement rules

Support METRIC name=value lines with finite decimal grammar, exponents, negatives and zero. Never use Lisp READ on untrusted input. Reject NaN, infinity, hex and missing primary metric. Define name/Unicode grammar in fixtures, including upstream micro-symbol names. Duplicate names retain last-value-wins behavior with a diagnostic. Secondary-metric consistency must be explicit and tested.

Use monotonic time for durations, wall clock for timestamps. Persist all repeated samples and median aggregates. Every benchmark invocation, including baseline and failures, consumes a documented persisted execution budget. Built-in warmup orchestration is deferred; a benchmark script may perform its own warmup. Report candidate count separately from execution count. Budget exhaustion blocks further execution but permits inspection, discard, and valid decisions on already collected evidence. No hidden reset on restart or implicit retries.

Noise diagnostics use repeated measurements of unchanged code/configuration. Do not copy upstream confidence based on spread across different candidates. Median absolute deviation is descriptive variability, not statistical confidence. Zero MAD is not infinite certainty; zero baseline means relative improvement is undefined while absolute delta remains useful. Keep sample counts visible. A configurable tolerance is policy, not a significance test.

Launch argv by default; explicitly invoke the configured shell script rather than accepting interpolated command strings. Drain stdout/stderr concurrently to bounded logs, retain truncation metadata, return only bounded tails. Timeout and Ctrl-C terminate and reap the whole ordinary process group with a bounded TERM/KILL grace period, including checks. Deliberately detached processes are outside that guarantee. Running scripts remains authorized code execution, not containment.

## Lisp implementation choices

Use ASDF for load/build/test and UIOP where sufficient. Target SBCL directly for POSIX locks, signals/process groups and executable generation where portability helpers do not meet the contract. Use ordinary functions, structs and conditions, with deterministic state logic separate from I/O. No command class hierarchy, plugin framework or macro DSL.

Proposed libraries, subject to milestone-1 API/license and round-trip verification:

- clingon for subcommands, option validation and generated help.
- yason for JSON encoding/decoding, with explicit null/boolean/numeric policies.
- ASDF/UIOP bundled with SBCL; SB-POSIX contrib for needed Unix operations.
- A maintained digest library only if required for file fingerprints; select and pin it explicitly rather than relying on undocumented platform hash utilities.

Pin SBCL and all dependency revisions in a reproducible bootstrap manifest. Unpinned Quicklisp downloads are not a release build; runtime never downloads code. Inventory transitive dependencies/licenses. Build with sb-ext:save-lisp-and-die or an equivalent ASDF program-op contract, using --no-userinit --no-sysinit. Build per OS/architecture; these are native host-specific images, not one cross-platform binary. Do not save live locks, processes, project streams or personal initialization state into the image.

Suggested responsibility split: package.lisp, model.lisp, store.lisp, process.lisp, git.lisp, cli.lisp, ASDF/build files, focused tests. Keep text/JSON status rendering in CLI; no reporting subsystem. Development may use the REPL; deployed CLI behavior remains noninteractive and deterministic at its boundaries.

Current environment observation: sbcl was not found on PATH on the Linux implementation host. Installing/provisioning it is future implementation setup. No SBCL execution or packaging has been verified yet.

## Upstream relationship

Reuse the experiment workflow, METRIC lines and benchmark/check/prompt conventions. Start fresh native sessions; detect existing pi state and refuse to overwrite or adopt it silently. No legacy session migration, pi-format projection, dashboard assets or pi adapter in v1. Preserve MIT attribution for any translated code. Native failed/missing scores are null rather than legacy zero sentinels.

## Milestones and acceptance gates

### 1. Contract and SBCL spike

Freeze CLI/schema, metric grammar, budgets and recovery semantics; pin libraries/licenses. Prove executable generation, clean JSON stdout, Unicode/null round trips, locks, Git worktree identity and descendant-process timeout in disposable fixtures.

Gate: real execution with SBCL on the implementation host. Resolve process-group/locking limitations before building on them. Record decisions and runnable checks, not a plan-only handoff.

### 2. Durable measurement slice

Implement init, baseline, begin, run and status with handoff context; journal replay, log capture, checks and budgets. Produce an executable early.

Gate: one CLI process records baseline/candidate; another reconstructs identical state. Failure/missing metrics/checks and interrupted runs persist accurately. No agent service is needed.

### 3. Git decisions and recovery

Implement scoped keep/discard, intent journal and recovery.

Gate: a synthetic repository keeps an improvement, discards a regression, preserves all diagnostics/recovery bytes, rejects outside-scope or measured-source drift, handles failed Git hooks, and recovers from kills between finalization steps without duplicate commits or decisions.

### 4. Portable handoff and usage

Finish status --context/--history and built-in top-level/subcommand help. The short README mirrors the executable quickstart; --help remains sufficient on its own.

Gate: two independent shell callers can hand off an experiment using only executable/files. No agent adapter, report generator or dashboard is installed or needed.

### 5. Release-candidate verification

Clean build/test/package on Linux and macOS. Invoke produced binaries outside the source checkout with no developer Lisp setup. Record host, runtime, source revision and artifact fingerprints; measure startup time and artifact size without speculative thresholds.

Gate: reproducible end-to-end transcript, appropriate tests, dependency/attribution inventory and explicit platform limitations. Untested OS/architecture remains unverified. Publishing, external push and global installation are not implied.

## Verification matrix

Domain: lower/higher; zero/negative scores; finite grammar; duplicate/secondary metrics; baseline failure; budget boundaries; medians/variability; deterministic replay; idempotent decision; corrupted journal.

Process: concurrent stdout/stderr flood; output limit; nonzero exit; missing metric; failed checks; timeout; Ctrl-C; descendant cleanup; Unicode; JSON stdout purity; documented exit codes.

Git/storage: baseline -> keep -> discard -> restart; tracked/untracked/renamed files; linked-worktree .git file; staged foreign work; scorer/source drift; hook failure; writer contention; interrupted finalization at every boundary; preserved recovery files. Run against newly created temporary repositories only.

Distribution: clean ASDF build/test; help/version/error; execution without Quicklisp/Node/pi; Linux/macOS process lifecycle; dependency pins/licenses; paths with spaces and Unicode. No claims about unexecuted platforms or power-loss recovery.

## Proposed decisions

1. SBCL/Common Lisp executable, CLI first, Linux/macOS first.
2. Caller-driven experiment toolkit; no supervisor or MCP in v1.
3. Clean dedicated worktree, explicit scope and recoverable discard.
4. Native event journal and text/JSON status only; no exports, dashboard or legacy migration.
5. Preserve the experiment workflow while improving durable state and honest noise reporting.

Next action: discuss/revise the plan, then separately authorize milestone 1. This document does not start implementation.

## References checked

- https://github.com/davebcn87/pi-autoresearch
- https://github.com/dnaeon/clingon
- https://github.com/phmarek/yason
- https://www.sbcl.org/manual/
- https://asdf.common-lisp.dev/uiop.html
