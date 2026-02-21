#!/bin/bash
# abi_tracker/process_all_apt_versions.sh
# Process remaining APT versions (2025.4+)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# APT versions not in conda
APT_VERSIONS=(
    "2025.4"
    "2025.5"
    "2025.6"
    "2025.8"
    "2025.9"
    "2025.10"
)

echo "==================================================="
echo "Processing APT-only oneDAL versions"
echo "Total: ${#APT_VERSIONS[@]} versions"
echo "==================================================="
echo ""

for VERSION in "${APT_VERSIONS[@]}"; do
    echo ""
    echo ">>> Processing $VERSION <<<"
    bash "${SCRIPT_DIR}/process_apt_version.sh" "$VERSION" || {
        echo "⚠️  Failed to process $VERSION, continuing..."
    }
    echo ""
    echo "---------------------------------------------------"
done

echo ""
echo "==================================================="
echo "✓ All APT versions processed"
echo "==================================================="
echo ""
echo "All baselines:"
ls -lh /workspace/abi_tracker_workspace/baselines/dal/*.abi | awk '{print $9, "(" $5 ")"}'
