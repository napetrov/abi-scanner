#!/bin/bash
# abi_tracker/process_conda_forge_versions.sh
# Process conda-forge dal/daal versions (2020-2021)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${WORKSPACE:-/workspace/abi_tracker_workspace}"

# Use dal (not daal) for consistency
VERSIONS=(
    "2020.1:daal-2020.1-219.tar.bz2"
    "2020.2:daal-2020.2-ha770c72_256.tar.bz2"
    "2020.3:daal-2020.3-ha770c72_304.tar.bz2"
    "2021.1.1:dal-2021.1.1-ha770c72_79.tar.bz2"
    "2021.2.2:dal-2021.2.2-ha770c72_389.tar.bz2"
    "2021.3.0:dal-2021.3.0-ha770c72_557.tar.bz2"
    "2021.4.0:dal-2021.4.0-ha770c72_729.tar.bz2"
    "2021.5.1:dal-2021.5.1-ha770c72_803.tar.bz2"
    "2021.6.0:dal-2021.6.0-ha770c72_915.tar.bz2"
)

BASELINES_DIR="${WORKSPACE}/baselines/dal"
METADATA_DIR="${WORKSPACE}/metadata/dal"

mkdir -p "$BASELINES_DIR" "$METADATA_DIR"

echo "==================================================="
echo "Processing conda-forge DAL/DAAL versions"
echo "Total: ${#VERSIONS[@]} versions"
echo "==================================================="
echo ""

for VER_PKG in "${VERSIONS[@]}"; do
    VERSION="${VER_PKG%%:*}"
    PACKAGE="${VER_PKG##*:}"
    
    BASELINE_FILE="${BASELINES_DIR}/dal_${VERSION}.abi"
    
    if [ -f "$BASELINE_FILE" ]; then
        echo "✓ ${VERSION} already exists, skipping"
        continue
    fi
    
    echo ""
    echo ">>> Processing $VERSION <<<"
    
    TEMP_DIR="/tmp/conda_forge_$$"
    mkdir -p "$TEMP_DIR"
    
    # Download
    echo "  [1/4] Downloading..."
    URL="https://conda.anaconda.org/conda-forge/linux-64/${PACKAGE}"
    curl -sL "$URL" -o "${TEMP_DIR}/package.tar.bz2"
    SIZE=$(du -h "${TEMP_DIR}/package.tar.bz2" | cut -f1)
    echo "    Downloaded: $SIZE"
    
    # Extract
    echo "  [2/4] Extracting..."
    tar xjf "${TEMP_DIR}/package.tar.bz2" -C "$TEMP_DIR" 2>/dev/null
    
    # Find .so
    echo "  [3/4] Creating ABI baseline..."
    SO_FILE=$(find "$TEMP_DIR" -name "libdaal.so*" -o -name "libonedal.so*" | grep -E "\.so\.[0-9]+" | head -1)
    
    if [ -z "$SO_FILE" ]; then
        echo "    ⚠️  No .so found, skipping"
        rm -rf "$TEMP_DIR"
        continue
    fi
    
    abidw "$SO_FILE" --out-file "$BASELINE_FILE" 2>&1 | grep -v "^$" | head -3 || true
    BASELINE_SIZE=$(du -h "$BASELINE_FILE" | cut -f1)
    echo "    ✓ Baseline: $BASELINE_SIZE"
    
    # Metadata
    echo "  [4/4] Metadata..."
    METADATA_FILE="${METADATA_DIR}/${VERSION}_metadata.json"
    cat > "$METADATA_FILE" << EOF
{
  "library": "dal",
  "version": "${VERSION}",
  "source": "conda_forge",
  "processed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "package": "${PACKAGE}",
  "baseline": "${BASELINE_FILE}",
  "baseline_size": "${BASELINE_SIZE}"
}
EOF
    
    # Cleanup
    rm -rf "$TEMP_DIR"
    
    echo "    ✓ Done"
done

echo ""
echo "==================================================="
echo "✓ All conda-forge versions processed"
echo "==================================================="
echo ""
echo "All baselines:"
ls -lh "$BASELINES_DIR"/*.abi | wc -l
du -sh "$BASELINES_DIR"
