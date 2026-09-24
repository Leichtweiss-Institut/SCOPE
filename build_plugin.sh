#!/usr/bin/env bash
#
# Build an installable QGIS plugin zip for SCOPE.
#
# The resulting SCOPE.zip contains a single top-level folder named
# "SCOPE" (matching the Python package name) and can be installed via
# QGIS -> Plugins -> Manage and Install Plugins -> Install from ZIP.
#
# Usage:
#   ./build_plugin.sh
#
set -euo pipefail

PLUGIN_NAME="SCOPE"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SRC_DIR}/build"
STAGE_DIR="${BUILD_DIR}/${PLUGIN_NAME}"
ZIP_PATH="${SRC_DIR}/${PLUGIN_NAME}.zip"

echo "Building ${PLUGIN_NAME} plugin package..."

# Fresh staging directory.
rm -rf "${BUILD_DIR}"
mkdir -p "${STAGE_DIR}"

# Copy plugin sources into the staging folder, excluding dev-only and
# generated artifacts. Everything that ships with the plugin lives here.
rsync -a \
    --exclude '.git/' \
    --exclude 'build/' \
    --exclude 'dist/' \
    --exclude '__pycache__/' \
    --exclude '*.py[cod]' \
    --exclude '*.code-workspace' \
    --exclude '*.zip' \
    --exclude '*.log' \
    --exclude '*.grd' \
    --exclude '*.xyz' \
    --exclude '.vscode/' \
    --exclude '.idea/' \
    --exclude 'build_plugin.sh' \
    --exclude 'launcher.py' \
    --exclude '.gitignore' \
    --exclude '.gitattributes' \
    --exclude '.ruff_cache/' \
    "${SRC_DIR}/" "${STAGE_DIR}/"

# Sanity check: metadata.txt must be present for the Plugin Manager.
if [[ ! -f "${STAGE_DIR}/metadata.txt" ]]; then
    echo "ERROR: metadata.txt missing from staging directory." >&2
    exit 1
fi

# Create the zip with the plugin folder at the top level.
rm -f "${ZIP_PATH}"
( cd "${BUILD_DIR}" && zip -r -q "${ZIP_PATH}" "${PLUGIN_NAME}" )

echo "Created: ${ZIP_PATH}"
echo "Install via QGIS -> Plugins -> Manage and Install Plugins -> Install from ZIP."
