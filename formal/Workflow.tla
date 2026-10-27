------------------------------- MODULE Workflow -------------------------------
EXTENDS Naturals, Sequences, FiniteSets, TLC

\* One initialized session, one candidate, two competing CLI processes.
\* Baseline is already persisted (one attempt-start, attempt, baseline).
\* Every log append and Git commit is an indivisible durable step. The lock is
\* an OS lock: a crashed process loses it, while the journal/Git/files survive.
CONSTANTS Clients, Budget, BadEvidence, BadCommitRetry
ASSUME /\ Cardinality(Clients) = 2
       /\ Budget \in 2..3
       /\ BadEvidence \in BOOLEAN
       /\ BadCommitRetry \in BOOLEAN

E(kind, source, file, evaluator, head) ==
  [kind |-> kind, source |-> source, file |-> file,
   evaluator |-> evaluator, head |-> head]

VARIABLES log, holders, source, file, saved, evaluator, head, commits,
          aggregating, restored, postCrashCommit
vars == <<log, holders, source, file, saved, evaluator, head, commits,
          aggregating, restored, postCrashCommit>>

Indices(kinds) == {i \in 1..Len(log) : log[i].kind \in kinds}
MaxIndex(S) == CHOOSE i \in S : \A j \in S : j <= i
Last(kinds) ==
  IF Indices(kinds) = {} THEN E("none", "none", "none", "none", "none")
  ELSE log[MaxIndex(Indices(kinds))]
Starts == Cardinality(Indices({"start"}))
Intent == Last({"intent"})
OpenIntent == /\ Intent.kind = "intent"
              /\ Last({"intent", "cancel", "resolved"}).kind = "intent"
Begun == Indices({"begin"}) # {}
Intents == Cardinality(Indices({"intent"}))
Resolved == Last({"resolved"}).kind = "resolved"
LatestAttempt == Last({"start", "attempt-ok", "attempt-good",
                      "attempt-flat", "attempt-fail", "aggregate"})
CandidateAttempt ==
  MaxIndex(Indices({"start", "attempt-ok", "attempt-good",
                    "attempt-flat", "attempt-fail", "aggregate"}))
    > MaxIndex(Indices({"begin"}))
Evidence == Last({"aggregate"})
Accepted == Last({"baseline", "resolved"})
Keep == Intent.evaluator = "keep"
MatchingIntent == /\ source = Intent.source
                  /\ file = Intent.file
                  /\ evaluator = "trusted"
Base == "h0"
Ready == holders # {}

Init ==
  /\ log = <<E("start", "s0", "none", "trusted", Base),
             E("attempt-ok", "s0", "none", "trusted", Base),
             E("baseline", "s0", "none", "trusted", Base)>>
  /\ holders = {}
  /\ source = "s0" /\ file = "none" /\ saved = "none"
  /\ evaluator = "trusted" /\ head = Base /\ commits = 0
  /\ aggregating = "idle" /\ restored = FALSE
  /\ postCrashCommit = FALSE

Acquire(c) ==
  /\ c \in Clients /\ holders = {}
  /\ holders' = {c}
  /\ UNCHANGED <<log, source, file, saved, evaluator, head, commits,
                 aggregating, restored>>
Release(c) ==
  /\ holders = {c}
  /\ ~OpenIntent /\ LatestAttempt.kind # "start" /\ aggregating = "idle"
  /\ holders' = {}
  /\ aggregating' = "idle"
  /\ UNCHANGED <<log, source, file, saved, evaluator, head, commits, restored>>
Crash(c) ==
  /\ holders = {c}
  /\ holders' = {} /\ aggregating' = "idle"
  /\ postCrashCommit' = OpenIntent /\ head = "h1"
  /\ UNCHANGED <<log, source, file, saved, evaluator, head, commits, restored>>

Begin ==
  /\ Ready /\ ~Begun /\ head = Base /\ evaluator = "trusted"
  /\ log' = Append(log, E("begin", "s0", "none", "trusted", Base))
  /\ UNCHANGED <<holders, source, file, saved, evaluator, head, commits,
                 aggregating, restored>>
Edit(s) ==
  /\ Begun /\ ~Resolved /\ s \in {"s0", "s1", "s2"}
  /\ s # source /\ source' = s
  /\ UNCHANGED <<log, holders, file, saved, evaluator, head, commits,
                 aggregating, restored>>
NewFile(b) ==
  /\ Begun /\ ~Resolved /\ b \in {"none", "b1", "b2"}
  /\ b # file /\ file' = b
  /\ UNCHANGED <<log, holders, source, saved, evaluator, head, commits,
                 aggregating, restored>>
Drift ==
  /\ Begun /\ ~Resolved /\ evaluator = "trusted"
  /\ evaluator' = "drift"
  /\ UNCHANGED <<log, holders, source, file, saved, head, commits,
                 aggregating, restored>>
RestoreEvaluator ==
  /\ evaluator = "drift" /\ evaluator' = "trusted"
  /\ UNCHANGED <<log, holders, source, file, saved, head, commits,
                 aggregating, restored>>

StartRun ==
  /\ Ready /\ Begun /\ ~OpenIntent /\ ~Resolved
  /\ Starts < Budget /\ evaluator = "trusted" /\ head = Base
  /\ LatestAttempt.kind # "start"
  /\ log' = Append(log, E("start", source, file, evaluator, head))
  /\ aggregating' = "running"
  /\ UNCHANGED <<holders, source, file, saved, evaluator, head, commits, restored>>
FinishRun(outcome) ==
  /\ Ready /\ LatestAttempt.kind = "start" /\ aggregating = "running"
  /\ outcome \in {"good", "flat", "fail"}
  /\ log' = Append(log,
       E(IF evaluator = "drift" \/ outcome = "fail" THEN "attempt-fail"
         ELSE IF outcome = "good" THEN "attempt-good" ELSE "attempt-flat",
         LatestAttempt.source, LatestAttempt.file,
         evaluator, head))
  /\ aggregating' = (IF outcome # "fail" /\ evaluator = "trusted"
                    THEN "ready" ELSE "idle")
  /\ UNCHANGED <<holders, source, file, saved, evaluator, head, commits, restored>>
Aggregate ==
  /\ Ready /\ aggregating = "ready"
  /\ LatestAttempt.kind \in {"attempt-good", "attempt-flat"}
  /\ log' = Append(log, E("aggregate", LatestAttempt.source,
                          LatestAttempt.file,
                          IF LatestAttempt.kind = "attempt-good"
                          THEN "improved" ELSE "flat", head))
  /\ aggregating' = "idle"
  /\ UNCHANGED <<holders, source, file, saved, evaluator, head, commits, restored>>
\* A crash after start leaves the budget reservation in the log. Recovery
\* writes a failed attempt but never a second start for the same reservation.
RecoverRun ==
  /\ Ready /\ LatestAttempt.kind = "start" /\ aggregating = "idle"
  \* Recovery's attempt record has no source fingerprint: it is not evidence.
  /\ log' = Append(log, E("attempt-fail", "unknown",
                          "none", "interrupted", head))
  /\ aggregating' = "idle"
  /\ UNCHANGED <<holders, source, file, saved, evaluator, head, commits, restored>>

DecideKeep ==
  /\ Ready /\ Begun /\ ~OpenIntent /\ ~Resolved /\ head = Base
  /\ Intents < 2
  /\ (source # "s0" \/ file # "none")
  /\ evaluator = "trusted"
  /\ IF BadEvidence THEN TRUE
     ELSE /\ LatestAttempt.kind = "aggregate"
          /\ Evidence.source = source /\ Evidence.file = file
          /\ Evidence.evaluator = "improved"
  /\ log' = Append(log, E("intent", source, file, "keep", head))
  /\ UNCHANGED <<holders, source, file, saved, evaluator, head, commits,
                 aggregating, restored>>
DecideDiscard ==
  /\ Ready /\ Begun /\ ~OpenIntent /\ ~Resolved /\ head = Base
  /\ Intents < 2
  /\ evaluator = "trusted"
  /\ LatestAttempt.kind # "start"
  /\ IF CandidateAttempt /\ LatestAttempt.source # "unknown"
     THEN /\ source = LatestAttempt.source /\ file = LatestAttempt.file
     ELSE TRUE
  /\ log' = Append(log, E("intent", source, file, "discard", head))
  /\ UNCHANGED <<holders, source, file, saved, evaluator, head, commits,
                 aggregating, restored>>

\* A hook can refuse before Git changes HEAD; only then cancel the intent.
HookFailure ==
  /\ Ready /\ OpenIntent /\ Keep /\ head = Base
  /\ log' = Append(log, E("cancel", Intent.source, Intent.file, "keep", head))
  /\ UNCHANGED <<holders, source, file, saved, evaluator, head, commits,
                 aggregating, restored>>
Commit ==
  /\ Ready /\ OpenIntent /\ Keep /\ MatchingIntent
  /\ (head = Base \/ (BadCommitRetry /\ postCrashCommit /\ head = "h1"))
  /\ commits < 2
  /\ head' = IF head = Base THEN "h1" ELSE "h2"
  /\ commits' = commits + 1
  /\ UNCHANGED <<log, holders, source, file, saved, evaluator,
                 aggregating, restored>>
\* Untracked bytes are moved, never removed; replay accepts a matching backup.
MoveNew ==
  /\ Ready /\ OpenIntent /\ ~Keep /\ file # "none"
  /\ file = Intent.file /\ saved = "none"
  /\ saved' = file /\ file' = "none"
  /\ UNCHANGED <<log, holders, source, evaluator, head, commits,
                 aggregating, restored>>
RestoreTracked ==
  /\ Ready /\ OpenIntent /\ ~Keep /\ head = Base
  /\ (file = "none" \/ file = Intent.file)
  /\ (Intent.file = "none" \/ saved = Intent.file)
  /\ (source = Intent.source \/ source = "s0")
  /\ source' = "s0" /\ restored' = TRUE
  /\ UNCHANGED <<log, holders, file, saved, evaluator, head, commits, aggregating>>
RecordApplied ==
  /\ Ready /\ OpenIntent /\ Last({"applied"}).kind # "applied"
  /\ IF Keep THEN /\ head # Base /\ head \in {"h1", "h2"}
               /\ MatchingIntent
               ELSE /\ restored /\ source = "s0"
                    /\ file = "none"
                    /\ (Intent.file = "none" \/ saved = Intent.file)
  /\ log' = Append(log, E("applied", Intent.source, Intent.file,
                          Intent.evaluator, head))
  /\ UNCHANGED <<holders, source, file, saved, evaluator, head, commits,
                 aggregating, restored>>
Resolve ==
  /\ Ready /\ OpenIntent /\ Last({"applied"}).kind = "applied"
  /\ evaluator = "trusted"
  /\ IF Keep THEN MatchingIntent
     ELSE /\ source = "s0" /\ file = "none"
          /\ (Intent.file = "none" \/ saved = Intent.file)
  /\ log' = Append(log, E("resolved", Intent.source, Intent.file,
                          Intent.evaluator, head))
  /\ UNCHANGED <<holders, source, file, saved, evaluator, head, commits,
                 aggregating, restored>>

NonCrashNext ==
  \/ \E c \in Clients : Acquire(c) \/ Release(c)
  \/ Begin \/ \E s \in {"s0", "s1", "s2"} : Edit(s)
  \/ \E b \in {"none", "b1", "b2"} : NewFile(b)
  \/ Drift \/ RestoreEvaluator \/ StartRun
  \/ \E outcome \in {"good", "flat", "fail"} : FinishRun(outcome)
  \/ Aggregate \/ RecoverRun \/ DecideKeep \/ DecideDiscard
  \/ HookFailure \/ Commit \/ MoveNew \/ RestoreTracked \/ RecordApplied \/ Resolve
Next == (NonCrashNext /\ UNCHANGED postCrashCommit)
        \/ \E c \in Clients : Crash(c)
Spec == Init /\ [][Next]_vars

TypeOK ==
  /\ log \in Seq({E(k,s,f,e,h) :
       k \in {"start","attempt-ok","attempt-good","attempt-flat",
              "attempt-fail","baseline","begin",
              "aggregate","intent","cancel","applied","resolved"},
       s \in {"s0","s1","s2","unknown"}, f \in {"none","b1","b2"},
       e \in {"trusted","drift","interrupted","keep","discard",
              "improved","flat"},
       h \in {Base,"h1","h2"}})
  /\ holders \subseteq Clients /\ source \in {"s0","s1","s2"}
  /\ file \in {"none","b1","b2"} /\ saved \in {"none","b1","b2"}
  /\ evaluator \in {"trusted","drift"} /\ head \in {Base,"h1","h2"}
  /\ commits \in 0..2
  /\ aggregating \in {"idle", "running", "ready"}
  /\ restored \in BOOLEAN
  /\ postCrashCommit \in BOOLEAN
Exclusive == Cardinality(holders) <= 1
BudgetSafe == Starts <= Budget
CommitOnce == commits <= 1
EvidenceSafe ==
  OpenIntent /\ Keep =>
    /\ Evidence.kind = "aggregate" /\ Evidence.source = Intent.source
    /\ Evidence.file = Intent.file /\ Evidence.evaluator = "improved"
AcceptedSafe ==
  Resolved /\ Last({"resolved"}).evaluator = "keep" =>
    /\ Evidence.kind = "aggregate" /\ Evidence.evaluator = "improved"
    /\ Evidence.source = Last({"resolved"}).source
    /\ Evidence.file = Last({"resolved"}).file
    /\ head = Last({"resolved"}).head
OwnedNewFile ==
  OpenIntent /\ ~Keep /\ Intent.file # "none" /\ saved # "none"
    => saved = Intent.file
Reconciled == head = Accepted.head \/ OpenIntent
ResolvedDiscardPreserves ==
  Resolved /\ Last({"resolved"}).evaluator = "discard"
    /\ Last({"resolved"}).file # "none"
    => saved = Last({"resolved"}).file
================================================================================
