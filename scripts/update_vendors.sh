#!/usr/bin/env bash
# Update vendored third-party code under src/fuel_analyst/_vendor/.
#
# bcwft2018 (single file) comes from the dependencies/BC_CFFBPS_FuelTyping_Tool submodule:
#   git submodule update --remote dependencies/BC_CFFBPS_FuelTyping_Tool
#   bash scripts/update_vendors.sh
#
# ConPyro (package) comes from a local clone of https://github.com/gagreene/conpyro, which
# stays the upstream source of truth. Point CONPYRO_SRC at that clone (it must have no
# uncommitted changes; check out the commit you want to vendor first):
#   CONPYRO_SRC=/path/to/conpyro bash scripts/update_vendors.sh
# Without CONPYRO_SRC only bcwft2018 is refreshed; either part is skipped when its source is unavailable.
# Note: flame_components is not vendored; it is installed from PyPI.
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR_DIR="$REPO_ROOT/src/fuel_analyst/_vendor"

# bcwft2018 (skipped when the submodule is not checked out, e.g. a non-recursive clone)
BC_DIR="$REPO_ROOT/dependencies/BC_CFFBPS_FuelTyping_Tool"
if [ -f "$BC_DIR/bcwft2018.py" ]; then
  BC_SHA=$(git -C "$BC_DIR" rev-parse --short HEAD)
  { echo "# Vendored from https://github.com/gagreene/BC_CFFBPS_FuelTyping_Tool"
    echo "# Upstream commit: $BC_SHA"
    echo "# To update: run scripts/update_vendors.sh"
    echo ""
    cat "$BC_DIR/bcwft2018.py"
  } > "$VENDOR_DIR/bcwft2018.py"
  echo "Updated bcwft2018.py (commit $BC_SHA)"
else
  echo "BC_CFFBPS_FuelTyping_Tool submodule not checked out; skipped bcwft2018"
fi

# conpyro
if [ -n "${CONPYRO_SRC:-}" ]; then
  if [ ! -d "$CONPYRO_SRC/src/conpyro" ]; then
    echo "CONPYRO_SRC=$CONPYRO_SRC has no src/conpyro directory" >&2
    exit 1
  fi
  if [ -n "$(git -C "$CONPYRO_SRC" status --porcelain)" ]; then
    echo "CONPYRO_SRC has uncommitted changes; commit or stash them first" >&2
    exit 1
  fi
  CP_SHA=$(git -C "$CONPYRO_SRC" rev-parse HEAD)
  CP_DST="$VENDOR_DIR/conpyro"
  rm -rf "$CP_DST"
  mkdir -p "$CP_DST"
  cp -R "$CONPYRO_SRC/src/conpyro/." "$CP_DST/"
  rm -rf "$CP_DST/tests"
  find "$CP_DST" -name __pycache__ -type d -prune -exec rm -rf {} +
  find "$CP_DST" -name '*.pyc' -delete
  {
    echo "# Vendored ConPyro"
    echo ""
    echo "- Upstream: https://github.com/gagreene/conpyro"
    echo "- Upstream commit: $CP_SHA"
    echo "- License: MIT (Gregory A. Greene), same as FuelAnalyst"
    echo '- Generated copy: do not edit here. Fix upstream, then run `scripts/update_vendors.sh`.'
    echo '- Excluded from this copy: `tests/`, `docs/`, `build/`, `pyproject.toml`. FuelAnalyst keeps its own ISF solver unit test in `tests/unit/vendored_conpyro/`.'
  } > "$CP_DST/UPSTREAM.md"
  echo "Updated conpyro (commit $CP_SHA)"
else
  echo "CONPYRO_SRC not set; skipped conpyro"
fi
