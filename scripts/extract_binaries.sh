#!/bin/bash
# abi_tracker/extract_binaries.sh
# Extract .so files from packages

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${SCRIPT_DIR}/../workspace"
DOWNLOADS="${WORKSPACE}/downloads"
EXTRACTED="${WORKSPACE}/extracted"

LIBRARY="${1:-onedal}"
SOURCE="${2:-apt}"

PACKAGE_DIR="${DOWNLOADS}/${LIBRARY}/${SOURCE}"
EXTRACT_DIR="${EXTRACTED}/${LIBRARY}/${SOURCE}"

mkdir -p "${EXTRACT_DIR}"

echo "Extracting binaries from ${LIBRARY} (source: ${SOURCE})..."

case "${SOURCE}" in
    apt)
        for DEB in "${PACKAGE_DIR}"/*.deb; do
            [ -f "$DEB" ] || continue
            
            # Extract version from filename
            BASENAME=$(basename "$DEB" .deb)
            VERSION=$(echo "$BASENAME" | sed 's/intel-oneapi-dal-\(2025\.[0-9]*\).*/\1/')
            
            OUTDIR="${EXTRACT_DIR}/${VERSION}"
            
            if [ -d "$OUTDIR" ]; then
                echo "✓ $VERSION already extracted"
                continue
            fi
            
            echo "Extracting $VERSION..."
            mkdir -p "$OUTDIR"
            dpkg -x "$DEB" "$OUTDIR"
        done
        ;;
        
    pypi)
        # Extract from Python wheels
        for WHL in "${PACKAGE_DIR}"/*.whl; do
            [ -f "$WHL" ] || continue
            
            BASENAME=$(basename "$WHL" .whl)
            VERSION=$(echo "$BASENAME" | grep -oP '2025\.\d+\.\d+' | head -1)
            
            OUTDIR="${EXTRACT_DIR}/${VERSION}"
            
            if [ -d "$OUTDIR" ]; then
                echo "✓ $VERSION already extracted"
                continue
            fi
            
            echo "Extracting $VERSION..."
            mkdir -p "$OUTDIR"
            unzip -q "$WHL" -d "$OUTDIR"
        done
        ;;
esac

echo ""
echo "Finding .so files in ${LIBRARY}..."
find "${EXTRACT_DIR}" -name "lib${LIBRARY}*.so*" -type f | sort
