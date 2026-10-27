# Status

The six-command macOS arm64 CLI is implemented. Milestones 1-4 pass; milestone
5 passes on macOS, but Linux remains unverified. `./bootstrap.sh` runs ASDF
assertions and builds `build/hillclimber`; `python3 integration.py` passes
34 disposable-repository tests plus one portable formal-runner test. See `VERIFICATION.md` for exact gates,
artifact fingerprint and retained quickstart evidence.

Independent fresh-agent help-only onboarding passed: baseline 10, best 5, one
keep and resumed status in a clean linked worktree. Evidence is retained under
scratch/independent-onboarding/.

Remaining limits: Linux/other OS builds are unverified; this image dynamically
links Homebrew zstd; deliberately detached benchmark descendants and arbitrary
power loss are outside the tested guarantees.
