#!/usr/bin/env bash
# Update vendored third-party code under src/fuel_analyst/_vendor/.
#
# By default each source is shallow-cloned from its upstream GitHub repository (default branch)
# into a temporary directory, so every run vendors the newest upstream commit. Run it from an
# account that can read the repositories; the temporary clones are deleted on exit.
#
#   bash scripts/update_vendors.sh                    refresh bcwft2018 and ConPyro
#   bash scripts/update_vendors.sh --only bc          refresh only bcwft2018
#   bash scripts/update_vendors.sh --only conpyro     refresh only ConPyro
#
# Each source is refreshed independently: if one fails (cannot clone, missing files, dirty local
# clone), the error is reported, its existing vendored copy is left exactly as it was, the other
# source is still refreshed, and the script exits 1 at the end. A vendored copy is only replaced
# after its replacement has been fully built.
#
# To vendor a specific commit (or unpushed upstream work) instead, point an env var at a local
# clone with no uncommitted changes, with that commit checked out:
#   BC_SRC=/path/to/BC_CFFBPS_FuelTyping_Tool   bcwft2018 (single file, bcwft2018.py)
#   CONPYRO_SRC=/path/to/conpyro                ConPyro (package, src/conpyro)
# BC_URL and CONPYRO_URL override the upstream clone URLs (used by the tests).
# Note: flame_components is not vendored; it is installed from PyPI.
set -e

BC_URL="${BC_URL:-https://github.com/gagreene/BC_CFFBPS_FuelTyping_Tool.git}"
CONPYRO_URL="${CONPYRO_URL:-https://github.com/gagreene/conpyro.git}"

ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --only)
      ONLY="${2:-}"
      case "$ONLY" in
        bc|conpyro) ;;
        *) echo "--only expects 'bc' or 'conpyro'" >&2; exit 2 ;;
      esac
      shift 2
      ;;
    *)
      echo "Unknown argument: $1 (see the header of this script)" >&2
      exit 2
      ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR_DIR="$REPO_ROOT/src/fuel_analyst/_vendor"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT

# Note: set -e is inactive inside functions called from an `||` list, so every step below checks
# its own status and returns 1 on failure.

# Set SRC_DIR to a source checkout: the local override when given, else a fresh shallow clone.
# $1 = override path (may be empty), $2 = upstream URL, $3 = label for messages
prepare_src() {
  if [ -n "$1" ]; then
    SRC_DIR="$1"
    return 0
  fi
  SRC_DIR="$TMP_ROOT/$3"
  echo "Cloning $2 ..."
  if ! git clone --quiet --depth 1 "$2" "$SRC_DIR"; then
    echo "Could not clone $2" >&2
    return 1
  fi
}

# Return 1 when a local override clone has uncommitted changes.
# $1 = override path (may be empty), $2 = env var name for the message
require_clean_override() {
  if [ -n "$1" ] && [ -n "$(git -C "$1" status --porcelain)" ]; then
    echo "$2 has uncommitted changes; commit or stash them first" >&2
    return 1
  fi
}

refresh_bc() {
  prepare_src "${BC_SRC:-}" "$BC_URL" bc || return 1
  if [ ! -f "$SRC_DIR/bcwft2018.py" ]; then
    echo "BC source $SRC_DIR has no bcwft2018.py" >&2
    return 1
  fi
  require_clean_override "${BC_SRC:-}" BC_SRC || return 1
  local sha
  sha=$(git -C "$SRC_DIR" rev-parse --short HEAD) || return 1
  local out="$TMP_ROOT/bcwft2018.py.new"
  { echo "# Vendored from https://github.com/gagreene/BC_CFFBPS_FuelTyping_Tool"
    echo "# Upstream commit: $sha"
    echo "# To update: run scripts/update_vendors.sh"
    echo ""
    cat "$SRC_DIR/bcwft2018.py"
  } > "$out" || return 1
  cp "$out" "$VENDOR_DIR/bcwft2018.py" || return 1
  echo "Updated bcwft2018.py (commit $sha)"
}

refresh_conpyro() {
  prepare_src "${CONPYRO_SRC:-}" "$CONPYRO_URL" conpyro || return 1
  if [ ! -d "$SRC_DIR/src/conpyro" ]; then
    echo "ConPyro source $SRC_DIR has no src/conpyro directory" >&2
    return 1
  fi
  require_clean_override "${CONPYRO_SRC:-}" CONPYRO_SRC || return 1
  local sha
  sha=$(git -C "$SRC_DIR" rev-parse HEAD) || return 1
  # Build the replacement package aside; the existing vendored copy is only swapped out once the
  # new one is complete.
  local new="$TMP_ROOT/conpyro.new"
  mkdir -p "$new" || return 1
  cp -R "$SRC_DIR/src/conpyro/." "$new/" || return 1
  rm -rf "$new/tests"
  find "$new" -name __pycache__ -type d -prune -exec rm -rf {} +
  find "$new" -name '*.pyc' -delete
  {
    echo "# Vendored ConPyro"
    echo ""
    echo "- Upstream: https://github.com/gagreene/conpyro"
    echo "- Upstream commit: $sha"
    echo "- License: MIT (Gregory A. Greene), same as FuelAnalyst"
    echo '- Generated copy: do not edit here. Fix upstream, then run `scripts/update_vendors.sh`.'
    echo '- Excluded from this copy: `tests/`, `docs/`, `build/`, `pyproject.toml`. FuelAnalyst keeps its own ISF solver unit test in `tests/unit/vendored_conpyro/`.'
  } > "$new/UPSTREAM.md" || return 1
  local old="$TMP_ROOT/conpyro.old"
  if [ -d "$VENDOR_DIR/conpyro" ]; then
    mv "$VENDOR_DIR/conpyro" "$old" || return 1
  fi
  if ! mv "$new" "$VENDOR_DIR/conpyro"; then
    rm -rf "$VENDOR_DIR/conpyro"
    [ -d "$old" ] && mv "$old" "$VENDOR_DIR/conpyro"
    return 1
  fi
  echo "Updated conpyro (commit $sha)"
}

FAILED=""
if [ -z "$ONLY" ] || [ "$ONLY" = "bc" ]; then
  refresh_bc || FAILED="$FAILED bcwft2018"
fi
if [ -z "$ONLY" ] || [ "$ONLY" = "conpyro" ]; then
  refresh_conpyro || FAILED="$FAILED conpyro"
fi
if [ -n "$FAILED" ]; then
  echo "Refresh failed for:$FAILED (existing vendored copies were left unchanged)" >&2
  exit 1
fi
