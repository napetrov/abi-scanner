#!/bin/bash
# abi_tracker/compare_all.sh
# Compare all versions sequentially and generate reports

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${SCRIPT_DIR}/../workspace"
BASELINES="${WORKSPACE}/baselines"
REPORTS="${WORKSPACE}/reports"
SUPPRESSIONS="${SCRIPT_DIR}/suppressions"

LIBRARY="${1:-onedal}"
SOURCE="${2:-apt}"

BASELINE_DIR="${BASELINES}/${LIBRARY}/${SOURCE}"
REPORT_DIR="${REPORTS}/${LIBRARY}/${SOURCE}"

mkdir -p "${REPORT_DIR}"

# Find suppression file
SUPPRESSION_FILE="${SUPPRESSIONS}/${LIBRARY}.txt"
SUPPRESSION_ARGS=""
if [ -f "$SUPPRESSION_FILE" ]; then
    echo "Using suppressions: $SUPPRESSION_FILE"
    SUPPRESSION_ARGS="--suppressions $SUPPRESSION_FILE"
fi

echo "Comparing ABI for ${LIBRARY} (source: ${SOURCE})..."
echo ""

# Get sorted list of versions
VERSIONS=($(ls "${BASELINE_DIR}"/*.abi | sort -V | xargs -n1 basename | sed 's/.*_\(2025\.[0-9]*\)\.abi/\1/'))

TOTAL=${#VERSIONS[@]}

for ((i=0; i<$TOTAL-1; i++)); do
    OLD="${VERSIONS[$i]}"
    NEW="${VERSIONS[$((i+1))]}"
    
    OLD_ABI="${BASELINE_DIR}/${LIBRARY}_${OLD}.abi"
    NEW_ABI="${BASELINE_DIR}/${LIBRARY}_${NEW}.abi"
    REPORT_FILE="${REPORT_DIR}/${OLD}_to_${NEW}.txt"
    
    echo "========================================"
    echo "$OLD → $NEW"
    echo "========================================"
    
    # Run abidiff with suppressions
    abidiff $SUPPRESSION_ARGS "$OLD_ABI" "$NEW_ABI" > "$REPORT_FILE" 2>&1 || true
    EXIT_CODE=$?
    
    # Parse summary
    SUMMARY=$(head -4 "$REPORT_FILE")
    echo "$SUMMARY"
    echo ""
    echo "Exit code: $EXIT_CODE"
    
    case $EXIT_CODE in
        0) echo "✅ No ABI changes" ;;
        4) echo "✅ Compatible changes (additions only)" ;;
        8) echo "⚠️  Incompatible changes detected" ;;
        12) echo "❌ BREAKING changes (symbols removed/changed)" ;;
        *) echo "? Unknown exit code" ;;
    esac
    
    echo "Report: $REPORT_FILE"
    echo ""
done

echo "All comparisons complete. Reports in: $REPORT_DIR"
