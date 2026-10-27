#!/bin/sh
# Complete finite checks, including two deliberately broken configurations.
set -eu
cd "$(dirname "$0")"
# Launchers must use TLA+ 1.7.4 with Java 21; see README.md.
SANY=${SANY:-sany}
TLC=${TLC:-tlc}
for tool in "$SANY" "$TLC" rg; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "Required tool not found: $tool (see formal/README.md)" >&2
        exit 1
    }
done
base="../scratch/formal"
mkdir -p "$base"
# A stopped wrapper can leave its Java child alive. Never share TLC metadata
# or logs with another invocation, even if a prior run was interrupted.
out=$(mktemp -d "$base/run.XXXXXXXX")
echo "Logs: $out"
export JAVA_TOOL_OPTIONS="-Xmx2048m"
for module in Workflow Recovery; do
    "$SANY" "$module.tla" > "$out/$module.sany.log" 2>&1
    if rg -q 'Semantic errors:|Parse Error|Fatal errors' "$out/$module.sany.log"; then
        echo "SANY failed: $module" >&2
        exit 1
    fi
done
for case in Workflow Recovery BadEvidence BadCommitRetry; do
    mkdir -p "$out/$case"
    module=Workflow
    [ "$case" = Recovery ] && module=Recovery
    if "$TLC" -workers 2 -fpmem 0.1 \
        -metadir "$out/$case" -config "$case.cfg" "$module.tla" \
        > "$out/$case.log" 2>&1; then
        if [ "$case" = BadEvidence ] || [ "$case" = BadCommitRetry ]; then
            echo "Missing expected counterexample: $case" >&2
            exit 1
        fi
        rg -q 'Model checking completed. No error has been found.' "$out/$case.log"
    else
        if [ "$case" = BadEvidence ]; then
            rg -q 'Invariant EvidenceSafe is violated.' "$out/$case.log"
        elif [ "$case" = BadCommitRetry ]; then
            rg -q 'Invariant CommitOnce is violated.' "$out/$case.log"
            rg -q '<Crash line' "$out/$case.log"
        else
            echo "Unexpected TLC failure: $case" >&2
            exit 1
        fi
    fi
    echo "$case: $(rg 'states generated, .*distinct states found|Finished in ' "$out/$case.log" | tr '\n' ' ')"
done
