# hillclimber

A caller-driven, local experiment CLI. You edit and think; hillclimber
measures, records evidence and makes scoped Git decisions. No agent service or
Node runtime. Start with `build/hillclimber --help`: its quickstart is complete
and executable, including one-time setup and a keep/discard cycle. Every
command also has `--help`.

Build on the tested macOS arm64 host:

```sh
cd /Users/liu/Code/hillclimber
./bootstrap.sh
python3 integration.py
```

`bootstrap.sh` verifies exact source revisions in `.deps/` and builds/tests
with ASDF and SBCL `--no-userinit --no-sysinit`. After dependencies are
present, `sbcl --no-userinit --no-sysinit --non-interactive --load build.lisp`
works offline. The native executable is `build/hillclimber`. Runtime requires
Git and `/bin/sh` plus the macOS image's Homebrew `libzstd.1.dylib`, but no
Lisp initialization or dependency fetch.

The executable's quickstart (run in a new disposable or dedicated worktree):

```sh
mkdir -p demo/src && cd demo && git init
echo slow > src/value
echo '#!/bin/sh' > bench.sh
echo 'if grep -q fast src/value; then echo METRIC elapsed_ms=5; else echo METRIC elapsed_ms=10; fi' >> bench.sh
echo '#!/bin/sh' > checks.sh
echo 'test -s src/value' >> checks.sh
git add src bench.sh checks.sh && git commit -m 'Set up experiment'
hillclimber init --name Demo --metric elapsed_ms --direction lower --unit ms --scope src --max-runs 12 --benchmark bench.sh --check checks.sh
hillclimber run --baseline --repeat 3
hillclimber begin --hypothesis 'Try fast value'
echo fast > src/value
hillclimber run --repeat 3 --timeout 120
hillclimber decide keep --reason 'Lower median; checks passed'
hillclimber begin --hypothesis 'Try slow again'
echo slow > src/value
hillclimber run
hillclimber decide discard --reason 'Regression'
hillclimber status --context --json
```

The six commands are `init`, `begin`, `run`, `decide`, `status`, `recover`.
Use `--project PATH` to target an exact worktree root and `--json` for
versioned, machine-readable stdout. Run `status --context --json` to resume.
All tests create disposable repositories under `scratch/`; they do not touch
user Git data. Build products and test fixtures stay ignored in this project.

For dependencies, licenses and verification evidence see `DEPENDENCIES.md`
and `VERIFICATION.md`. Linux is not yet tested; macOS results do not imply
Linux support. Evaluator protection is cooperative, not a sandbox. A shell
script can deliberately write outside scope or detach a descendant; only
ordinary process-group descendants are cleaned up. Journal fsync and tested
process-crash recovery do not guarantee arbitrary power-loss durability.
