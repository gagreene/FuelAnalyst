#!/usr/bin/env bash
# Update vendored single-file modules from their git submodule sources.
# Run after pulling new submodule commits:
#   git submodule update --remote dependencies/flame_components dependencies/BC_CFFBPS_FuelTyping_Tool
#   bash update_vendors.sh
set -e

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
VENDOR_DIR="$REPO_ROOT/src/fuel_analyst/_vendor"

# flame_components
FC_SHA=$(git -C "$REPO_ROOT/dependencies/flame_components" rev-parse --short HEAD)
{ echo "# Vendored from https://github.com/gagreene/flame_components"
  echo "# Upstream commit: $FC_SHA"
  echo "# To update: run update_vendors.sh"
  echo ""
  cat "$REPO_ROOT/dependencies/flame_components/flame_components.py"
} > "$VENDOR_DIR/flame_components.py"
echo "Updated flame_components.py (commit $FC_SHA)"

# bcwft2018
BC_SHA=$(git -C "$REPO_ROOT/dependencies/BC_CFFBPS_FuelTyping_Tool" rev-parse --short HEAD)
{ echo "# Vendored from https://github.com/gagreene/BC_CFFBPS_FuelTyping_Tool"
  echo "# Upstream commit: $BC_SHA"
  echo "# To update: run update_vendors.sh"
  echo ""
  cat "$REPO_ROOT/dependencies/BC_CFFBPS_FuelTyping_Tool/bcwft2018.py"
} > "$VENDOR_DIR/bcwft2018.py"
echo "Updated bcwft2018.py (commit $BC_SHA)"
