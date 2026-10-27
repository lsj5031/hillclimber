# Attribution and third-party notices

Hillclimber adapts the experiment/measure/keep-or-discard mechanism from
[pi-autoresearch](https://github.com/davebcn87/pi-autoresearch), by Tobi Lütke
and David Cortés, into a standalone Common Lisp CLI. The caller supplies
hypotheses and edits; the CLI owns measurements, evidence and scoped Git
decisions. It does not require pi or an agent runtime.

Reference revision: 04b8a50dac7efe80ffc91648bd00ed9b022e24c2.
The upstream MIT notice is retained below for attribution to that mechanism.

## pi-autoresearch — MIT

MIT License

Copyright (c) 2026 Tobi Lutke, David Cortés

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Build and runtime dependencies

See DEPENDENCIES.md for exact source pins and dependency license locations.
Dependencies are fetched separately, not vendored in this source tree.
Redistributed executables include Lisp dependency code and must carry the
applicable dependency license notices, LICENSE and this file.
This source preview does not distribute executables.
