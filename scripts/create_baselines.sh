#!/bin/bash
# abi_tracker/create_baselines.sh
# Create ABI XML dumps from binaries

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${SCRIPT_DIR}/../workspace"
EXTRACTED="${WORKSPACE}/extracted"
BASELINES="${WORKSPACE}/baselines"

LIBRARY="${1:-onedal}"
SOURCE="${2:-apt}"

EXTRACT_DIR="${EXTRACTED}/${LIBRARY}/${SOURCE}"
BASELINE_DIR="${BASELINES}/${LIBRARY}/${SOURCE}"

mkdir -p "${BASELINE_DIR}"

echo "Creating ABI baselines for ${LIBRARY} (source: ${SOURCE})..."

for VER_DIR in "${EXTRACT_DIR}"/2025.*; do
    [ -d "$VER_DIR" ] || continue
    
    VERSION=$(basename "$VER_DIR")
    BASELINE="${BASELINE_DIR}/${LIBRARY}_${VERSION}.abi"
    
    if [ -f "$BASELINE" ]; then
        echo "✓ $VERSION baseline exists ($(du -h "$BASELINE" | cut -f1))"
        continue
    fi
    
    # Find primary .so file
    SO_FILE=$(find "$VER_DIR" -name "lib${LIBRARY}.so.3" -type f | head -1)
    
    if [ -z "$SO_FILE" ]; then
        echo "⚠ $VERSION: libonedal.so.3 not found, skipping"
        continue
    fi
    
    echo "Creating baseline for $VERSION..."
    abidw "$SO_FILE" --out-file "$BASELINE" 2>&1 | grep -v "^$" || true
    
    SIZE=$(du -h "$BASELINE" | cut -f1)
    echo "  ✓ $VERSION baseline created ($SIZE)"
done

echo ""
echo "Baselines:"
ls -lh "${BASELINE_DIR}"/*.abi | awk '{print $9, "(" $5 ")"}'
