#!/bin/bash
# abi_tracker/run_full_analysis.sh
# Master script: download → extract → baseline → compare

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

LIBRARY="${1:-onedal}"
SOURCE="${2:-apt}"

echo "==================================================="
echo "ABI Tracker: Full Analysis"
echo "Library: ${LIBRARY}"
echo "Source: ${SOURCE}"
echo "==================================================="
echo ""

# Step 1: Download
echo "[1/4] Downloading packages..."
bash "${SCRIPT_DIR}/download_packages.sh" "$LIBRARY" "$SOURCE"
echo ""

# Step 2: Extract
echo "[2/4] Extracting binaries..."
bash "${SCRIPT_DIR}/extract_binaries.sh" "$LIBRARY" "$SOURCE"
echo ""

# Step 3: Create baselines
echo "[3/4] Creating ABI baselines..."
bash "${SCRIPT_DIR}/create_baselines.sh" "$LIBRARY" "$SOURCE"
echo ""

# Step 4: Compare
echo "[4/4] Comparing versions..."
bash "${SCRIPT_DIR}/compare_all.sh" "$LIBRARY" "$SOURCE"
echo ""

echo "==================================================="
echo "Analysis complete!"
echo "Reports: workspace/reports/${LIBRARY}/${SOURCE}/"
echo "==================================================="
