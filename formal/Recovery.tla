------------------------------- MODULE Recovery -------------------------------
EXTENDS Workflow

\* A pending keep (before/after its Git commit), or a pending discard with
\* an untracked file. These are crash-surviving states, not new journal writes.
RecoveryInit ==
  \E action \in {"keep", "discard"}, alreadyCommitted \in BOOLEAN :
    /\ (action = "keep" \/ ~alreadyCommitted)
    /\ log = <<E("start", "s0", "none", "trusted", "h0"),
               E("attempt-ok", "s0", "none", "trusted", "h0"),
               E("baseline", "s0", "none", "trusted", "h0"),
               E("begin", "s0", "none", "trusted", "h0"),
               E("start", "s1", "b1", "trusted", "h0"),
               E("attempt-good", "s1", "b1", "trusted", "h0"),
               E("aggregate", "s1", "b1", "improved", "h0"),
               E("intent", "s1", "b1", action, "h0")>>
    /\ holders = {} /\ source = "s1" /\ file = "b1"
    /\ saved = "none" /\ evaluator = "trusted"
    /\ head = (IF alreadyCommitted THEN "h1" ELSE "h0")
    /\ commits = (IF alreadyCommitted THEN 1 ELSE 0)
    /\ aggregating = "idle" /\ restored = FALSE
    /\ postCrashCommit = alreadyCommitted

AcquireAny == \E c \in Clients : Acquire(c)
Stable(A) == A /\ UNCHANGED postCrashCommit
\* Environment assumption: after this crash there are no more crashes, no
\* external edits, no evaluator drift and no failing Git hooks. The process
\* keeps the lock until it resolves. Each enabled recovery step eventually
\* executes (weak process/Git/filesystem fairness).
RecoveryNext ==
  Stable(AcquireAny \/ Commit \/ MoveNew \/ RestoreTracked
         \/ RecordApplied \/ Resolve)
RecoverySpec ==
  RecoveryInit /\ [][RecoveryNext]_vars
  /\ WF_vars(Stable(AcquireAny)) /\ WF_vars(Stable(Commit))
  /\ WF_vars(Stable(MoveNew)) /\ WF_vars(Stable(RestoreTracked))
  /\ WF_vars(Stable(RecordApplied)) /\ WF_vars(Stable(Resolve))
EventuallyResolved == <>Resolved
===============================================================================
