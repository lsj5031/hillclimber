#!/bin/sh
# Complete finite checks, including two deliberately broken configurations.
set -eu
cd "$(dirname "$0")"
base="../scratch/formal"
mkdir -p "$base"
# A stopped wrapper can leave its Java child alive. Never share TLC metadata
# or logs with another invocation, even if a prior run was interrupted.
out=$(mktemp -d "$base/run.XXXXXXXX")
echo "Logs: $out"
export JAVA_TOOL_OPTIONS="-Xmx2048m"
for module in Workflow Recovery; do
    /Users/liu/.local/bin/sany "$module.tla" > "$out/$module.sany.log" 2>&1
    if rg -q 'Semantic errors:|Parse Error|Fatal errors' "$out/$module.sany.log"; then
        echo "SANY failed: $module" >&2
        exit 1
    fi
done
for case in Workflow Recovery BadEvidence BadCommitRetry; do
    mkdir -p "$out/$case"
    module=Workflow
    [ "$case" = Recovery ] && module=Recovery
    if /Users/liu/.local/bin/tlc -workers 2 -fpmem 0.1 \
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
