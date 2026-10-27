(in-package :hillclimber)

(defparameter *quickstart*
"One-time setup (in a NEW disposable or dedicated clean Git worktree):
  mkdir -p demo/src && cd demo && git init
  echo slow > src/value
  echo '#!/bin/sh' > bench.sh
  echo 'if grep -q fast src/value; then echo METRIC elapsed_ms=5; else echo METRIC elapsed_ms=10; fi' >> bench.sh
  echo '#!/bin/sh' > checks.sh
  echo 'test -s src/value' >> checks.sh
  git add src bench.sh checks.sh && git commit -m 'Set up experiment'
  hillclimber init --name Demo --metric elapsed_ms --direction lower --unit ms --scope src --max-runs 12 --benchmark bench.sh --check checks.sh
  hillclimber run --baseline --repeat 3

Each experiment (caller edits; hillclimber measures and decides):
  hillclimber begin --hypothesis 'Try fast value'
  echo fast > src/value
  hillclimber run --repeat 3 --timeout 120
  hillclimber decide keep --reason 'Lower median; checks passed'
  hillclimber begin --hypothesis 'Try slow again'
  echo slow > src/value
  hillclimber run
  hillclimber decide discard --reason 'Regression'
  hillclimber status --context --json
")
(defparameter *intro*
"hillclimber measures benchmark scripts, records evidence, and applies Git decisions.
You supply hypotheses and source edits; it does not supervise or edit your code.

Sequence: init -> run --baseline -> begin -> edit -> run -> decide -> repeat.
Use status to resume; recover after an interrupted run or decision.

")
(defparameter *common*
"Scripts run with /bin/sh from the project root. Print METRIC name=finite_decimal
(e.g. METRIC elapsed_ms=-1.2e3). Last duplicate wins. Names: letters,
digits, _, ., -, µ, μ. Units are labels, never conversion factors.
Decimal scores must be representable as finite double floats; nonzero values
that underflow to zero are rejected.
Only --scope paths may change. Benchmark, checks and --input paths are protected.
Do not edit between measurement and keep or manually commit/reset while pending.
hillclimber owns keep/discard, not your scripts. State/logs: .auto/ in project.
Use status --context --json to discover state; never guess or reinitialize.
--project PATH (default cwd) chooses the exact worktree root. --json returns one
versioned object on stdout, including help/errors; no interactive prompts.
Malformed option tokens fail first; otherwise --help wins over --version and
both precede repository/state checks. Help and version never mutate files.
Exit: 0 success/help; 2 arguments; 3 precondition; 4 failed measurement;
5 Git/storage/internal; 130 interrupt. See COMMAND --help for exact options.
")
(defparameter *help*
  (list
   (cons "init" "init --name TEXT --metric NAME --direction lower|higher --scope PATH [--scope PATH ...] --max-runs N --benchmark PATH [--check PATH] [--input PATH ...] [--unit LABEL] [--tolerance DECIMAL]
Requires clean dedicated Git worktree, existing scope and committed evaluator files.
Creates .auto templates, session and journal; merges .auto/ into local Git exclude.
No overwrite. Each benchmark invocation (including failures) costs one run.
Defaults: unit=unit, tolerance=0 (absolute, strict improvement).
Example: hillclimber init --name Demo --metric elapsed_ms --direction lower --scope src --max-runs 12 --benchmark bench.sh
Exit: 0, 2 invalid, 3 dirty/existing session, 5 Git/storage.")
   (cons "run" "run [--baseline] [--repeat N] [--timeout SECONDS]
Baseline requires clean source and no earlier baseline. Candidate run requires begin.
Defaults: repeat=1, timeout=120 seconds per benchmark/check.
Each invocation consumes one budget even on failure/interrupt; no implicit retry.
Stores bounded (65536 bytes per stream) logs and score or null; checks must pass.
Failed runs exit 4; retry run or discard. Baseline must pass before begin.
Example: hillclimber run --baseline --repeat 3
Exit: 0, 2 invalid, 3 precondition/budget, 4 measurement, 5 storage.")
   (cons "begin" "begin --hypothesis TEXT
Requires successful baseline, no pending candidate, clean worktree/index and unchanged
branch/evaluator/HEAD. Persists candidate ID and accepted HEAD; makes no code edits.
Example: hillclimber begin --hypothesis 'Try smaller buffer'
Exit: 0, 2 invalid, 3 precondition, 5 Git/storage.")
   (cons "decide" "decide keep|discard --reason TEXT
Requires a pending candidate. Keep requires last passing measurement, unchanged
measured source, passing checks, score strictly better than best by tolerance.
Keep stages only changed scope paths and commits without bypassing Git hooks.
Discard restores tracked scope paths and moves new files to .auto/recovery/ID/.
Intent is journaled first; on interruption use recover, not another decide.
Example: hillclimber decide keep --reason 'Median improved'
Example: hillclimber decide discard --reason 'Regression'
Exit: 0 including discard, 2 invalid, 3 precondition, 5 Git/storage.")
   (cons "status" "status [--history N] [--context]
Read-only committed journal replay: baseline/best, accepted HEAD, pending candidate,
budget, latest result and next action. History defaults to 0; N <= 100.
Works across invocations. Incomplete final journal bytes are diagnosed while
status reads the complete prefix; recover backs up and trims that fragment.
Invalid complete records block status and mutation.
Example: hillclimber status --context --json
Exit: 0, 2 invalid, 3 no session, 5 corruption.")
   (cons "recover" "recover
Requires existing session. Reconciles an interrupted execution or decision.
An incomplete run is marked failed with missing score; budget stays consumed.
Truncated final journal bytes are copied to recovery before repair.
Decision intent is compared against HEAD and recorded source, then completed;
ambiguous drift fails closed. Repeating recover after resolution is harmless.
Example: hillclimber recover
Exit: 0, 3 precondition/drift, 5 ambiguous Git/storage.")))
(defun help-for (command)
  (if command
      (format nil "hillclimber ~a~%~%~a~%~%Global: --project PATH, --json, --help, --version.~%~%~a"
              command (or (cdr (assoc command *help* :test #'equal)) "")
              *common*)
      (format nil "~a~a~%Commands: init, run, begin, decide, status, recover.~%~%~a"
              *intro* *quickstart* *common*)))
(defun parse-args (args)
  (let ((positionals nil) (options nil) (flag-help nil) (flag-json nil) (flag-version nil)
        (project nil))
    (loop while args for word = (pop args)
          do (cond
               ((equal word "--help") (setf flag-help t))
               ((equal word "--json") (setf flag-json t))
               ((equal word "--version") (setf flag-version t))
               ((equal word "--project")
                (unless args (fail "arguments" "--project requires PATH." "See --help." 2))
                (setf project (pop args)))
               ((member word '("--baseline" "--context") :test #'equal)
                (push (cons word t) options))
               ((member word '("--name" "--metric" "--direction" "--scope"
                               "--max-runs" "--benchmark" "--check" "--input"
                               "--unit" "--tolerance" "--repeat" "--timeout"
                               "--hypothesis" "--reason" "--history") :test #'equal)
                (unless args (fail "arguments" (format nil "~a requires a value." word)
                                   "See COMMAND --help." 2))
                (push (cons word (pop args)) options))
               ((and (plusp (length word)) (char= (char word 0) #\-))
                (fail "arguments" (format nil "Unknown option ~a." word) "See --help." 2))
               (t (push word positionals))))
    (values (nreverse positionals) (nreverse options) project flag-json flag-help flag-version)))
(defun allowed-options (command options)
  (let ((valid (cdr (assoc command
                           '(("init" . ("--name" "--metric" "--direction" "--scope" "--max-runs"
                                        "--benchmark" "--check" "--input" "--unit" "--tolerance"))
                             ("run" . ("--baseline" "--repeat" "--timeout"))
                             ("begin" . ("--hypothesis"))
                             ("decide" . ("--reason"))
                             ("status" . ("--history" "--context"))
                             ("recover" . nil)) :test #'equal))))
    (dolist (o options)
      (unless (member (car o) valid :test #'equal)
        (fail "arguments" (format nil "~a is not an option for ~a." (car o) command)
              (format nil "See hillclimber ~a --help." command) 2)))))
(defun status-view (root options)
  (let* ((session (load-session root)) (st (state root t))
         (bytes (journal-bytes root))
         (truncated (< (1+ (journal-prefix bytes)) (length bytes)))
         (actual (git-head root))
         (drift (and (stringp (field st "accepted"))
                     (not (equal actual (field st "accepted")))
                     (eq (field st "intent") :null)))
         (pending (field st "pending")) (attempt (field st "attempt"))
         (n (if (option options "--history")
                (int-option (option options "--history") "--history" 0) 0)))
    (when (> n 100) (fail "arguments" "--history maximum is 100." "Use --history 100." 2))
    (let ((result (obj "project" root "name" (field session "name")
                       "metric" (field session "metric") "direction" (field session "direction")
                       "unit" (field session "unit") "baseline" (field st "baseline")
                       "best" (field st "best") "accepted" (field st "accepted")
                       "actual_head" actual "head_drift" (bool drift)
                       "candidate" pending "last_attempt" attempt
                       "executions" (field st "runs")
                       "candidates" (field st "candidates")
                       "remaining" (- (field session "budget") (field st "runs"))
                       "journal_warning" (if truncated "Incomplete final record; run recover." :null)
                       "next" (cond
                                (truncated "recover")
                                (drift "resolve HEAD drift manually")
                                ((not (eq (field st "intent") :null)) "recover")
                                ((and (hash-table-p attempt)
                                      (equal (field attempt "type") "attempt-start")) "recover")
                                ((eq (field st "baseline") :null) "run --baseline")
                                ((not (eq pending :null)) "run or decide")
                                (t "begin --hypothesis")))))
      (when (option options "--context")
        (setf (gethash "context" result)
              (obj "hypothesis" (if (eq pending :null) :null (field pending "hypothesis"))
                   "scope" (field session "scope") "protected" (field session "protected")
                   "tolerance" (field session "tolerance")
                   "prompt" (uiop:read-file-string (path root ".auto/prompt.md")))))
      (when (plusp n)
        (let* ((history (coerce (field st "history") 'list))
               (last (last history (min n (length history)))))
          (setf (gethash "history" result) (arr last))))
      result)))
(defun dispatch (positionals options project)
  (let ((command (first positionals)))
    (unless (assoc command *help* :test #'equal)
      (fail "arguments" "Expected one of: init, run, begin, decide, status, recover."
            "Use hillclimber --help." 2))
    (unless (= (length positionals) (if (equal command "decide") 2 1))
      (fail "arguments" "Unexpected or missing positional arguments."
            (format nil "See hillclimber ~a --help." command) 2))
    (allowed-options command options)
    (let ((root (root-path (or project (uiop:getcwd)))))
      (if (equal command "init")
          (initialize root options)
          (if (equal command "status")
              (status-view root options)
              (progn
                (load-session root)
                (with-session-lock
                  root (lambda ()
                         (cond
                           ((equal command "begin")
                            (begin-candidate root (option options "--hypothesis")))
                           ((equal command "run")
                            (measure root (option options "--baseline")
                                     (int-option (option options "--repeat" "1") "--repeat")
                                     (int-option (option options "--timeout" "120") "--timeout")))
                           ((equal command "decide")
                            (decision root (second positionals) (option options "--reason")))
                           ((equal command "recover") (recover-session root)))))))))))
(defun response (kind payload)
  (obj "v" 1 "kind" kind "data" payload))
(defun print-result (data)
  (if (gethash "remaining" data)
      (format t "Session: ~a~%Baseline: ~a  Best: ~a ~a~%Accepted: ~a~%Candidate: ~a~%Executions: ~d  Remaining: ~d~%Next: ~a~%"
              (field data "name")
              (field (field data "baseline") "score" "none")
              (field data "best") (field data "unit")
              (field data "accepted") (field (field data "candidate") "id" "none")
              (field data "executions") (field data "remaining") (field data "next"))
      (loop for key being the hash-keys of data using (hash-value value)
            do (format t "~a: ~a~%" key
                       (if (eq value :null) "none" value)))))
(defun main ()
  (let ((json-mode (member "--json" (uiop:command-line-arguments) :test #'equal))
        (exit-code 0))
    (catch 'user-interrupt
      (handler-bind ((sb-sys:interactive-interrupt
                       (lambda (e) (declare (ignore e))
                         (setf exit-code 130)
                         (throw 'user-interrupt nil))))
      (handler-case
        (multiple-value-bind (positionals options project j help version)
            (parse-args (uiop:command-line-arguments))
          (setf json-mode j)
          (let* ((cmd (first positionals))
                 (result (cond
                           (help (response "help" (obj "command" (or cmd :null)
                                                       "text" (help-for (and (assoc cmd *help* :test #'equal) cmd)))))
                           (version (response "version" (obj "version" "0.1.0" "sbcl" (lisp-implementation-version))))
                           (t (response "result" (dispatch positionals options project))))))
            (if json-mode (write-line (json result))
                (if (equal (field result "kind") "help")
                    (write-line (field (field result "data") "text"))
                    (if (equal (field result "kind") "result")
                        (print-result (field result "data"))
                        (format t "~a~%" (json (field result "data"))))))))
      (cli-error (e)
        (setf exit-code (err-exit e))
        (let ((payload (obj "code" (err-code e) "message" (err-message e) "next" (err-next e))))
          (if json-mode
              (write-line (json (response "error" payload)))
              (format *error-output* "~a: ~a~%Next: ~a~%" (err-code e) (err-message e) (err-next e)))))
      (error (e)
        (setf exit-code 5)
        (if json-mode
            (write-line (json (response "error" (obj "code" "internal"
                                                    "message" (princ-to-string e)
                                                    "next" "Inspect the session and run recover if a decision is pending."))))
            (format *error-output* "internal: ~a~%" e))))))
    (when (= exit-code 130)
      (let ((payload (obj "code" "interrupted"
                          "message" "Interrupted; any started execution consumed budget."
                          "next" "Run recover, then inspect status and logs.")))
        (if json-mode
            (write-line (json (response "error" payload)))
            (format *error-output* "interrupted: ~a~%Next: ~a~%"
                    (field payload "message") (field payload "next")))))
    (finish-output) (finish-output *error-output*)
    (sb-ext:exit :code exit-code)))
