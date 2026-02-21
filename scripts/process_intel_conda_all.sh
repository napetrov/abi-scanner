#!/bin/bash
# abi_tracker/process_intel_conda_all.sh
# Process ALL dal versions from Intel conda (2021-2025)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# All Intel conda versions
VERSIONS=(
    "2021.7.0"
    "2021.7.1"
    "2023.0.0"
    "2023.1.0"
    "2023.2.0"
    "2024.0.0"
    "2024.0.1"
    "2024.2.0"
    "2024.3.0"
    "2024.4.0"
    "2024.5.0"
    "2024.6.0"
    "2024.7.0"
)

echo "==================================================="
echo "Processing Intel conda 2021-2024 versions"
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
echo "✓ All Intel conda versions processed"
echo "==================================================="
