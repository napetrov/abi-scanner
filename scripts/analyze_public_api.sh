#!/bin/bash
# abi_tracker/analyze_public_api.sh
# Extract headers and determine public vs private API

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${SCRIPT_DIR}/../workspace"
EXTRACTED="${WORKSPACE}/extracted"
API_ANALYSIS="${WORKSPACE}/api_analysis"

LIBRARY="${1:-onedal}"
SOURCE="${2:-apt}"
VERSION="${3:-2025.0}"

EXTRACT_DIR="${EXTRACTED}/${LIBRARY}/${SOURCE}/${VERSION}"
ANALYSIS_DIR="${API_ANALYSIS}/${LIBRARY}/${SOURCE}/${VERSION}"

mkdir -p "${ANALYSIS_DIR}"

echo "Analyzing public API for ${LIBRARY} ${VERSION}..."

# Find header files
HEADERS=$(find "$EXTRACT_DIR" -name "*.h" -o -name "*.hpp" | grep -E "/include/" | sort)

if [ -z "$HEADERS" ]; then
    echo "No headers found in $EXTRACT_DIR"
    exit 1
fi

echo "Found $(echo "$HEADERS" | wc -l) header files"

# Parse public API namespaces/classes
echo ""
echo "Public namespaces:"
echo "$HEADERS" | xargs grep -h "^namespace " | sort -u | head -20

# Extract public classes
echo ""
echo "Public classes:"
echo "$HEADERS" | xargs grep -h "^class.*{" | sed 's/class \([A-Za-z_][A-Za-z0-9_]*\).*/\1/' | sort -u | head -30

# Generate public symbol list
OUTPUT="${ANALYSIS_DIR}/public_api.txt"
echo "# Public API for ${LIBRARY} ${VERSION}" > "$OUTPUT"
echo "# Generated: $(date)" >> "$OUTPUT"
echo "" >> "$OUTPUT"

# List all public function declarations
echo "Extracting function declarations..."
for HEADER in $HEADERS; do
    # Skip internal/detail headers
    if echo "$HEADER" | grep -qE "internal|detail|backend"; then
        continue
    fi
    
    # Extract function declarations
    grep -E "^\s*(virtual\s+)?[a-zA-Z_].*\(.*\).*;" "$HEADER" 2>/dev/null | \
        sed 's/^\s*//' | \
        grep -v "^//" | \
        grep -v "^#" >> "$OUTPUT" || true
done

echo "Public API analysis saved: $OUTPUT"
echo ""
echo "Summary:"
wc -l "$OUTPUT"
