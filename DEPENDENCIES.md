# Pinned build inventory (macOS arm64)

Runtime does not fetch packages or require Quicklisp, Python, Node, or an agent.
Build-time sources are checked out under `.deps/` by `bootstrap.sh` at these
exact revisions. `build.lisp` uses only those paths. Verify with
`git -C .deps/NAME rev-parse HEAD` before building.

| Source | Revision | License |
| --- | --- | --- |
| SBCL + bundled ASDF/UIOP, SB-POSIX | Homebrew SBCL 2.6.9 | SBCL public domain/BSD portions; ASDF MIT |
| [yason](https://github.com/phmarek/yason) | `ea16bc5c5ad099322bffc77686f6e9a67e68a6c1` | BSD-style, see `.deps/yason/LICENSE` |
| [alexandria](https://gitlab.common-lisp.net/alexandria/alexandria) | `f283e25efbe9f4323419a138b22ad2fc027f6641` | public domain / 0-clause MIT fallback, `.deps/alexandria/LICENCE` |
| [trivial-gray-streams](https://github.com/trivial-gray-streams/trivial-gray-streams) | `257d73ec36958beb7d49eba5567d5409827197b7` | MIT, `.deps/trivial-gray-streams/COPYING` |

Yason depends on Alexandria and trivial-gray-streams. No clingon: its
transitive dependency surface is disproportionate to six commands, so the CLI
uses a small explicit option table. Git and `/bin/sh` are runtime requirements.
The executable contains the pinned Lisp library code; retain the dependency
license texts alongside redistributed binaries. The behavior is a fresh
implementation, not a translation of upstream TypeScript; workflow inspiration:
`davebcn87/pi-autoresearch` at
`04b8a50dac7efe80ffc91648bd00ed9b022e24c2` (MIT). No upstream assets
are copied.
