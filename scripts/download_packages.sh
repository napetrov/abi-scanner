#!/bin/bash
# abi_tracker/download_packages.sh
# Download oneDAL packages from multiple sources

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="${SCRIPT_DIR}/../workspace"
DOWNLOADS="${WORKSPACE}/downloads"

# Configuration
LIBRARY="${1:-onedal}"
SOURCE="${2:-apt}"  # apt, conda, pypi
VERSIONS="${3:-all}"  # all, 2025.0-2025.10, or specific versions

mkdir -p "${DOWNLOADS}/${LIBRARY}/${SOURCE}"
cd "${DOWNLOADS}/${LIBRARY}/${SOURCE}"

case "${SOURCE}" in
    apt)
        echo "Downloading from Intel APT repository..."
        BASE_URL="https://apt.repos.intel.com/oneapi/pool/main"
        
        # Parse versions from repodata
        REPODATA="/tmp/oneapi_packages"
        if [ ! -f "$REPODATA" ]; then
            curl -s "${BASE_URL/pool\/main/dists/all/main/binary-amd64}/Packages.gz" | gunzip > "$REPODATA"
        fi
        
        # Get package list
        PACKAGES=$(awk '/^Package: intel-oneapi-dal-2025\./,/^Version:/ {
            if ($1 == "Package:") pkg=$2;
            if ($1 == "Version:") print pkg "-" $2 "_amd64.deb"
        }' "$REPODATA" | sort -V)
        
        for PKG in $PACKAGES; do
            if [ ! -f "$PKG" ]; then
                echo "Downloading $PKG..."
                wget -q "${BASE_URL}/${PKG}"
            else
                echo "✓ $PKG already downloaded"
            fi
        done
        ;;
        
    pypi)
        echo "Downloading from PyPI..."
        # For Python wheels with embedded .so
        # TODO: implement PyPI download logic
        echo "PyPI source not yet implemented"
        exit 1
        ;;
        
    conda)
        echo "Downloading from conda-forge..."
        # TODO: implement conda download logic
        echo "Conda source not yet implemented"
        exit 1
        ;;
        
    *)
        echo "Unknown source: ${SOURCE}"
        echo "Usage: $0 <library> <source:apt|conda|pypi> [versions]"
        exit 1
        ;;
esac

echo ""
echo "Downloaded packages:"
ls -lh *.deb 2>/dev/null || ls -lh *.whl 2>/dev/null || echo "No packages found"
