#!/bin/bash
# abi_tracker/process_all_2025_versions.sh
# Process all oneDAL 2025.x versions from Intel conda

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Available versions in Intel conda (as of 2026-02-21)
VERSIONS=(
    "2025.0.0"
    "2025.0.1"
    "2025.1.0"
    "2025.2.0"
)

echo "==================================================="
echo "Processing all oneDAL 2025.x versions"
echo "Total: ${#VERSIONS[@]} versions"
echo "==================================================="
echo ""

for VERSION in "${VERSIONS[@]}"; do
    echo ""
    echo ">>> Processing $VERSION <<<"
    bash "${SCRIPT_DIR}/process_single_version.sh" dal "$VERSION" || {
        echo "⚠️  Failed to process $VERSION, continuing..."
    }
    echo ""
    echo "---------------------------------------------------"
done

echo ""
echo "==================================================="
echo "✓ All versions processed"
echo "==================================================="
echo ""
echo "Baselines:"
ls -lh /workspace/abi_tracker_workspace/baselines/dal/*.abi

echo ""
echo "Public API:"
ls -lh /workspace/abi_tracker_workspace/public_api/dal/*.json
