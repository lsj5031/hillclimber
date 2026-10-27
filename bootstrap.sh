#!/bin/sh
set -eu
cd "$(dirname "$0")"
mkdir -p .deps build scratch
[ "$(sbcl --version)" = "SBCL 2.6.9" ] || {
  echo "Build requires pinned SBCL 2.6.9" >&2
  exit 1
}
fetch() {
  name=$1 url=$2 revision=$3
  if [ ! -d ".deps/$name/.git" ]; then
    git clone -q "$url" ".deps/$name"
  fi
  if [ -n "$(git -C ".deps/$name" status --porcelain)" ]; then
    echo "Dirty dependency, refusing to change or build it: $name" >&2
    exit 1
  fi
  actual=$(git -C ".deps/$name" rev-parse HEAD)
  if [ "$actual" != "$revision" ]; then
    git -C ".deps/$name" checkout -q --detach "$revision"
  fi
  actual=$(git -C ".deps/$name" rev-parse HEAD)
  [ "$actual" = "$revision" ] || { echo "Unpinned dependency: $name" >&2; exit 1; }
}
fetch yason https://github.com/phmarek/yason.git ea16bc5c5ad099322bffc77686f6e9a67e68a6c1
fetch alexandria https://gitlab.common-lisp.net/alexandria/alexandria.git f283e25efbe9f4323419a138b22ad2fc027f6641
fetch trivial-gray-streams https://github.com/trivial-gray-streams/trivial-gray-streams.git 257d73ec36958beb7d49eba5567d5409827197b7
sbcl --no-userinit --no-sysinit --non-interactive --load build.lisp
