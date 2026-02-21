#!/bin/bash
# abi_tracker/process_apt_version.sh
# Process one version from Intel APT repository

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${WORKSPACE:-/workspace/abi_tracker_workspace}"

VERSION="${1:-2025.4}"

echo "==================================================="
echo "Processing oneDAL ${VERSION} (APT source)"
echo "==================================================="
echo ""

TEMP_DIR="/tmp/abi_apt_process_$$"
mkdir -p "$TEMP_DIR"

BASELINES_DIR="${WORKSPACE}/baselines/dal"
API_DIR="${WORKSPACE}/public_api/dal"
METADATA_DIR="${WORKSPACE}/metadata/dal"

mkdir -p "$BASELINES_DIR" "$API_DIR" "$METADATA_DIR"

# Check if already processed
BASELINE_FILE="${BASELINES_DIR}/dal_${VERSION}.0.abi"
if [ -f "$BASELINE_FILE" ]; then
    echo "✓ ${VERSION} already processed, skipping download"
    echo "  Baseline exists: $BASELINE_FILE"
    exit 0
fi

# Intel APT repository
APT_BASE="https://apt.repos.intel.com/oneapi/pool/main"

# Step 1: Get package metadata
echo "[1/6] Fetching APT metadata..."
REPODATA="${TEMP_DIR}/Packages"
curl -s "https://apt.repos.intel.com/oneapi/dists/all/main/binary-amd64/Packages.gz" | gunzip > "$REPODATA"

# Find exact .deb filenames
RUNTIME_DEB=$(awk "/^Package: intel-oneapi-dal-${VERSION}\$/,/^Filename:/ {if (\$1 == \"Filename:\") print \$2}" "$REPODATA" | head -1)
DEVEL_DEB=$(awk "/^Package: intel-oneapi-dal-devel-${VERSION}\$/,/^Filename:/ {if (\$1 == \"Filename:\") print \$2}" "$REPODATA" | head -1)

if [ -z "$RUNTIME_DEB" ]; then
    echo "❌ Runtime package not found for ${VERSION}"
    rm -rf "$TEMP_DIR"
    exit 1
fi

echo "  Found: $(basename $RUNTIME_DEB)"
[ -n "$DEVEL_DEB" ] && echo "  Found: $(basename $DEVEL_DEB)"

# Step 2: Download runtime only (devel too large, skip for now)
echo ""
echo "[2/6] Downloading runtime package..."
RUNTIME_FILE="${TEMP_DIR}/runtime.deb"
curl -L "https://apt.repos.intel.com/oneapi/${RUNTIME_DEB}" -o "$RUNTIME_FILE"
echo "  ✓ Runtime: $(du -h $RUNTIME_FILE | cut -f1)"

# Step 3: Extract
echo ""
echo "[3/6] Extracting runtime..."
EXTRACT_DIR="${TEMP_DIR}/extracted"
mkdir -p "$EXTRACT_DIR"
dpkg -x "$RUNTIME_FILE" "$EXTRACT_DIR" 2>/dev/null
echo "  ✓ Extracted"

# Step 4: Create ABI baseline
echo ""
echo "[4/6] Creating ABI baseline..."
SO_FILE=$(find "$EXTRACT_DIR" -name "libonedal.so.3" -type f | head -1)

if [ -z "$SO_FILE" ]; then
    echo "  ❌ libonedal.so.3 not found!"
    rm -rf "$TEMP_DIR"
    exit 1
fi

abidw "$SO_FILE" --out-file "$BASELINE_FILE" 2>&1 | grep -v "^$" | head -5 || true
BASELINE_SIZE=$(du -h "$BASELINE_FILE" | cut -f1)
echo "  ✓ ABI baseline: $BASELINE_SIZE"

# Step 5: Headers (skip for now, too large)
echo ""
echo "[5/6] Headers..."
echo "  ⚠️  Skipping headers (APT devel package is 168MB, use conda versions for headers)"

# Step 6: Metadata
echo ""
echo "[6/6] Saving metadata..."
METADATA_FILE="${METADATA_DIR}/${VERSION}.0_metadata.json"

cat > "$METADATA_FILE" << EOF
{
  "library": "dal",
  "version": "${VERSION}.0",
  "source": "intel_apt",
  "processed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "packages": {
    "runtime": "$(basename $RUNTIME_DEB)",
    "devel": "$(basename ${DEVEL_DEB:-null})"
  },
  "files": {
    "baseline": "${BASELINE_FILE}",
    "public_api": null,
    "so_file": "$(basename $SO_FILE)"
  },
  "stats": {
    "headers_count": 0,
    "baseline_size": "$(du -h $BASELINE_FILE | cut -f1)"
  }
}
EOF

echo "  ✓ Metadata: $METADATA_FILE"

# Cleanup
echo ""
echo "Cleaning up..."
rm -rf "$TEMP_DIR"

echo ""
echo "==================================================="
echo "✓ ${VERSION} processed successfully"
echo "  Baseline: ${BASELINE_FILE}"
echo "==================================================="
