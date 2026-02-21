#!/bin/bash
# abi_tracker/compare_versions.sh
# Compare all 2025.x versions sequentially

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${WORKSPACE:-/workspace/abi_tracker_workspace}"

BASELINES_DIR="${WORKSPACE}/baselines/dal"
API_DIR="${WORKSPACE}/public_api/dal"
REPORTS_DIR="${WORKSPACE}/reports/dal"
SUPPRESSIONS="${SCRIPT_DIR}/suppressions/onedal.txt"

mkdir -p "$REPORTS_DIR"

# Get sorted list of versions
VERSIONS=($(ls ${BASELINES_DIR}/dal_*.abi | sort -V | sed 's/.*dal_\(.*\)\.abi/\1/'))

echo "==================================================="
echo "Comparing oneDAL 2025.x versions"
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
    
    # Run comparison
    python3 "${SCRIPT_DIR}/scripts/compare_abi.py" \
        "$OLD_ABI" \
        "$NEW_ABI" \
        "$OLD_API" \
        "$NEW_API" \
        "$SUPPRESSIONS" > "$REPORT"
    
    # Display summary
    echo "Report saved: $REPORT"
    python3 << PYEOF
import json
with open('$REPORT') as f:
    data = json.load(f)
print(f"  Verdict: {data['verdict']} (exit {data['exit_code']})")
print(f"  Public changes: +{data['changes']['public']['added']} -{data['changes']['public']['removed']}")
print(f"  Private changes: +{data['changes']['private']['added']} -{data['changes']['private']['removed']}")
PYEOF
    
    echo ""
done

echo "==================================================="
echo "✓ All comparisons complete"
echo "Reports in: $REPORTS_DIR"
echo "==================================================="
