(require :asdf)
(let ((root (uiop:pathname-directory-pathname *load-pathname*)))
  (asdf:initialize-output-translations
   `(:output-translations
     (t (:function
         (lambda (source matching)
           (declare (ignore matching))
           (merge-pathnames (subseq (namestring source) 1)
                            ,(merge-pathnames "build/cache/" root)))))
                          :ignore-inherited-configuration))
  (dolist (name '(".deps/alexandria/" ".deps/trivial-gray-streams/" ".deps/yason/" ""))
    (push (merge-pathnames name root) asdf:*central-registry*))
  (asdf:load-system "hillclimber")
  (asdf:test-system "hillclimber")
  (asdf:make "hillclimber"))
