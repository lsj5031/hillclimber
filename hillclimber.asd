(asdf:defsystem "hillclimber"
  :depends-on ("yason" "sb-posix")
  :serial t
  :components ((:file "package") (:file "core") (:file "process") (:file "workflow") (:file "cli"))
  :build-operation "program-op"
  :build-pathname "build/hillclimber"
  :entry-point "hillclimber:main"
  :in-order-to ((asdf:test-op (asdf:test-op "hillclimber/tests"))))

(asdf:defsystem "hillclimber/tests"
  :depends-on ("hillclimber")
  :components ((:file "tests"))
  :perform (asdf:test-op (o c) (declare (ignore o c)) (uiop:symbol-call :hillclimber :test-core)))
