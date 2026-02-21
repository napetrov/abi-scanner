#!/bin/bash
# abi_tracker/compare_all_versions.sh
# Compare ALL oneDAL 2025.x versions sequentially

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${WORKSPACE:-/workspace/abi_tracker_workspace}"

BASELINES_DIR="${WORKSPACE}/baselines/dal"
API_DIR="${WORKSPACE}/public_api/dal"
REPORTS_DIR="${WORKSPACE}/reports/dal"
SUPPRESSIONS="${SCRIPT_DIR}/suppressions/onedal.txt"

mkdir -p "$REPORTS_DIR"

# Get sorted list of all versions
VERSIONS=($(ls ${BASELINES_DIR}/dal_*.abi | sort -V | sed 's/.*dal_\(.*\)\.abi/\1/'))

echo "==================================================="
echo "Comparing ALL oneDAL 2025.x versions"
echo "Found ${#VERSIONS[@]} versions"
echo "==================================================="
echo ""

for ((i=0; i<${#VERSIONS[@]}-1; i++)); do
    OLD="${VERSIONS[$i]}"
    NEW="${VERSIONS[$((i+1))]}"
    
    OLD_ABI="${BASELINES_DIR}/dal_${OLD}.abi"
    NEW_ABI="${BASELINES_DIR}/dal_${NEW}.abi"
    OLD_API="${API_DIR}/${OLD}_public_api.json"
    NEW_API="${API_DIR}/${NEW}_public_api.json"
    REPORT="${REPORTS_DIR}/${OLD}_to_${NEW}.json"
    
    echo ">>> Comparing $OLD → $NEW <<<"
    
    if [ ! -f "$OLD_ABI" ] || [ ! -f "$NEW_ABI" ]; then
        echo "⚠️  Missing baselines, skipping"
        continue
    fi
    
    # For APT versions without public API JSON, use empty
    [ ! -f "$OLD_API" ] && OLD_API="/dev/null"
    [ ! -f "$NEW_API" ] && NEW_API="/dev/null"
    
    # Run comparison
    python3 "${SCRIPT_DIR}/scripts/compare_abi.py" \
        "$OLD_ABI" \
        "$NEW_ABI" \
        "$OLD_API" \
        "$NEW_API" \
        "$SUPPRESSIONS" > "$REPORT" 2>/dev/null || {
        echo "⚠️  Comparison failed, trying without public API..."
        # Fallback: just run abidiff
        abidiff "$SUPPRESSIONS" "$OLD_ABI" "$NEW_ABI" > "${REPORT}.txt" 2>&1 || true
        EXIT_CODE=$?
        echo "{\"comparison\": \"$OLD → $NEW\", \"exit_code\": $EXIT_CODE, \"raw_output\": \"${REPORT}.txt\"}" > "$REPORT"
    }
    
    # Display summary
    echo "Report saved: $REPORT"
    python3 << PYEOF 2>/dev/null || echo "  (see ${REPORT})"
import json
try:
    with open('$REPORT') as f:
        data = json.load(f)
    print(f"  Verdict: {data.get('verdict', 'N/A')} (exit {data.get('exit_code', '?')})")
    if 'changes' in data:
        print(f"  Public changes: +{data['changes']['public']['added']} -{data['changes']['public']['removed']}")
        print(f"  Private changes: +{data['changes']['private']['added']} -{data['changes']['private']['removed']}")
except:
    pass
PYEOF
    
    echo ""
done

echo "==================================================="
echo "✓ All comparisons complete"
echo "Reports in: $REPORTS_DIR"
ls -lh "$REPORTS_DIR"/*.json | wc -l
echo "==================================================="
