#!/bin/bash
# abi_tracker/process_single_version.sh
# Download ONE version from Intel conda, extract ABI + public API, then delete

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${WORKSPACE:-/workspace/abi_tracker_workspace}"

LIBRARY="${1:-dal}"
VERSION="${2:-2025.0.0}"

echo "==================================================="
echo "Processing ${LIBRARY} ${VERSION}"
echo "==================================================="
echo ""

# Temporary directory for this version
TEMP_DIR="/tmp/abi_process_$$"
mkdir -p "$TEMP_DIR"

# Output directories
BASELINES_DIR="${WORKSPACE}/baselines/${LIBRARY}"
API_DIR="${WORKSPACE}/public_api/${LIBRARY}"
METADATA_DIR="${WORKSPACE}/metadata/${LIBRARY}"

mkdir -p "$BASELINES_DIR" "$API_DIR" "$METADATA_DIR"

# Intel conda channel
CONDA_BASE="https://software.repos.intel.com/python/conda/linux-64"

# Step 1: Get build number from repodata
echo "[1/6] Fetching package metadata..."
REPODATA="${TEMP_DIR}/repodata.json"
curl -s "${CONDA_BASE}/repodata.json" -o "$REPODATA"

# Find exact package filename
RUNTIME_PKG=$(python3 << PYEOF
import json
with open('$REPODATA') as f:
    data = json.load(f)
packages = data.get('packages', {})
for fname, meta in packages.items():
    if fname.startswith('${LIBRARY}-${VERSION}') and fname.endswith('.tar.bz2'):
        print(fname)
        break
PYEOF
)

INCLUDE_PKG=$(python3 << PYEOF
import json
with open('$REPODATA') as f:
    data = json.load(f)
packages = data.get('packages', {})
for fname, meta in packages.items():
    if fname.startswith('${LIBRARY}-include-${VERSION}') and fname.endswith('.tar.bz2'):
        print(fname)
        break
PYEOF
)

if [ -z "$RUNTIME_PKG" ]; then
    echo "❌ Runtime package not found for ${LIBRARY} ${VERSION}"
    rm -rf "$TEMP_DIR"
    exit 1
fi

echo "  Found: $RUNTIME_PKG"
if [ -n "$INCLUDE_PKG" ]; then
    echo "  Found: $INCLUDE_PKG"
fi

# Step 2: Download packages
echo ""
echo "[2/6] Downloading packages..."

curl -L "${CONDA_BASE}/${RUNTIME_PKG}" -o "${TEMP_DIR}/runtime.tar.bz2"
echo "  ✓ Runtime: $(du -h ${TEMP_DIR}/runtime.tar.bz2 | cut -f1)"

if [ -n "$INCLUDE_PKG" ]; then
    curl -L "${CONDA_BASE}/${INCLUDE_PKG}" -o "${TEMP_DIR}/include.tar.bz2"
    echo "  ✓ Include: $(du -h ${TEMP_DIR}/include.tar.bz2 | cut -f1)"
fi

# Step 3: Extract packages
echo ""
echo "[3/6] Extracting packages..."
EXTRACT_DIR="${TEMP_DIR}/extracted"
mkdir -p "$EXTRACT_DIR"

tar xjf "${TEMP_DIR}/runtime.tar.bz2" -C "$EXTRACT_DIR" 2>/dev/null
echo "  ✓ Runtime extracted"

if [ -f "${TEMP_DIR}/include.tar.bz2" ]; then
    tar xjf "${TEMP_DIR}/include.tar.bz2" -C "$EXTRACT_DIR" 2>/dev/null
    echo "  ✓ Headers extracted"
fi

# Step 4: Find primary .so and create ABI baseline
echo ""
echo "[4/6] Creating ABI baseline..."

# For dal package, primary lib is libonedal.so.3
SO_FILE=$(find "$EXTRACT_DIR" -name "libonedal.so.3" -type f | head -1)

if [ -z "$SO_FILE" ]; then
    echo "  ⚠️  libonedal.so.3 not found, trying alternatives..."
    SO_FILE=$(find "$EXTRACT_DIR" -name "libonedal*.so*" -type f | head -1)
fi

if [ -z "$SO_FILE" ]; then
    echo "  ❌ No .so files found!"
    rm -rf "$TEMP_DIR"
    exit 1
fi

BASELINE_FILE="${BASELINES_DIR}/${LIBRARY}_${VERSION}.abi"

if [ -f "$BASELINE_FILE" ]; then
    echo "  ✓ Baseline already exists"
else
    abidw "$SO_FILE" --out-file "$BASELINE_FILE" 2>&1 | grep -v "^$" | head -5 || true
    BASELINE_SIZE=$(du -h "$BASELINE_FILE" | cut -f1)
    echo "  ✓ ABI baseline: $BASELINE_SIZE"
fi

# Step 5: Parse headers for public API
echo ""
echo "[5/6] Parsing public API from headers..."

HEADERS_DIR=$(find "$EXTRACT_DIR" -type d -name "include" | head -1)

if [ -z "$HEADERS_DIR" ]; then
    echo "  ⚠️  No headers found in package"
    API_FILE=""
else
    HEADERS_COUNT=$(find "$HEADERS_DIR" -name "*.hpp" -o -name "*.h" | wc -l)
    echo "  Found $HEADERS_COUNT header files"
    
    API_FILE="${API_DIR}/${VERSION}_public_api.json"
    
    python3 "${SCRIPT_DIR}/scripts/parse_headers.py" "$HEADERS_DIR" "${LIBRARY}" > "$API_FILE" 2>/dev/null || true
    
    if [ -f "$API_FILE" ]; then
        echo "  ✓ Public API analysis saved: $API_FILE"
    fi
fi

# Step 6: Save metadata
echo ""
echo "[6/6] Saving metadata..."
METADATA_FILE="${METADATA_DIR}/${VERSION}_metadata.json"

cat > "$METADATA_FILE" << EOF
{
  "library": "${LIBRARY}",
  "version": "${VERSION}",
  "source": "intel_conda",
  "processed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "packages": {
    "runtime": "${RUNTIME_PKG}",
    "include": "${INCLUDE_PKG:-null}"
  },
  "files": {
    "baseline": "${BASELINE_FILE}",
    "public_api": "${API_FILE:-null}",
    "so_file": "$(basename $SO_FILE)"
  },
  "stats": {
    "headers_count": ${HEADERS_COUNT:-0},
    "baseline_size": "$(du -h $BASELINE_FILE | cut -f1)"
  }
}
EOF

echo "  ✓ Metadata: $METADATA_FILE"

# Cleanup temporary files
echo ""
echo "Cleaning up temporary files..."
rm -rf "$TEMP_DIR"

echo ""
echo "==================================================="
echo "✓ ${VERSION} processed successfully"
echo "  Baseline: ${BASELINE_FILE}"
[ -n "$API_FILE" ] && echo "  Public API: $API_FILE"
echo "  Metadata: $METADATA_FILE"
echo "==================================================="
