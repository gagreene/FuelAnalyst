#!/usr/bin/env bash
# Validate the official FOFEM 6.9.4 batch executable (runfofem.exe) under Wine on Linux.
#
# This is the Linux/Wine counterpart to tests/manual/fofem694_no_install_smoke.ps1: it invokes
# the tracked src/fuel_analyst/supporting_data/fofem_694/runfofem.exe directly (not through
# FuelAnalyst's Python code) in an isolated Wine prefix, once before and once after installing
# the Microsoft Visual C++ runtime via winetricks vcrun2022, matching the requirement in
# development/plans/2026-09-29-runfofem-wheel-integration.md's "Final step: Linux/Wine
# validation" section: "Test a fresh prefix both before and after runtime provisioning ...
# Record the Wine version, prefix architecture, runtime version, and results."
#
# The exact consumption/soil input lines and expected output column counts below (80/74/80 for
# consumption, 86/80/86 for soil) were verified directly against this same bundled EXE on
# Windows before this script was written - see the sibling PowerShell script and
# tests/integration/test_fofem694_official_batch.py's
# test_process_emissions_consumption_mode_matches_direct_runfofem_output for the source of the
# consumption row. This script only proves runfofem.exe itself runs correctly under Wine; it
# does not exercise FuelAnalyst's Python code - see the companion
# fofem694_linux_wine_validation.md for the follow-up steps that do.
#
# Usage:
#   bash tests/manual/fofem694_linux_wine_smoke.sh [--bundle-dir DIR] [--wineprefix DIR]
#       [--skip-preflight] [--include-mortality] [--keep]
#
#   --bundle-dir DIR       Directory with runfofem.exe/Emission_Factors.csv/fof_spp.csv.
#                          Defaults to the repository's tracked
#                          src/fuel_analyst/supporting_data/fofem_694.
#   --wineprefix DIR       Wine prefix to use/create. Defaults to a fresh temporary directory
#                          (recommended - a fresh prefix is what the plan asks to test).
#   --skip-preflight       Skip the "before winetricks" failure-mode check and provision
#                          vcrun2022 immediately. Use this only if you have already recorded
#                          the pre-provisioning failure separately.
#   --include-mortality    Also run the mortality (run type 2) case, requiring fof_spp.csv.
#   --keep                 Do not delete the temporary work directory on exit (for inspection).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BUNDLE_DIR="$REPO_ROOT/src/fuel_analyst/supporting_data/fofem_694"
WINEPREFIX_ARG=""
SKIP_PREFLIGHT=0
INCLUDE_MORTALITY=0
KEEP=0

while [ $# -gt 0 ]; do
    case "$1" in
        --bundle-dir) BUNDLE_DIR="$2"; shift 2 ;;
        --wineprefix) WINEPREFIX_ARG="$2"; shift 2 ;;
        --skip-preflight) SKIP_PREFLIGHT=1; shift ;;
        --include-mortality) INCLUDE_MORTALITY=1; shift ;;
        --keep) KEEP=1; shift ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

if ! command -v wine >/dev/null 2>&1; then
    echo "FATAL: 'wine' is not on PATH. Install it first (e.g. 'sudo apt install wine' on" >&2
    echo "Debian/Ubuntu, which also pulls in wine-binfmt for transparent .exe execution)." >&2
    exit 1
fi
if ! command -v winetricks >/dev/null 2>&1; then
    echo "FATAL: 'winetricks' is not on PATH. Install it first (e.g. 'sudo apt install winetricks')." >&2
    exit 1
fi

for name in runfofem.exe Emission_Factors.csv fof_spp.csv; do
    if [ ! -f "$BUNDLE_DIR/$name" ]; then
        echo "FATAL: missing required bundle file: $BUNDLE_DIR/$name" >&2
        exit 1
    fi
done
BURNUP_FIXTURE="$REPO_ROOT/tests/test_data/fofem694/burnup_parameters_694.brn"
if [ ! -f "$BURNUP_FIXTURE" ]; then
    echo "FATAL: missing Burnup parameter fixture: $BURNUP_FIXTURE" >&2
    exit 1
fi
if [ "$INCLUDE_MORTALITY" -eq 1 ]; then
    MORTALITY_FIXTURE="$REPO_ROOT/tests/test_data/fofem694/FFI_FOFEM_Sample.tre"
    if [ ! -f "$MORTALITY_FIXTURE" ]; then
        echo "FATAL: missing mortality fixture: $MORTALITY_FIXTURE" >&2
        exit 1
    fi
fi

WORKDIR="$(mktemp -d)"
if [ "$KEEP" -eq 0 ]; then
    trap 'rm -rf "$WORKDIR"' EXIT
else
    echo "Work directory (kept): $WORKDIR"
fi

if [ -n "$WINEPREFIX_ARG" ]; then
    export WINEPREFIX="$WINEPREFIX_ARG"
else
    export WINEPREFIX="$WORKDIR/wineprefix"
fi
export WINEARCH=win64
export WINEDEBUG=-all

APP_DIR="$WORKDIR/app"
DATA_DIR="$WORKDIR/work"
mkdir -p "$APP_DIR" "$DATA_DIR"
cp "$BUNDLE_DIR/runfofem.exe" "$APP_DIR/runfofem.exe"
cp "$BUNDLE_DIR/Emission_Factors.csv" "$APP_DIR/Emission_Factors.csv"
cp "$BUNDLE_DIR/fof_spp.csv" "$APP_DIR/fof_spp.csv"
# FOFEM resolves its reference CSVs through FOFEM_DATA, not the executable's
# directory. Use a Windows path so the batch application can read it under Wine.
export FOFEM_DATA="$(winepath -w "$APP_DIR" | tr -d '\r\n')"
cp "$BURNUP_FIXTURE" "$DATA_DIR/Burnup-Params.brn"
if [ "$INCLUDE_MORTALITY" -eq 1 ]; then
    cp "$MORTALITY_FIXTURE" "$DATA_DIR/FFI_FOFEM_Sample.tre"
fi

echo "=== Environment ==="
echo "uname: $(uname -a)"
echo "wine: $(wine --version)"
echo "winetricks: $(winetricks --version 2>&1 | sed -n '/^[0-9]/p')"
echo "WINEPREFIX: $WINEPREFIX"
echo "WINEARCH: $WINEARCH"
echo "Bundle dir: $BUNDLE_DIR"
echo "FOFEM_DATA: $FOFEM_DATA"
echo

write_consumption_input() {
    # Writes a batch consumption/soil input file with the required Expanded Emission Factor
    # switches, using the exact row verified against this EXE on Windows.
    #
    # :param $1: Destination input file path.
    # :param $2: '0' for consumption, '1' for soil.
    # :return: None. Writes the input file.
    local dest="$1"
    local mode="$2"
    {
        printf '#1k-SizeClass\r\n'
        printf '#ConsumptionEquation\r\n'
        printf '#EFG-STFS 3\r\n'
        printf '#EFG-CWDRSC 7\r\n'
        printf '#EFG-DuffRSC 8\r\n'
        printf '#BurnUpFile %s\r\n' "$(winepath -w "$DATA_DIR/Burnup-Params.brn" 2>/dev/null | tr -d '\r\n')"
        printf '#PlotId,Litter\r\n'
        if [ "$mode" = '1' ]; then
            printf 'p1,4.46,0.45,0.89,6.0,1.34,0.45,0.45,0.45,0.45,0.45,0.45,0.45,0.45,10.0,8.92,20.0,1.18,2.23,0.45,1.78,2.23,10.0,InteriorWest,GrassGroup,Summer,Natural,Loamy-Skeletal,10,20.0,-1,-1,-1,-1,-1,-1\r\n'
        else
            printf 'p1,4.46,0.45,0.89,6.0,1.34,0.45,0.45,0.45,0.45,0.45,0.45,0.45,0.45,10.0,8.92,20.0,1.18,2.23,0.45,1.78,2.23,10.0,InteriorWest,GrassGroup,Summer,Natural,-1,-1,-1,-1,-1,-1\r\n'
        fi
    } > "$dest"
}

run_case() {
    # Runs one runfofem.exe batch case under Wine and reports pass/fail.
    #
    # :param $1: Case name (for messages).
    # :param $2: Run type ('0' consumption, '1' soil).
    # :param $3: Expected output line count.
    # :param $4: Expected header/unit column counts, e.g. "80,74,80".
    # :param $5: Whether a failure is EXPECTED here (1) or not (0) - used for the preflight check.
    # :return: 0 if the observed result matched what was expected, 1 otherwise. Prints details.
    local name="$1" mode="$2" expected_lines="$3" expected_cols="$4" expect_failure="$5"
    local input="$DATA_DIR/${name}_input.txt"
    local output="$DATA_DIR/${name}_output.csv"
    local error="$DATA_DIR/${name}_error.txt"
    write_consumption_input "$input" "$mode"

    set +e
    wine "$APP_DIR/runfofem.exe" "$mode" \
        "$(winepath -w "$input" | tr -d '\r\n')" \
        "$(winepath -w "$output" | tr -d '\r\n')" \
        "$(winepath -w "$error" | tr -d '\r\n')"
    local rc=$?
    set -e

    if [ "$expect_failure" -eq 1 ]; then
        if [ "$rc" -ne 0 ] || [ ! -s "$output" ]; then
            echo "$name: FAIL AS EXPECTED (preflight, exit $rc) - runfofem.exe could not run correctly."
            if [ -f "$error" ]; then
                cat "$error"
            fi
            return 0
        fi
        echo "$name: UNEXPECTEDLY SUCCEEDED before vcrun2022 provisioning (exit $rc)."
        echo "  This host's Wine prefix may already have a usable VC++ runtime from elsewhere."
        return 0
    fi

    if [ "$rc" -ne 0 ] || [ ! -f "$output" ] || [ ! -f "$error" ]; then
        echo "$name: FAIL - exit $rc, output/error file missing. Work dir: $DATA_DIR"
        return 1
    fi
    local actual_lines
    actual_lines=$(awk 'END{print NR}' "$output")
    if [ "$actual_lines" -ne "$expected_lines" ]; then
        echo "$name: FAIL - output has $actual_lines lines, expected $expected_lines. Work dir: $DATA_DIR"
        return 1
    fi
    local counts
    counts=$(awk -F',' 'NR<=3{print NF}' "$output" | paste -sd,)
    if [ "$counts" != "$expected_cols" ]; then
        echo "$name: FAIL - column counts $counts, expected $expected_cols. Work dir: $DATA_DIR"
        return 1
    fi
    if ! grep -q '"p1"' "$output"; then
        echo "$name: FAIL - output does not contain plot 'p1'. Work dir: $DATA_DIR"
        return 1
    fi
    local real_errors
    real_errors=$(tail -n +5 "$error" | tr -d '\r' | grep -c '[^[:space:]]' || true)
    if [ "$real_errors" -ne 0 ]; then
        echo "$name: FAIL - runfofem.exe reported batch errors: $(tail -n +5 "$error")"
        return 1
    fi
    echo "$name: PASS ($counts columns, $actual_lines lines)"
    return 0
}

echo "=== Preflight: before winetricks vcrun2022 (expect failure) ==="
if [ "$SKIP_PREFLIGHT" -eq 1 ]; then
    echo "Skipped (--skip-preflight)."
else
    run_case 'preflight' '0' 3 '80,74,80' 1 || true
fi
echo

echo "=== Provisioning: winetricks vcrun2022 ==="
winetricks -q vcrun2022
echo "Provisioned."
echo

echo "=== Consumption (run type 0) ==="
consumption_ok=1
run_case 'consumption' '0' 3 '80,74,80' 0 || consumption_ok=0
echo

echo "=== Soil (run type 1) ==="
soil_ok=1
run_case 'soil' '1' 3 '86,80,86' 0 || soil_ok=0
echo

mortality_ok=1
if [ "$INCLUDE_MORTALITY" -eq 1 ]; then
    echo "=== Mortality (run type 2) ==="
    input="$DATA_DIR/FFI_FOFEM_Sample.tre"
    output="$DATA_DIR/mortality_output.csv"
    error="$DATA_DIR/mortality_error.txt"
    set +e
    wine "$APP_DIR/runfofem.exe" '2' \
        "$(winepath -w "$input" | tr -d '\r\n')" \
        "$(winepath -w "$output" | tr -d '\r\n')" \
        "$(winepath -w "$error" | tr -d '\r\n')" 'S' '10'
    rc=$?
    set -e
    if [ "$rc" -ne 0 ] || [ ! -s "$output" ]; then
        echo "mortality: FAIL - exit $rc. Work dir: $DATA_DIR"
        mortality_ok=0
    else
        echo "mortality: PASS ($(awk 'END{print NR}' "$output") lines)"
    fi
    echo
fi

echo "=== Summary ==="
echo "Wine: $(wine --version)"
echo "WINEARCH: $WINEARCH"
echo "vcrun2022: provisioned via winetricks"
echo "Consumption: $([ "$consumption_ok" -eq 1 ] && echo PASS || echo FAIL)"
echo "Soil: $([ "$soil_ok" -eq 1 ] && echo PASS || echo FAIL)"
if [ "$INCLUDE_MORTALITY" -eq 1 ]; then
    echo "Mortality: $([ "$mortality_ok" -eq 1 ] && echo PASS || echo FAIL)"
fi

if [ "$consumption_ok" -eq 1 ] && [ "$soil_ok" -eq 1 ] && [ "$mortality_ok" -eq 1 ]; then
    exit 0
fi
exit 1
