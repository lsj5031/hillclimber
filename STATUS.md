# Current status

Milestones 1-4 have working macOS gates (see `VERIFICATION.md`); milestone 5
is in progress. Seven disposable integration tests and ASDF assertions pass
after replacing a failed process-group approach with native `execv`.
Remaining: interrupt and decision-boundary recovery tests, final build
fingerprint and startup measurements. Linux remains unverified.
