# FOFEM 6.9.4 Linux/Wine validation results

Recorded on 2026-09-29 (America/Vancouver).

**The raw FOFEM executable and the updated FuelAnalyst `fof_gui` backend work
under Wine on this host: all eight real integration tests passed, and all 33
targeted unit tests passed after correcting a fixture line-ending assumption.**
The user approved the production change after the initial validation. The
integration test gate was temporarily loosened for validation and restored.
No bundled DLLs, commits, or pushes were added or created.

## Environment

- Branch: `test/linux-wine-runfofem-validation`.
- HEAD: `8892291a9f68979c062920bd7b80a24ce42725f0` (actual checkout rather than
  the `2bc493b` starting commit named in the instructions).
- Distribution: Ubuntu 24.04.5 LTS, Noble Numbat; architecture: `x86_64`.
- Kernel: `Linux Gregory-Threadripper 6.17.0-20-generic #20~24.04.1-Ubuntu SMP PREEMPT_DYNAMIC Thu Mar 19 01:28:37 UTC 2 x86_64 x86_64 x86_64 GNU/Linux`.
- Wine: `wine-9.0 (Ubuntu 9.0~repack-4build3)`.
- Installed packages: `wine`, `wine64`, and `wine-binfmt` each
  `9.0~repack-4build3`; `winetricks` `20240105-2`.
- `winetricks --version`: `20240105 - sha256sum: 17da748ce874adb2ee9fed79d2550c0c58e57d5969cc779a8779301350625c55`.
- `/usr/share/binfmts/wine` exists with `package wine`,
  `interpreter /usr/bin/wine`, and `magic MZ`. However, outside the sandbox,
  `/proc/sys/fs/binfmt_misc` contains only `python3.12`, `register`, and `status`:
  **no active Wine handler**. `update-binfmts` is absent from PATH.
- Configured PyCharm interpreter: Python 3.13.2, conda environment
  `/home/gregory/miniconda3/envs/ProcessGeospatial`; package manager: conda.
  `fuel-analyst`, `pyfofem-fire-effects`, and `pytest` distributions are absent;
  source imports work using `PYTHONPATH=src`.
- The referenced root `AGENTS.md` and `.claude/CLAUDE.md` are absent; no parent
  `AGENTS.md` was found up to `/` during initial inspection.

Initially Wine and winetricks were absent. The agent's installation attempt,
`sudo -n apt-get install -y wine winetricks wine-binfmt`, failed with
`sudo: a password is required` (exit 1). The user then installed the packages.
The initial smoke attempt before installation exited 1 with this complete output:

```text
FATAL: 'wine' is not on PATH. Install it first (e.g. 'sudo apt install wine' on
Debian/Ubuntu, which also pulls in wine-binfmt for transparent .exe execution).
```

After installation, sandboxed `wine --version` was terminated with
`Bad system call`. Wine invocations and final Python probes were therefore run
outside the sandbox using the approved escalation mechanism. There was no
automatic approval-review rejection. Host binary registration was inspected
outside the sandbox as well.

## Smoke-script defect and verified correction

The first installed-Wine run used the unchanged script and a fresh prefix at
`/tmp/tmp.q9eCKvDlOw/wineprefix`. All three post-provisioning cases failed:
consumption and soil exited 1; mortality exited 24. Inspecting the batch error
files, rather than changing expected output counts, identified missing reference
data. The exact preflight error file contained:

```text
 This file contains FOFEM batch errors.
 Some missing numeric values may be represented as -1
 Input file: Z:\tmp\tmp.q9eCKvDlOw\work\preflight_input.txt

Error opening or can't find input emission file: Emission_Factors.csv

 Emission_Factors.csv - please make sure the Environment Variable FOFEM_DATA is set to where this file resides
```

Consumption/soil reported the same missing `Emission_Factors.csv`; mortality
reported 24 records with species codes not found. This was a script setup defect,
not a Windows-loader or VC++ runtime failure. A diagnostic consumption call in
that same provisioned prefix, changing only `FOFEM_DATA` to
`Z:\tmp\tmp.q9eCKvDlOw\app`, exited 0, produced the expected `80,74,80` columns,
and had only the standard batch-error preamble.

The smoke script was corrected to export a Wine-converted `FOFEM_DATA` path to
its isolated app directory. Its winetricks version reporting now selects the
numeric version rather than the `Executing cd /usr/bin` banner, and preflight
failures print the batch error file if present. **Expected line counts, column
counts, and pass/fail checks were not loosened.** `bash -n` passes.

## Corrected fresh-prefix results

Command:

```bash
bash tests/manual/fofem694_linux_wine_smoke.sh --include-mortality --keep
```

- Exit code: **0**.
- Retained work directory: `/tmp/tmp.WDSM21nPRu`.
- Retained prefix: `/tmp/tmp.WDSM21nPRu/wineprefix`; `WINEARCH=win64`.
- Isolated app directory: `/tmp/tmp.WDSM21nPRu/app`.
- Provisioning: `winetricks -q vcrun2022` completed.
- Installed x64 runtime registry version: **`v14.44.35211.00`**, `Installed=1`,
  queried using `wine reg query 'HKLM\Software\Microsoft\VisualStudio\14.0\VC\Runtimes\x64'`.

| Case | Result |
| --- | --- |
| Consumption before VC++ provisioning | Succeeded, exit 0, in a newly created prefix |
| Runtime provisioning | Completed; x64 registry version `v14.44.35211.00` |
| Consumption after provisioning | PASS: 3 lines, column counts `80,74,80` |
| Soil after provisioning | PASS: 3 lines, column counts `86,80,86` |
| Mortality after provisioning | PASS: 11 output lines, exit 0; error file independently inspected and contains only the standard preamble |

**There is no missing-runtime failure text to report for the corrected fresh
prefix: it already executes consumption before separately provisioning VC++.**
The script explicitly reports `UNEXPECTEDLY SUCCEEDED`. The earlier preflight
failure was the missing-reference-data error quoted above and must not be
presented as evidence of a missing runtime. The source of the working
pre-provisioning runtime implementation was not separately investigated.

The distro's 2024 winetricks script reported SHA256 mismatches for the current
Microsoft x86/x64 redistributable downloads. Its unattended `-q` mode continued
without prompting; no `--force` flag or checksum edits were used. The full logs
below preserve the URLs and expected/observed hashes. Provisioning and actual
batch execution succeeded despite these warnings; this does not establish that
this old winetricks version will reliably provision future downloads.

## FuelAnalyst-level probes before the approved code change

The configured Python interpreter was checked using the `python-tools` skill.
With the same successfully provisioned prefix, `WINEARCH=win64`,
`FUEL_ANALYST_FOFEM_DIR=/tmp/tmp.WDSM21nPRu/app`, and `PYTHONPATH=src`, direct
`subprocess.run([exe_path], capture_output=True, text=True, timeout=30)` calls
and the actual unmodified `_run_runfofem()` helper produced:

```text
WINEPREFIX: /tmp/tmp.WDSM21nPRu/wineprefix
CREATE_NO_WINDOW available: False
Tracked bundle PermissionError [Errno 13] Permission denied: '/home/gregory/PycharmProjects/FuelAnalyst/src/fuel_analyst/supporting_data/fofem_694/runfofem.exe'
Provisioned smoke app PermissionError [Errno 13] Permission denied: '/tmp/tmp.WDSM21nPRu/app/runfofem.exe'
Executable temporary copy: OSError [Errno 8] Exec format error: '/tmp/fuelanalyst-pe-probe-_zl8c7dv/runfofem.exe'
FuelAnalyst invocation: AttributeError module 'subprocess' has no attribute 'CREATE_NO_WINDOW'
```

The tracked EXE has Git mode `100644` and lacks execute permission. The temporary
copy probe used `shutil.copy2` and `chmod(0o755)` solely to distinguish the
permission failure from missing binary-format handling; it was automatically
removed. The tracked executable's permissions were not changed.

The helper probe used the real corrected consumption input and retained work
folder. It fails while evaluating the Windows-only
`subprocess.CREATE_NO_WINDOW` argument, before launching a child process.
Consequently, registering Wine and changing execute permissions alone cannot
make this exact helper work on Linux.

At this stage the editable `[fofem]` installation and opt-in pytest suite were not run because
the prerequisite condition for that step—transparent executable invocation—did
not pass. The configured environment also lacks pytest. The Windows-only gate
was never loosened, so no gate restoration was needed and no test passes or
skips are claimed.

## Approved implementation and final validation

The user subsequently approved implementation. `_run_runfofem()` now prepends
`wine` on Linux and uses `subprocess.CREATE_NO_WINDOW` only on Windows (zero
creation flags elsewhere). Windows still executes the EXE directly. Existing
environment handling preserves `WINEPREFIX` and supplies worker-specific
`FOFEM_DATA`. No binfmt handler, execute-bit changes, or DLL bundling is needed.

The configured interpreter installed the editable `.[fofem,test]` checkout,
`pyfofem-fire-effects==0.1.1`, pytest 9.1.1, and pytest support dependencies into
`/tmp/fuelanalyst-wine-validation-deps` using pip's `--target` and `--no-deps`
options. The configured conda environment's packages were not changed. Existing
scientific packages came from that environment; `PYTHONPATH` included the target
directory and `src` for the validation runs.

With `WINEPREFIX=/tmp/tmp.WDSM21nPRu/wineprefix`, `WINEDEBUG=-all`,
`FUEL_ANALYST_FOFEM_DIR=/tmp/tmp.WDSM21nPRu/app`, and
`FUEL_ANALYST_RUN_FOFEM694_TESTS=1`, the real suite was run outside the sandbox:

```shell
/home/gregory/miniconda3/envs/ProcessGeospatial/bin/python -m pytest tests/integration/test_fofem694_official_batch.py tests/unit/test_fofem_gui_emissions.py -v
```

The integration gate was temporarily changed to check only the opt-in variable.
A shell EXIT trap restored the original file, and `git diff` confirms no change
to `tests/integration/test_fofem694_official_batch.py` remains. Its permanent gate
still allows only Windows, as requested in the validation instructions.

**All eight real integration tests passed**, including consumption compared with
independently constructed batch output, soil, wind limits and errors,
equation selection, missing-data validation, malformed-input reporting, and
generated mortality input acceptance. This verifies native Linux input/output
paths, the generated Burnup path, and worker reference-data lookup for those
cases; no extra path conversion was needed in the Python helper.

The combined run initially reported 40 passed and one failed. The failure was an
existing byte-comparison test whose fixture checks out with LF on Linux while
the writer emits CRLF. The test now canonicalizes only the fixture's line endings
to CRLF before the exact byte comparison, still requiring the writer to emit
CRLF and preserving all expected parameter content. Production writer behavior
was not changed. A subsequent targeted unit run passed **33/33**. Added launcher
coverage verifies Linux execution without the Windows subprocess constant,
Windows's original flags/command, mortality arguments, paths containing spaces,
and preservation of the selected prefix and data directory. Windows behavior
was checked with a mocked launcher, not rerun on a Windows host.

README and CODEBASE now document Linux/Wine execution and prefix setup; the
runtime wheel remains Windows-only. Multicore execution was covered by existing
mocked unit coverage, not a new real concurrent Wine stress test.

## Final verdict

**The bundled raw EXE and the updated FuelAnalyst backend work under Wine 9.0 on
this Ubuntu host. A code change was necessary and has been implemented with
user approval.** The observed raw
failures came from smoke-script reference-data lookup, and the corrected script
passes in a fresh prefix. There is no reason from this run to reintroduce bundled
Microsoft DLLs.

The implementation, launcher tests, documentation, smoke script, and this report
are staged explicitly by name. Nothing has been committed or pushed. Results
apply to the tested host and runtime; other Wine versions and macOS were not
validated.

## Full installed-Wine console output, before script correction

The console transcripts below retain every output line; CRLF endings and
trailing whitespace are normalized for Markdown.

<details>
<summary>Complete combined stdout/stderr; exit code 1</summary>

```text
Work directory (kept): /tmp/tmp.q9eCKvDlOw
=== Environment ===
uname: Linux Gregory-Threadripper 6.17.0-20-generic #20~24.04.1-Ubuntu SMP PREEMPT_DYNAMIC Thu Mar 19 01:28:37 UTC 2 x86_64 x86_64 x86_64 GNU/Linux
wine: wine-9.0 (Ubuntu 9.0~repack-4build3)
winetricks: Executing cd /usr/bin
WINEPREFIX: /tmp/tmp.q9eCKvDlOw/wineprefix
WINEARCH: win64
Bundle dir: /home/gregory/PycharmProjects/FuelAnalyst/src/fuel_analyst/supporting_data/fofem_694

=== Preflight: before winetricks vcrun2022 (expect failure) ===
preflight: FAIL AS EXPECTED (preflight, exit 1) - runfofem.exe could not run correctly.

=== Provisioning: winetricks vcrun2022 ===
Executing cd /usr/bin
------------------------------------------------------
warning: You are using a 64-bit WINEPREFIX. Note that many verbs only install 32-bit versions of packages. If you encounter problems, please retest in a clean 32-bit WINEPREFIX before reporting a bug.
------------------------------------------------------
Using winetricks 20240105 - sha256sum: 17da748ce874adb2ee9fed79d2550c0c58e57d5969cc779a8779301350625c55 with wine-9.0 (Ubuntu 9.0~repack-4build3) and WINEARCH=win64
Executing w_do_call vcrun2022
------------------------------------------------------
warning: You are using a 64-bit WINEPREFIX. Note that many verbs only install 32-bit versions of packages. If you encounter problems, please retest in a clean 32-bit WINEPREFIX before reporting a bug.
------------------------------------------------------
Executing load_vcrun2022
Using native,builtin override for following DLLs: concrt140 msvcp140 msvcp140_1 msvcp140_2 msvcp140_atomic_wait msvcp140_codecvt_ids vcamp140 vccorlib140 vcomp140 vcruntime140
Executing wine C:\windows\syswow64\regedit.exe /S C:\windows\Temp\override-dll.reg
Executing /usr/lib/wine/wine64 C:\windows\regedit.exe /S C:\windows\Temp\override-dll.reg
Executing mkdir -p /home/gregory/.cache/winetricks/vcrun2022
Executing cd /home/gregory/.cache/winetricks/vcrun2022
Downloading https://aka.ms/vs/17/release/vc_redist.x86.exe to /home/gregory/.cache/winetricks/vcrun2022
--2026-09-29 18:48:30--  https://aka.ms/vs/17/release/vc_redist.x86.exe
Resolving aka.ms (aka.ms)... 184.30.154.152
Connecting to aka.ms (aka.ms)|184.30.154.152|:443... connected.
HTTP request sent, awaiting response... 301 Moved Permanently
Location: https://download.visualstudio.microsoft.com/download/pr/bd1c8d9d-ba95-4eee-bc6e-df1fcc876373/0C09F2611660441084CE0DF425C51C11E147E6447963C3690F97E0B25C55ED64/VC_redist.x86.exe [following]
--2026-09-29 18:48:30--  https://download.visualstudio.microsoft.com/download/pr/bd1c8d9d-ba95-4eee-bc6e-df1fcc876373/0C09F2611660441084CE0DF425C51C11E147E6447963C3690F97E0B25C55ED64/VC_redist.x86.exe
Resolving download.visualstudio.microsoft.com (download.visualstudio.microsoft.com)... 2001:569:139::cfc2:c70b, 2001:569:139::cfc2:c71a, 140.248.154.172
Connecting to download.visualstudio.microsoft.com (download.visualstudio.microsoft.com)|2001:569:139::cfc2:c70b|:443... connected.
HTTP request sent, awaiting response... 200 OK
Length: 13953392 (13M) [application/octet-stream]
Saving to: ‘vc_redist.x86.exe’

     0K .......... .......... .......... .......... ..........  0% 5.88M 2s
    50K .......... .......... .......... .......... ..........  0% 4.32M 3s
   100K .......... .......... .......... .......... ..........  1% 7.25M 2s
   150K .......... .......... .......... .......... ..........  1% 11.3M 2s
   200K .......... .......... .......... .......... ..........  1% 10.9M 2s
   250K .......... .......... .......... .......... ..........  2% 20.0M 2s
   300K .......... .......... .......... .......... ..........  2% 14.4M 2s
   350K .......... .......... .......... .......... ..........  2% 10.7M 2s
   400K .......... .......... .......... .......... ..........  3% 15.5M 1s
   450K .......... .......... .......... .......... ..........  3% 50.5M 1s
   500K .......... .......... .......... .......... ..........  4% 3.25M 2s
   550K .......... .......... .......... .......... ..........  4% 77.1M 1s
   600K .......... .......... .......... .......... ..........  4% 27.6M 1s
   650K .......... .......... .......... .......... ..........  5%  215M 1s
   700K .......... .......... .......... .......... ..........  5% 56.4M 1s
   750K .......... .......... .......... .......... ..........  5% 35.3M 1s
   800K .......... .......... .......... .......... ..........  6% 6.84M 1s
   850K .......... .......... .......... .......... ..........  6% 50.9M 1s
   900K .......... .......... .......... .......... ..........  6% 25.6M 1s
   950K .......... .......... .......... .......... ..........  7%  162M 1s
  1000K .......... .......... .......... .......... ..........  7% 51.5M 1s
  1050K .......... .......... .......... .......... ..........  8% 58.1M 1s
  1100K .......... .......... .......... .......... ..........  8% 7.05M 1s
  1150K .......... .......... .......... .......... ..........  8%  183M 1s
  1200K .......... .......... .......... .......... ..........  9%  115M 1s
  1250K .......... .......... .......... .......... ..........  9% 63.8M 1s
  1300K .......... .......... .......... .......... ..........  9% 64.2M 1s
  1350K .......... .......... .......... .......... .......... 10% 75.7M 1s
  1400K .......... .......... .......... .......... .......... 10%  152M 1s
  1450K .......... .......... .......... .......... .......... 11% 60.0M 1s
  1500K .......... .......... .......... .......... .......... 11% 79.8M 1s
  1550K .......... .......... .......... .......... .......... 11% 50.1M 1s
  1600K .......... .......... .......... .......... .......... 12% 85.6M 1s
  1650K .......... .......... .......... .......... .......... 12%  150M 1s
  1700K .......... .......... .......... .......... .......... 12% 59.8M 1s
  1750K .......... .......... .......... .......... .......... 13% 60.0M 1s
  1800K .......... .......... .......... .......... .......... 13% 85.6M 1s
  1850K .......... .......... .......... .......... .......... 13% 61.4M 1s
  1900K .......... .......... .......... .......... .......... 14%  147M 1s
  1950K .......... .......... .......... .......... .......... 14% 15.0M 1s
  2000K .......... .......... .......... .......... .......... 15% 1.16M 1s
  2050K .......... .......... .......... .......... .......... 15%  164M 1s
  2100K .......... .......... .......... .......... .......... 15%  130M 1s
  2150K .......... .......... .......... .......... .......... 16%  101M 1s
  2200K .......... .......... .......... .......... .......... 16%  129M 1s
  2250K .......... .......... .......... .......... .......... 16%  105M 1s
  2300K .......... .......... .......... .......... .......... 17%  100M 1s
  2350K .......... .......... .......... .......... .......... 17%  151M 1s
  2400K .......... .......... .......... .......... .......... 17% 80.2M 1s
  2450K .......... .......... .......... .......... .......... 18%  120M 1s
  2500K .......... .......... .......... .......... .......... 18%  138M 1s
  2550K .......... .......... .......... .......... .......... 19% 2.88M 1s
  2600K .......... .......... .......... .......... .......... 19% 98.7M 1s
  2650K .......... .......... .......... .......... .......... 19% 70.3M 1s
  2700K .......... .......... .......... .......... .......... 20%  189M 1s
  2750K .......... .......... .......... .......... .......... 20%  109M 1s
  2800K .......... .......... .......... .......... .......... 20%  126M 1s
  2850K .......... .......... .......... .......... .......... 21% 97.4M 1s
  2900K .......... .......... .......... .......... .......... 21%  161M 1s
  2950K .......... .......... .......... .......... .......... 22% 72.0M 1s
  3000K .......... .......... .......... .......... .......... 22%  159M 1s
  3050K .......... .......... .......... .......... .......... 22% 1.84M 1s
  3100K .......... .......... .......... .......... .......... 23%  138M 1s
  3150K .......... .......... .......... .......... .......... 23% 93.8M 1s
  3200K .......... .......... .......... .......... .......... 23%  200M 1s
  3250K .......... .......... .......... .......... .......... 24%  104M 1s
  3300K .......... .......... .......... .......... .......... 24% 86.1M 1s
  3350K .......... .......... .......... .......... .......... 24% 94.1M 1s
  3400K .......... .......... .......... .......... .......... 25%  145M 1s
  3450K .......... .......... .......... .......... .......... 25%  119M 1s
  3500K .......... .......... .......... .......... .......... 26% 94.1M 1s
  3550K .......... .......... .......... .......... .......... 26%  167M 1s
  3600K .......... .......... .......... .......... .......... 26% 96.0M 1s
  3650K .......... .......... .......... .......... .......... 27%  103M 1s
  3700K .......... .......... .......... .......... .......... 27%  158M 1s
  3750K .......... .......... .......... .......... .......... 27% 94.0M 1s
  3800K .......... .......... .......... .......... .......... 28% 93.7M 1s
  3850K .......... .......... .......... .......... .......... 28%  177M 1s
  3900K .......... .......... .......... .......... .......... 28% 88.9M 0s
  3950K .......... .......... .......... .......... .......... 29%  104M 0s
  4000K .......... .......... .......... .......... .......... 29% 94.6M 0s
  4050K .......... .......... .......... .......... .......... 30% 9.96M 0s
  4100K .......... .......... .......... .......... .......... 30%  191M 0s
  4150K .......... .......... .......... .......... .......... 30% 93.3M 0s
  4200K .......... .......... .......... .......... .......... 31%  134M 0s
  4250K .......... .......... .......... .......... .......... 31%  106M 0s
  4300K .......... .......... .......... .......... .......... 31% 94.9M 0s
  4350K .......... .......... .......... .......... .......... 32%  107M 0s
  4400K .......... .......... .......... .......... .......... 32% 96.4M 0s
  4450K .......... .......... .......... .......... .......... 33%  170M 0s
  4500K .......... .......... .......... .......... .......... 33% 91.4M 0s
  4550K .......... .......... .......... .......... .......... 33%  145M 0s
  4600K .......... .......... .......... .......... .......... 34% 5.04M 0s
  4650K .......... .......... .......... .......... .......... 34% 98.9M 0s
  4700K .......... .......... .......... .......... .......... 34%  130M 0s
  4750K .......... .......... .......... .......... .......... 35%  165M 0s
  4800K .......... .......... .......... .......... .......... 35% 72.3M 0s
  4850K .......... .......... .......... .......... .......... 35%  184M 0s
  4900K .......... .......... .......... .......... .......... 36% 95.5M 0s
  4950K .......... .......... .......... .......... .......... 36% 95.0M 0s
  5000K .......... .......... .......... .......... .......... 37%  102M 0s
  5050K .......... .......... .......... .......... .......... 37%  159M 0s
  5100K .......... .......... .......... .......... .......... 37%  112M 0s
  5150K .......... .......... .......... .......... .......... 38% 89.0M 0s
  5200K .......... .......... .......... .......... .......... 38%  155M 0s
  5250K .......... .......... .......... .......... .......... 38%  102M 0s
  5300K .......... .......... .......... .......... .......... 39%  128M 0s
  5350K .......... .......... .......... .......... .......... 39%  124M 0s
  5400K .......... .......... .......... .......... .......... 39% 93.7M 0s
  5450K .......... .......... .......... .......... .......... 40% 88.6M 0s
  5500K .......... .......... .......... .......... .......... 40%  178M 0s
  5550K .......... .......... .......... .......... .......... 41%  107M 0s
  5600K .......... .......... .......... .......... .......... 41% 18.5M 0s
  5650K .......... .......... .......... .......... .......... 41%  122M 0s
  5700K .......... .......... .......... .......... .......... 42%  117M 0s
  5750K .......... .......... .......... .......... .......... 42% 93.3M 0s
  5800K .......... .......... .......... .......... .......... 42%  104M 0s
  5850K .......... .......... .......... .......... .......... 43%  153M 0s
  5900K .......... .......... .......... .......... .......... 43% 98.6M 0s
  5950K .......... .......... .......... .......... .......... 44% 93.9M 0s
  6000K .......... .......... .......... .......... .......... 44%  194M 0s
  6050K .......... .......... .......... .......... .......... 44% 90.8M 0s
  6100K .......... .......... .......... .......... .......... 45% 1.58M 0s
  6150K .......... .......... .......... .......... .......... 45%  149M 0s
  6200K .......... .......... .......... .......... .......... 45% 95.8M 0s
  6250K .......... .......... .......... .......... .......... 46%  139M 0s
  6300K .......... .......... .......... .......... .......... 46%  113M 0s
  6350K .......... .......... .......... .......... .......... 46% 97.7M 0s
  6400K .......... .......... .......... .......... .......... 47%  110M 0s
  6450K .......... .......... .......... .......... .......... 47% 92.8M 0s
  6500K .......... .......... .......... .......... .......... 48%  156M 0s
  6550K .......... .......... .......... .......... .......... 48% 98.0M 0s
  6600K .......... .......... .......... .......... .......... 48%  114M 0s
  6650K .......... .......... .......... .......... .......... 49%  931K 0s
  6700K .......... .......... .......... .......... .......... 49%  136M 0s
  6750K .......... .......... .......... .......... .......... 49% 76.0M 0s
  6800K .......... .......... .......... .......... .......... 50%  169M 0s
  6850K .......... .......... .......... .......... .......... 50% 90.4M 0s
  6900K .......... .......... .......... .......... .......... 51%  224M 0s
  6950K .......... .......... .......... .......... .......... 51% 87.6M 0s
  7000K .......... .......... .......... .......... .......... 51%  103M 0s
  7050K .......... .......... .......... .......... .......... 52% 94.6M 0s
  7100K .......... .......... .......... .......... .......... 52%  161M 0s
  7150K .......... .......... .......... .......... .......... 52%  481K 0s
  7200K .......... .......... .......... .......... .......... 53%  151M 0s
  7250K .......... .......... .......... .......... .......... 53%  121M 0s
  7300K .......... .......... .......... .......... .......... 53% 87.4M 0s
  7350K .......... .......... .......... .......... .......... 54%  131M 0s
  7400K .......... .......... .......... .......... .......... 54% 96.2M 0s
  7450K .......... .......... .......... .......... .......... 55%  146M 0s
  7500K .......... .......... .......... .......... .......... 55% 73.4M 0s
  7550K .......... .......... .......... .......... .......... 55%  168M 0s
  7600K .......... .......... .......... .......... .......... 56% 91.1M 0s
  7650K .......... .......... .......... .......... .......... 56%  103M 0s
  7700K .......... .......... .......... .......... .......... 56%  174M 0s
  7750K .......... .......... .......... .......... .......... 57%  119M 0s
  7800K .......... .......... .......... .......... .......... 57% 80.3M 0s
  7850K .......... .......... .......... .......... .......... 57%  159M 0s
  7900K .......... .......... .......... .......... .......... 58%  104M 0s
  7950K .......... .......... .......... .......... .......... 58% 87.8M 0s
  8000K .......... .......... .......... .......... .......... 59%  160M 0s
  8050K .......... .......... .......... .......... .......... 59%  103M 0s
  8100K .......... .......... .......... .......... .......... 59% 92.7M 0s
  8150K .......... .......... .......... .......... .......... 60%  276K 0s
  8200K .......... .......... .......... .......... .......... 60%  122M 0s
  8250K .......... .......... .......... .......... .......... 60%  162M 0s
  8300K .......... .......... .......... .......... .......... 61%  103M 0s
  8350K .......... .......... .......... .......... .......... 61% 94.7M 0s
  8400K .......... .......... .......... .......... .......... 62%  160M 0s
  8450K .......... .......... .......... .......... .......... 62%  105M 0s
  8500K .......... .......... .......... .......... .......... 62%  109M 0s
  8550K .......... .......... .......... .......... .......... 63%  133M 0s
  8600K .......... .......... .......... .......... .......... 63%  102M 0s
  8650K .......... .......... .......... .......... .......... 63% 93.4M 0s
  8700K .......... .......... .......... .......... .......... 64%  381K 0s
  8750K .......... .......... .......... .......... .......... 64%  222M 0s
  8800K .......... .......... .......... .......... .......... 64%  337M 0s
  8850K .......... .......... .......... .......... .......... 65%  131M 0s
  8900K .......... .......... .......... .......... .......... 65%  105M 0s
  8950K .......... .......... .......... .......... .......... 66% 89.6M 0s
  9000K .......... .......... .......... .......... .......... 66%  189M 0s
  9050K .......... .......... .......... .......... .......... 66%  138M 0s
  9100K .......... .......... .......... .......... .......... 67% 91.9M 0s
  9150K .......... .......... .......... .......... .......... 67%  109M 0s
  9200K .......... .......... .......... .......... .......... 67%  980K 0s
  9250K .......... .......... .......... .......... .......... 68%  126M 0s
  9300K .......... .......... .......... .......... .......... 68%  173M 0s
  9350K .......... .......... .......... .......... .......... 68%  118M 0s
  9400K .......... .......... .......... .......... .......... 69%  125M 0s
  9450K .......... .......... .......... .......... .......... 69% 94.8M 0s
  9500K .......... .......... .......... .......... .......... 70%  119M 0s
  9550K .......... .......... .......... .......... .......... 70%  102M 0s
  9600K .......... .......... .......... .......... .......... 70%  105M 0s
  9650K .......... .......... .......... .......... .......... 71% 92.9M 0s
  9700K .......... .......... .......... .......... .......... 71%  178M 0s
  9750K .......... .......... .......... .......... .......... 71%  103M 0s
  9800K .......... .......... .......... .......... .......... 72%  125M 0s
  9850K .......... .......... .......... .......... .......... 72% 85.1M 0s
  9900K .......... .......... .......... .......... .......... 73%  100M 0s
  9950K .......... .......... .......... .......... .......... 73%  163M 0s
 10000K .......... .......... .......... .......... .......... 73%  117M 0s
 10050K .......... .......... .......... .......... .......... 74% 95.1M 0s
 10100K .......... .......... .......... .......... .......... 74% 70.7M 0s
 10150K .......... .......... .......... .......... .......... 74%  319M 0s
 10200K .......... .......... .......... .......... .......... 75% 1.82M 0s
 10250K .......... .......... .......... .......... .......... 75% 89.3M 0s
 10300K .......... .......... .......... .......... .......... 75%  191M 0s
 10350K .......... .......... .......... .......... .......... 76%  171M 0s
 10400K .......... .......... .......... .......... .......... 76%  154M 0s
 10450K .......... .......... .......... .......... .......... 77% 96.8M 0s
 10500K .......... .......... .......... .......... .......... 77%  263M 0s
 10550K .......... .......... .......... .......... .......... 77% 78.8M 0s
 10600K .......... .......... .......... .......... .......... 78%  212M 0s
 10650K .......... .......... .......... .......... .......... 78% 88.7M 0s
 10700K .......... .......... .......... .......... .......... 78%  118M 0s
 10750K .......... .......... .......... .......... .......... 79% 2.43M 0s
 10800K .......... .......... .......... .......... .......... 79% 81.0M 0s
 10850K .......... .......... .......... .......... .......... 79%  155M 0s
 10900K .......... .......... .......... .......... .......... 80%  102M 0s
 10950K .......... .......... .......... .......... .......... 80%  105M 0s
 11000K .......... .......... .......... .......... .......... 81% 94.0M 0s
 11050K .......... .......... .......... .......... .......... 81%  159M 0s
 11100K .......... .......... .......... .......... .......... 81%  104M 0s
 11150K .......... .......... .......... .......... .......... 82%  121M 0s
 11200K .......... .......... .......... .......... .......... 82%  115M 0s
 11250K .......... .......... .......... .......... .......... 82% 37.4M 0s
 11300K .......... .......... .......... .......... .......... 83% 89.5M 0s
 11350K .......... .......... .......... .......... .......... 83% 99.4M 0s
 11400K .......... .......... .......... .......... .......... 84%  103M 0s
 11450K .......... .......... .......... .......... .......... 84% 95.0M 0s
 11500K .......... .......... .......... .......... .......... 84%  149M 0s
 11550K .......... .......... .......... .......... .......... 85%  108M 0s
 11600K .......... .......... .......... .......... .......... 85% 94.0M 0s
 11650K .......... .......... .......... .......... .......... 85%  192M 0s
 11700K .......... .......... .......... .......... .......... 86% 89.3M 0s
 11750K .......... .......... .......... .......... .......... 86% 93.7M 0s
 11800K .......... .......... .......... .......... .......... 86%  184M 0s
 11850K .......... .......... .......... .......... .......... 87% 95.3M 0s
 11900K .......... .......... .......... .......... .......... 87%  102M 0s
 11950K .......... .......... .......... .......... .......... 88%  117M 0s
 12000K .......... .......... .......... .......... .......... 88%  132M 0s
 12050K .......... .......... .......... .......... .......... 88% 87.3M 0s
 12100K .......... .......... .......... .......... .......... 89%  102M 0s
 12150K .......... .......... .......... .......... .......... 89%  150M 0s
 12200K .......... .......... .......... .......... .......... 89%  146M 0s
 12250K .......... .......... .......... .......... .......... 90% 4.98M 0s
 12300K .......... .......... .......... .......... .......... 90% 94.5M 0s
 12350K .......... .......... .......... .......... .......... 91%  183M 0s
 12400K .......... .......... .......... .......... .......... 91% 95.9M 0s
 12450K .......... .......... .......... .......... .......... 91%  156M 0s
 12500K .......... .......... .......... .......... .......... 92%  106M 0s
 12550K .......... .......... .......... .......... .......... 92%  102M 0s
 12600K .......... .......... .......... .......... .......... 92% 93.2M 0s
 12650K .......... .......... .......... .......... .......... 93%  119M 0s
 12700K .......... .......... .......... .......... .......... 93%  120M 0s
 12750K .......... .......... .......... .......... .......... 93%  101M 0s
 12800K .......... .......... .......... .......... .......... 94% 2.99M 0s
 12850K .......... .......... .......... .......... .......... 94% 94.2M 0s
 12900K .......... .......... .......... .......... .......... 95% 93.4M 0s
 12950K .......... .......... .......... .......... .......... 95%  135M 0s
 13000K .......... .......... .......... .......... .......... 95%  113M 0s
 13050K .......... .......... .......... .......... .......... 96% 94.7M 0s
 13100K .......... .......... .......... .......... .......... 96%  168M 0s
 13150K .......... .......... .......... .......... .......... 96% 94.6M 0s
 13200K .......... .......... .......... .......... .......... 97% 93.7M 0s
 13250K .......... .......... .......... .......... .......... 97%  141M 0s
 13300K .......... .......... .......... .......... .......... 97%  104M 0s
 13350K .......... .......... .......... .......... .......... 98%  119M 0s
 13400K .......... .......... .......... .......... .......... 98%  141M 0s
 13450K .......... .......... .......... .......... .......... 99% 98.2M 0s
 13500K .......... .......... .......... .......... .......... 99%  120M 0s
 13550K .......... .......... .......... .......... .......... 99% 83.8M 0s
 13600K .......... .......... ......                          100%  309M=0.9s

2026-09-29 18:48:32 (14.4 MB/s) - ‘vc_redist.x86.exe’ saved [13953392/13953392]

Executing cd /home/gregory/PycharmProjects/FuelAnalyst
------------------------------------------------------
SHA256 mismatch!

URL: https://aka.ms/vs/17/release/vc_redist.x86.exe
Downloaded: 0c09f2611660441084ce0df425c51c11e147e6447963c3690f97e0b25c55ed64
Expected: c61cef97487536e766130fa8714dd1b4143f6738bfb71806018eee1b5fe6f057

This is often the result of an updated package such as vcrun2019.
If you are willing to accept the risk, you can bypass this check.
Alternatively, you may use the --force option to ignore this check entirely.

Continue anyway?
------------------------------------------------------
------------------------------------------------------
Unattended mode, not prompting for confirmation
------------------------------------------------------
Executing cd /home/gregory/.cache/winetricks/vcrun2022
Executing wine vc_redist.x86.exe /q
Using native,builtin override for following DLLs: vcruntime140_1
Executing wine C:\windows\syswow64\regedit.exe /S C:\windows\Temp\override-dll.reg
Executing /usr/lib/wine/wine64 C:\windows\regedit.exe /S C:\windows\Temp\override-dll.reg
Executing cd /home/gregory/.cache/winetricks/vcrun2022
Downloading https://aka.ms/vs/17/release/vc_redist.x64.exe to /home/gregory/.cache/winetricks/vcrun2022
--2026-09-29 18:48:33--  https://aka.ms/vs/17/release/vc_redist.x64.exe
Resolving aka.ms (aka.ms)... 184.30.154.152
Connecting to aka.ms (aka.ms)|184.30.154.152|:443... connected.
HTTP request sent, awaiting response... 301 Moved Permanently
Location: https://download.visualstudio.microsoft.com/download/pr/bd1c8d9d-ba95-4eee-bc6e-df1fcc876373/CC0FF0EB1DC3F5188AE6300FAEF32BF5BEEBA4BDD6E8E445A9184072096B713B/VC_redist.x64.exe [following]
--2026-09-29 18:48:33--  https://download.visualstudio.microsoft.com/download/pr/bd1c8d9d-ba95-4eee-bc6e-df1fcc876373/CC0FF0EB1DC3F5188AE6300FAEF32BF5BEEBA4BDD6E8E445A9184072096B713B/VC_redist.x64.exe
Resolving download.visualstudio.microsoft.com (download.visualstudio.microsoft.com)... 2a04:4e42:96::684, 140.248.154.172
Connecting to download.visualstudio.microsoft.com (download.visualstudio.microsoft.com)|2a04:4e42:96::684|:443... connected.
HTTP request sent, awaiting response... 200 OK
Length: 25635768 (24M) [application/octet-stream]
Saving to: ‘vc_redist.x64.exe’

     0K .......... .......... .......... .......... ..........  0% 2.67M 9s
    50K .......... .......... .......... .......... ..........  0% 10.7M 6s
   100K .......... .......... .......... .......... ..........  0% 4.63M 6s
   150K .......... .......... .......... .......... ..........  0% 11.2M 5s
   200K .......... .......... .......... .......... ..........  0% 5.28M 5s
   250K .......... .......... .......... .......... ..........  1% 27.3M 4s
   300K .......... .......... .......... .......... ..........  1% 12.5M 4s
   350K .......... .......... .......... .......... ..........  1% 5.41M 4s
   400K .......... .......... .......... .......... ..........  1% 20.8M 4s
   450K .......... .......... .......... .......... ..........  1% 14.5M 3s
   500K .......... .......... .......... .......... ..........  2% 6.08M 3s
   550K .......... .......... .......... .......... ..........  2% 43.0M 3s
   600K .......... .......... .......... .......... ..........  2% 24.8M 3s
   650K .......... .......... .......... .......... ..........  2% 42.9M 3s
   700K .......... .......... .......... .......... ..........  2% 15.6M 3s
   750K .......... .......... .......... .......... ..........  3% 5.61M 3s
   800K .......... .......... .......... .......... ..........  3% 23.7M 3s
   850K .......... .......... .......... .......... ..........  3%  154M 3s
   900K .......... .......... .......... .......... ..........  3% 88.0M 2s
   950K .......... .......... .......... .......... ..........  3% 98.7M 2s
  1000K .......... .......... .......... .......... ..........  4% 62.0M 2s
  1050K .......... .......... .......... .......... ..........  4%  120M 2s
  1100K .......... .......... .......... .......... ..........  4% 21.1M 2s
  1150K .......... .......... .......... .......... ..........  4% 6.22M 2s
  1200K .......... .......... .......... .......... ..........  4%  145M 2s
  1250K .......... .......... .......... .......... ..........  5%  116M 2s
  1300K .......... .......... .......... .......... ..........  5% 31.0M 2s
  1350K .......... .......... .......... .......... ..........  5% 74.2M 2s
  1400K .......... .......... .......... .......... ..........  5% 66.6M 2s
  1450K .......... .......... .......... .......... ..........  5%  166M 2s
  1500K .......... .......... .......... .......... ..........  6% 93.2M 2s
  1550K .......... .......... .......... .......... ..........  6% 99.8M 2s
  1600K .......... .......... .......... .......... ..........  6%  192M 2s
  1650K .......... .......... .......... .......... ..........  6%  102M 2s
  1700K .......... .......... .......... .......... ..........  6%  170M 1s
  1750K .......... .......... .......... .......... ..........  7% 86.5M 1s
  1800K .......... .......... .......... .......... ..........  7%  111M 1s
  1850K .......... .......... .......... .......... ..........  7% 6.07M 1s
  1900K .......... .......... .......... .......... ..........  7% 43.3M 1s
  1950K .......... .......... .......... .......... ..........  7%  109M 1s
  2000K .......... .......... .......... .......... ..........  8%  173M 1s
  2050K .......... .......... .......... .......... ..........  8% 62.0M 1s
  2100K .......... .......... .......... .......... ..........  8%  168M 1s
  2150K .......... .......... .......... .......... ..........  8%  139M 1s
  2200K .......... .......... .......... .......... ..........  8%  137M 1s
  2250K .......... .......... .......... .......... ..........  9% 60.4M 1s
  2300K .......... .......... .......... .......... ..........  9% 99.0M 1s
  2350K .......... .......... .......... .......... ..........  9% 68.7M 1s
  2400K .......... .......... .......... .......... ..........  9%  192M 1s
  2450K .......... .......... .......... .......... ..........  9% 87.8M 1s
  2500K .......... .......... .......... .......... .......... 10%  187M 1s
  2550K .......... .......... .......... .......... .......... 10%  103M 1s
  2600K .......... .......... .......... .......... .......... 10%  165M 1s
  2650K .......... .......... .......... .......... .......... 10% 6.46M 1s
  2700K .......... .......... .......... .......... .......... 10%  147M 1s
  2750K .......... .......... .......... .......... .......... 11% 83.7M 1s
  2800K .......... .......... .......... .......... .......... 11% 72.2M 1s
  2850K .......... .......... .......... .......... .......... 11%  150M 1s
  2900K .......... .......... .......... .......... .......... 11%  102M 1s
  2950K .......... .......... .......... .......... .......... 11%  100M 1s
  3000K .......... .......... .......... .......... .......... 12%  168M 1s
  3050K .......... .......... .......... .......... .......... 12%  101M 1s
  3100K .......... .......... .......... .......... .......... 12%  151M 1s
  3150K .......... .......... .......... .......... .......... 12%  101M 1s
  3200K .......... .......... .......... .......... .......... 12% 65.3M 1s
  3250K .......... .......... .......... .......... .......... 13% 95.3M 1s
  3300K .......... .......... .......... .......... .......... 13%  189M 1s
  3350K .......... .......... .......... .......... .......... 13%  187M 1s
  3400K .......... .......... .......... .......... .......... 13% 88.5M 1s
  3450K .......... .......... .......... .......... .......... 13% 95.7M 1s
  3500K .......... .......... .......... .......... .......... 14%  186M 1s
  3550K .......... .......... .......... .......... .......... 14% 65.8M 1s
  3600K .......... .......... .......... .......... .......... 14%  180M 1s
  3650K .......... .......... .......... .......... .......... 14% 96.8M 1s
  3700K .......... .......... .......... .......... .......... 14%  148M 1s
  3750K .......... .......... .......... .......... .......... 15% 69.6M 1s
  3800K .......... .......... .......... .......... .......... 15%  167M 1s
  3850K .......... .......... .......... .......... .......... 15%  211M 1s
  3900K .......... .......... .......... .......... .......... 15% 89.3M 1s
  3950K .......... .......... .......... .......... .......... 15% 91.9M 1s
  4000K .......... .......... .......... .......... .......... 16% 14.6M 1s
  4050K .......... .......... .......... .......... .......... 16% 41.0M 1s
  4100K .......... .......... .......... .......... .......... 16% 88.5M 1s
  4150K .......... .......... .......... .......... .......... 16%  197M 1s
  4200K .......... .......... .......... .......... .......... 16% 65.5M 1s
  4250K .......... .......... .......... .......... .......... 17%  472M 1s
  4300K .......... .......... .......... .......... .......... 17% 72.8M 1s
  4350K .......... .......... .......... .......... .......... 17% 88.8M 1s
  4400K .......... .......... .......... .......... .......... 17%  188M 1s
  4450K .......... .......... .......... .......... .......... 17%  101M 1s
  4500K .......... .......... .......... .......... .......... 18%  149M 1s
  4550K .......... .......... .......... .......... .......... 18%  109M 1s
  4600K .......... .......... .......... .......... .......... 18%  167M 1s
  4650K .......... .......... .......... .......... .......... 18% 65.4M 1s
  4700K .......... .......... .......... .......... .......... 18% 95.1M 1s
  4750K .......... .......... .......... .......... .......... 19%  145M 1s
  4800K .......... .......... .......... .......... .......... 19%  101M 1s
  4850K .......... .......... .......... .......... .......... 19% 94.2M 1s
  4900K .......... .......... .......... .......... .......... 19%  200M 1s
  4950K .......... .......... .......... .......... .......... 19%  100M 1s
  5000K .......... .......... .......... .......... .......... 20%  165M 1s
  5050K .......... .......... .......... .......... .......... 20% 90.0M 1s
  5100K .......... .......... .......... .......... .......... 20%  211M 1s
  5150K .......... .......... .......... .......... .......... 20% 48.7M 1s
  5200K .......... .......... .......... .......... .......... 20%  193M 1s
  5250K .......... .......... .......... .......... .......... 21%  146M 1s
  5300K .......... .......... .......... .......... .......... 21%  102M 1s
  5350K .......... .......... .......... .......... .......... 21%  193M 1s
  5400K .......... .......... .......... .......... .......... 21% 66.0M 1s
  5450K .......... .......... .......... .......... .......... 21%  481M 1s
  5500K .......... .......... .......... .......... .......... 22% 68.6M 1s
  5550K .......... .......... .......... .......... .......... 22%  134M 1s
  5600K .......... .......... .......... .......... .......... 22% 75.8M 1s
  5650K .......... .......... .......... .......... .......... 22%  209M 1s
  5700K .......... .......... .......... .......... .......... 22% 54.7M 1s
  5750K .......... .......... .......... .......... .......... 23%  115M 1s
  5800K .......... .......... .......... .......... .......... 23% 89.5M 1s
  5850K .......... .......... .......... .......... .......... 23%  162M 1s
  5900K .......... .......... .......... .......... .......... 23%  218M 1s
  5950K .......... .......... .......... .......... .......... 23% 48.3M 1s
  6000K .......... .......... .......... .......... .......... 24%  461M 1s
  6050K .......... .......... .......... .......... .......... 24%  125M 1s
  6100K .......... .......... .......... .......... .......... 24% 63.0M 1s
  6150K .......... .......... .......... .......... .......... 24%  188M 1s
  6200K .......... .......... .......... .......... .......... 24%  187M 1s
  6250K .......... .......... .......... .......... .......... 25% 82.0M 1s
  6300K .......... .......... .......... .......... .......... 25%  101M 1s
  6350K .......... .......... .......... .......... .......... 25% 96.7M 1s
  6400K .......... .......... .......... .......... .......... 25%  101M 1s
  6450K .......... .......... .......... .......... .......... 25%  164M 0s
  6500K .......... .......... .......... .......... .......... 26% 94.3M 0s
  6550K .......... .......... .......... .......... .......... 26%  169M 0s
  6600K .......... .......... .......... .......... .......... 26%  204M 0s
  6650K .......... .......... .......... .......... .......... 26% 49.6M 0s
  6700K .......... .......... .......... .......... .......... 26%  191M 0s
  6750K .......... .......... .......... .......... .......... 27%  141M 0s
  6800K .......... .......... .......... .......... .......... 27%  104M 0s
  6850K .......... .......... .......... .......... .......... 27%  191M 0s
  6900K .......... .......... .......... .......... .......... 27% 65.9M 0s
  6950K .......... .......... .......... .......... .......... 27%  191M 0s
  7000K .......... .......... .......... .......... .......... 28% 87.3M 0s
  7050K .......... .......... .......... .......... .......... 28%  101M 0s
  7100K .......... .......... .......... .......... .......... 28%  171M 0s
  7150K .......... .......... .......... .......... .......... 28%  102M 0s
  7200K .......... .......... .......... .......... .......... 28% 94.3M 0s
  7250K .......... .......... .......... .......... .......... 29%  184M 0s
  7300K .......... .......... .......... .......... .......... 29% 95.1M 0s
  7350K .......... .......... .......... .......... .......... 29% 89.4M 0s
  7400K .......... .......... .......... .......... .......... 29%  101M 0s
  7450K .......... .......... .......... .......... .......... 29%  167M 0s
  7500K .......... .......... .......... .......... .......... 30% 1.91M 0s
  7550K .......... .......... .......... .......... .......... 30% 95.7M 0s
  7600K .......... .......... .......... .......... .......... 30%  177M 0s
  7650K .......... .......... .......... .......... .......... 30%  188M 0s
  7700K .......... .......... .......... .......... .......... 30%  180M 0s
  7750K .......... .......... .......... .......... .......... 31%  409M 0s
  7800K .......... .......... .......... .......... .......... 31%  442M 0s
  7850K .......... .......... .......... .......... .......... 31%  459M 0s
  7900K .......... .......... .......... .......... .......... 31% 67.6M 0s
  7950K .......... .......... .......... .......... .......... 31%  414M 0s
  8000K .......... .......... .......... .......... .......... 32%  135M 0s
  8050K .......... .......... .......... .......... .......... 32%  176M 0s
  8100K .......... .......... .......... .......... .......... 32%  424M 0s
  8150K .......... .......... .......... .......... .......... 32%  467M 0s
  8200K .......... .......... .......... .......... .......... 32%  438M 0s
  8250K .......... .......... .......... .......... .......... 33%  434M 0s
  8300K .......... .......... .......... .......... .......... 33%  348M 0s
  8350K .......... .......... .......... .......... .......... 33%  462M 0s
  8400K .......... .......... .......... .......... .......... 33%  460M 0s
  8450K .......... .......... .......... .......... .......... 33%  448M 0s
  8500K .......... .......... .......... .......... .......... 34%  424M 0s
  8550K .......... .......... .......... .......... .......... 34%  448M 0s
  8600K .......... .......... .......... .......... .......... 34%  461M 0s
  8650K .......... .......... .......... .......... .......... 34%  444M 0s
  8700K .......... .......... .......... .......... .......... 34%  307M 0s
  8750K .......... .......... .......... .......... .......... 35%  436M 0s
  8800K .......... .......... .......... .......... .......... 35%  441M 0s
  8850K .......... .......... .......... .......... .......... 35%  451M 0s
  8900K .......... .......... .......... .......... .......... 35%  460M 0s
  8950K .......... .......... .......... .......... .......... 35%  414M 0s
  9000K .......... .......... .......... .......... .......... 36%  363M 0s
  9050K .......... .......... .......... .......... .......... 36%  407M 0s
  9100K .......... .......... .......... .......... .......... 36%  319M 0s
  9150K .......... .......... .......... .......... .......... 36%  393M 0s
  9200K .......... .......... .......... .......... .......... 36% 6.35M 0s
  9250K .......... .......... .......... .......... .......... 37%  203M 0s
  9300K .......... .......... .......... .......... .......... 37%  438M 0s
  9350K .......... .......... .......... .......... .......... 37%  229M 0s
  9400K .......... .......... .......... .......... .......... 37%  413M 0s
  9450K .......... .......... .......... .......... .......... 37%  362M 0s
  9500K .......... .......... .......... .......... .......... 38%  314M 0s
  9550K .......... .......... .......... .......... .......... 38%  402M 0s
  9600K .......... .......... .......... .......... .......... 38%  407M 0s
  9650K .......... .......... .......... .......... .......... 38% 25.6M 0s
  9700K .......... .......... .......... .......... .......... 38% 99.3M 0s
  9750K .......... .......... .......... .......... .......... 39%  183M 0s
  9800K .......... .......... .......... .......... .......... 39%  207M 0s
  9850K .......... .......... .......... .......... .......... 39%  167M 0s
  9900K .......... .......... .......... .......... .......... 39%  304M 0s
  9950K .......... .......... .......... .......... .......... 39%  415M 0s
 10000K .......... .......... .......... .......... .......... 40%  347M 0s
 10050K .......... .......... .......... .......... .......... 40%  271M 0s
 10100K .......... .......... .......... .......... .......... 40%  292M 0s
 10150K .......... .......... .......... .......... .......... 40%  287M 0s
 10200K .......... .......... .......... .......... .......... 40% 22.9M 0s
 10250K .......... .......... .......... .......... .......... 41%  385M 0s
 10300K .......... .......... .......... .......... .......... 41%  425M 0s
 10350K .......... .......... .......... .......... .......... 41%  296M 0s
 10400K .......... .......... .......... .......... .......... 41%  366M 0s
 10450K .......... .......... .......... .......... .......... 41%  419M 0s
 10500K .......... .......... .......... .......... .......... 42%  414M 0s
 10550K .......... .......... .......... .......... .......... 42%  410M 0s
 10600K .......... .......... .......... .......... .......... 42%  455M 0s
 10650K .......... .......... .......... .......... .......... 42%  443M 0s
 10700K .......... .......... .......... .......... .......... 42%  461M 0s
 10750K .......... .......... .......... .......... .......... 43%  328M 0s
 10800K .......... .......... .......... .......... .......... 43%  461M 0s
 10850K .......... .......... .......... .......... .......... 43%  423M 0s
 10900K .......... .......... .......... .......... .......... 43%  450M 0s
 10950K .......... .......... .......... .......... .......... 43%  468M 0s
 11000K .......... .......... .......... .......... .......... 44%  434M 0s
 11050K .......... .......... .......... .......... .......... 44%  466M 0s
 11100K .......... .......... .......... .......... .......... 44%  442M 0s
 11150K .......... .......... .......... .......... .......... 44%  336M 0s
 11200K .......... .......... .......... .......... .......... 44%  461M 0s
 11250K .......... .......... .......... .......... .......... 45%  435M 0s
 11300K .......... .......... .......... .......... .......... 45%  456M 0s
 11350K .......... .......... .......... .......... .......... 45%  463M 0s
 11400K .......... .......... .......... .......... .......... 45%  473M 0s
 11450K .......... .......... .......... .......... .......... 45%  454M 0s
 11500K .......... .......... .......... .......... .......... 46%  469M 0s
 11550K .......... .......... .......... .......... .......... 46%  354M 0s
 11600K .......... .......... .......... .......... .......... 46%  421M 0s
 11650K .......... .......... .......... .......... .......... 46%  456M 0s
 11700K .......... .......... .......... .......... .......... 46%  455M 0s
 11750K .......... .......... .......... .......... .......... 47%  469M 0s
 11800K .......... .......... .......... .......... .......... 47%  420M 0s
 11850K .......... .......... .......... .......... .......... 47%  454M 0s
 11900K .......... .......... .......... .......... .......... 47%  461M 0s
 11950K .......... .......... .......... .......... .......... 47%  346M 0s
 12000K .......... .......... .......... .......... .......... 48%  460M 0s
 12050K .......... .......... .......... .......... .......... 48%  418M 0s
 12100K .......... .......... .......... .......... .......... 48%  437M 0s
 12150K .......... .......... .......... .......... .......... 48%  460M 0s
 12200K .......... .......... .......... .......... .......... 48%  439M 0s
 12250K .......... .......... .......... .......... .......... 49%  410M 0s
 12300K .......... .......... .......... .......... .......... 49%  358M 0s
 12350K .......... .......... .......... .......... .......... 49%  422M 0s
 12400K .......... .......... .......... .......... .......... 49%  453M 0s
 12450K .......... .......... .......... .......... .......... 49%  441M 0s
 12500K .......... .......... .......... .......... .......... 50%  439M 0s
 12550K .......... .......... .......... .......... .......... 50%  439M 0s
 12600K .......... .......... .......... .......... .......... 50%  464M 0s
 12650K .......... .......... .......... .......... .......... 50%  449M 0s
 12700K .......... .......... .......... .......... .......... 50%  332M 0s
 12750K .......... .......... .......... .......... .......... 51%  461M 0s
 12800K .......... .......... .......... .......... .......... 51%  446M 0s
 12850K .......... .......... .......... .......... .......... 51%  388M 0s
 12900K .......... .......... .......... .......... .......... 51%  440M 0s
 12950K .......... .......... .......... .......... .......... 51%  416M 0s
 13000K .......... .......... .......... .......... .......... 52%  459M 0s
 13050K .......... .......... .......... .......... .......... 52%  444M 0s
 13100K .......... .......... .......... .......... .......... 52%  336M 0s
 13150K .......... .......... .......... .......... .......... 52%  453M 0s
 13200K .......... .......... .......... .......... .......... 52%  466M 0s
 13250K .......... .......... .......... .......... .......... 53%  444M 0s
 13300K .......... .......... .......... .......... .......... 53%  429M 0s
 13350K .......... .......... .......... .......... .......... 53%  453M 0s
 13400K .......... .......... .......... .......... .......... 53%  463M 0s
 13450K .......... .......... .......... .......... .......... 53%  454M 0s
 13500K .......... .......... .......... .......... .......... 54%  459M 0s
 13550K .......... .......... .......... .......... .......... 54%  355M 0s
 13600K .......... .......... .......... .......... .......... 54%  451M 0s
 13650K .......... .......... .......... .......... .......... 54%  113M 0s
 13700K .......... .......... .......... .......... .......... 54% 94.5M 0s
 13750K .......... .......... .......... .......... .......... 55%  176M 0s
 13800K .......... .......... .......... .......... .......... 55% 98.1M 0s
 13850K .......... .......... .......... .......... .......... 55% 87.1M 0s
 13900K .......... .......... .......... .......... .......... 55%  192M 0s
 13950K .......... .......... .......... .......... .......... 55% 95.0M 0s
 14000K .......... .......... .......... .......... .......... 56% 87.4M 0s
 14050K .......... .......... .......... .......... .......... 56%  198M 0s
 14100K .......... .......... .......... .......... .......... 56%  101M 0s
 14150K .......... .......... .......... .......... .......... 56% 97.2M 0s
 14200K .......... .......... .......... .......... .......... 56%  176M 0s
 14250K .......... .......... .......... .......... .......... 57% 98.0M 0s
 14300K .......... .......... .......... .......... .......... 57% 96.0M 0s
 14350K .......... .......... .......... .......... .......... 57% 95.9M 0s
 14400K .......... .......... .......... .......... .......... 57%  167M 0s
 14450K .......... .......... .......... .......... .......... 57% 93.4M 0s
 14500K .......... .......... .......... .......... .......... 58%  103M 0s
 14550K .......... .......... .......... .......... .......... 58% 87.3M 0s
 14600K .......... .......... .......... .......... .......... 58%  194M 0s
 14650K .......... .......... .......... .......... .......... 58%  102M 0s
 14700K .......... .......... .......... .......... .......... 58%  166M 0s
 14750K .......... .......... .......... .......... .......... 59% 65.6M 0s
 14800K .......... .......... .......... .......... .......... 59%  158M 0s
 14850K .......... .......... .......... .......... .......... 59%  107M 0s
 14900K .......... .......... .......... .......... .......... 59%  154M 0s
 14950K .......... .......... .......... .......... .......... 59% 99.0M 0s
 15000K .......... .......... .......... .......... .......... 60% 66.0M 0s
 15050K .......... .......... .......... .......... .......... 60%  450M 0s
 15100K .......... .......... .......... .......... .......... 60%  118M 0s
 15150K .......... .......... .......... .......... .......... 60% 88.7M 0s
 15200K .......... .......... .......... .......... .......... 60%  101M 0s
 15250K .......... .......... .......... .......... .......... 61%  165M 0s
 15300K .......... .......... .......... .......... .......... 61% 95.5M 0s
 15350K .......... .......... .......... .......... .......... 61%  101M 0s
 15400K .......... .......... .......... .......... .......... 61% 94.6M 0s
 15450K .......... .......... .......... .......... .......... 61% 94.5M 0s
 15500K .......... .......... .......... .......... .......... 62%  188M 0s
 15550K .......... .......... .......... .......... .......... 62% 94.9M 0s
 15600K .......... .......... .......... .......... .......... 62%  165M 0s
 15650K .......... .......... .......... .......... .......... 62% 95.7M 0s
 15700K .......... .......... .......... .......... .......... 62%  100M 0s
 15750K .......... .......... .......... .......... .......... 63%  168M 0s
 15800K .......... .......... .......... .......... .......... 63% 62.8M 0s
 15850K .......... .......... .......... .......... .......... 63%  189M 0s
 15900K .......... .......... .......... .......... .......... 63%  186M 0s
 15950K .......... .......... .......... .......... .......... 63% 49.0M 0s
 16000K .......... .......... .......... .......... .......... 64%  190M 0s
 16050K .......... .......... .......... .......... .......... 64%  179M 0s
 16100K .......... .......... .......... .......... .......... 64%  175M 0s
 16150K .......... .......... .......... .......... .......... 64% 91.2M 0s
 16200K .......... .......... .......... .......... .......... 64% 68.1M 0s
 16250K .......... .......... .......... .......... .......... 65%  162M 0s
 16300K .......... .......... .......... .......... .......... 65%  170M 0s
 16350K .......... .......... .......... .......... .......... 65%  101M 0s
 16400K .......... .......... .......... .......... .......... 65% 64.9M 0s
 16450K .......... .......... .......... .......... .......... 65%  451M 0s
 16500K .......... .......... .......... .......... .......... 66%  112M 0s
 16550K .......... .......... .......... .......... .......... 66% 89.5M 0s
 16600K .......... .......... .......... .......... .......... 66%  212M 0s
 16650K .......... .......... .......... .......... .......... 66% 66.4M 0s
 16700K .......... .......... .......... .......... .......... 66%  166M 0s
 16750K .......... .......... .......... .......... .......... 67%  100M 0s
 16800K .......... .......... .......... .......... .......... 67%  168M 0s
 16850K .......... .......... .......... .......... .......... 67% 64.9M 0s
 16900K .......... .......... .......... .......... .......... 67%  196M 0s
 16950K .......... .......... .......... .......... .......... 67%  167M 0s
 17000K .......... .......... .......... .......... .......... 68% 65.7M 0s
 17050K .......... .......... .......... .......... .......... 68%  193M 0s
 17100K .......... .......... .......... .......... .......... 68% 92.2M 0s
 17150K .......... .......... .......... .......... .......... 68% 93.2M 0s
 17200K .......... .......... .......... .......... .......... 68%  160M 0s
 17250K .......... .......... .......... .......... .......... 69% 67.4M 0s
 17300K .......... .......... .......... .......... .......... 69%  177M 0s
 17350K .......... .......... .......... .......... .......... 69%  180M 0s
 17400K .......... .......... .......... .......... .......... 69%  104M 0s
 17450K .......... .......... .......... .......... .......... 69%  161M 0s
 17500K .......... .......... .......... .......... .......... 70% 67.0M 0s
 17550K .......... .......... .......... .......... .......... 70% 88.9M 0s
 17600K .......... .......... .......... .......... .......... 70%  159M 0s
 17650K .......... .......... .......... .......... .......... 70%  203M 0s
 17700K .......... .......... .......... .......... .......... 70% 64.3M 0s
 17750K .......... .......... .......... .......... .......... 71%  215M 0s
 17800K .......... .......... .......... .......... .......... 71% 87.4M 0s
 17850K .......... .......... .......... .......... .......... 71%  190M 0s
 17900K .......... .......... .......... .......... .......... 71% 97.1M 0s
 17950K .......... .......... .......... .......... .......... 71%  102M 0s
 18000K .......... .......... .......... .......... .......... 72% 95.5M 0s
 18050K .......... .......... .......... .......... .......... 72%  169M 0s
 18100K .......... .......... .......... .......... .......... 72% 65.4M 0s
 18150K .......... .......... .......... .......... .......... 72%  455M 0s
 18200K .......... .......... .......... .......... .......... 72%  110M 0s
 18250K .......... .......... .......... .......... .......... 73%  102M 0s
 18300K .......... .......... .......... .......... .......... 73% 94.3M 0s
 18350K .......... .......... .......... .......... .......... 73% 94.8M 0s
 18400K .......... .......... .......... .......... .......... 73%  167M 0s
 18450K .......... .......... .......... .......... .......... 73%  101M 0s
 18500K .......... .......... .......... .......... .......... 74%  166M 0s
 18550K .......... .......... .......... .......... .......... 74% 65.8M 0s
 18600K .......... .......... .......... .......... .......... 74%  188M 0s
 18650K .......... .......... .......... .......... .......... 74%  171M 0s
 18700K .......... .......... .......... .......... .......... 74% 65.7M 0s
 18750K .......... .......... .......... .......... .......... 75%  162M 0s
 18800K .......... .......... .......... .......... .......... 75% 66.7M 0s
 18850K .......... .......... .......... .......... .......... 75%  161M 0s
 18900K .......... .......... .......... .......... .......... 75%  197M 0s
 18950K .......... .......... .......... .......... .......... 75% 89.3M 0s
 19000K .......... .......... .......... .......... .......... 76%  207M 0s
 19050K .......... .......... .......... .......... .......... 76%  102M 0s
 19100K .......... .......... .......... .......... .......... 76% 62.9M 0s
 19150K .......... .......... .......... .......... .......... 76%  183M 0s
 19200K .......... .......... .......... .......... .......... 76% 96.8M 0s
 19250K .......... .......... .......... .......... .......... 77%  165M 0s
 19300K .......... .......... .......... .......... .......... 77%  102M 0s
 19350K .......... .......... .......... .......... .......... 77%  163M 0s
 19400K .......... .......... .......... .......... .......... 77% 96.8M 0s
 19450K .......... .......... .......... .......... .......... 77%  100M 0s
 19500K .......... .......... .......... .......... .......... 78% 89.3M 0s
 19550K .......... .......... .......... .......... .......... 78% 93.5M 0s
 19600K .......... .......... .......... .......... .......... 78%  190M 0s
 19650K .......... .......... .......... .......... .......... 78%  101M 0s
 19700K .......... .......... .......... .......... .......... 78% 95.3M 0s
 19750K .......... .......... .......... .......... .......... 79%  167M 0s
 19800K .......... .......... .......... .......... .......... 79%  101M 0s
 19850K .......... .......... .......... .......... .......... 79%  166M 0s
 19900K .......... .......... .......... .......... .......... 79% 88.7M 0s
 19950K .......... .......... .......... .......... .......... 79%  101M 0s
 20000K .......... .......... .......... .......... .......... 80%  101M 0s
 20050K .......... .......... .......... .......... .......... 80% 63.1M 0s
 20100K .......... .......... .......... .......... .......... 80%  187M 0s
 20150K .......... .......... .......... .......... .......... 80%  181M 0s
 20200K .......... .......... .......... .......... .......... 80% 97.9M 0s
 20250K .......... .......... .......... .......... .......... 81%  156M 0s
 20300K .......... .......... .......... .......... .......... 81%  105M 0s
 20350K .......... .......... .......... .......... .......... 81% 62.7M 0s
 20400K .......... .......... .......... .......... .......... 81%  189M 0s
 20450K .......... .......... .......... .......... .......... 81%  169M 0s
 20500K .......... .......... .......... .......... .......... 82% 65.1M 0s
 20550K .......... .......... .......... .......... .......... 82%  194M 0s
 20600K .......... .......... .......... .......... .......... 82%  169M 0s
 20650K .......... .......... .......... .......... .......... 82% 65.3M 0s
 20700K .......... .......... .......... .......... .......... 82%  451M 0s
 20750K .......... .......... .......... .......... .......... 83% 72.9M 0s
 20800K .......... .......... .......... .......... .......... 83%  168M 0s
 20850K .......... .......... .......... .......... .......... 83%  102M 0s
 20900K .......... .......... .......... .......... .......... 83% 91.8M 0s
 20950K .......... .......... .......... .......... .......... 83%  179M 0s
 21000K .......... .......... .......... .......... .......... 84%  101M 0s
 21050K .......... .......... .......... .......... .......... 84% 94.8M 0s
 21100K .......... .......... .......... .......... .......... 84%  164M 0s
 21150K .......... .......... .......... .......... .......... 84% 94.6M 0s
 21200K .......... .......... .......... .......... .......... 84% 66.2M 0s
 21250K .......... .......... .......... .......... .......... 85%  158M 0s
 21300K .......... .......... .......... .......... .......... 85%  199M 0s
 21350K .......... .......... .......... .......... .......... 85%  102M 0s
 21400K .......... .......... .......... .......... .......... 85% 88.7M 0s
 21450K .......... .......... .......... .......... .......... 85%  180M 0s
 21500K .......... .......... .......... .......... .......... 86%  104M 0s
 21550K .......... .......... .......... .......... .......... 86% 94.2M 0s
 21600K .......... .......... .......... .......... .......... 86% 62.7M 0s
 21650K .......... .......... .......... .......... .......... 86%  169M 0s
 21700K .......... .......... .......... .......... .......... 86%  201M 0s
 21750K .......... .......... .......... .......... .......... 87% 98.6M 0s
 21800K .......... .......... .......... .......... .......... 87%  161M 0s
 21850K .......... .......... .......... .......... .......... 87%  102M 0s
 21900K .......... .......... .......... .......... .......... 87% 88.3M 0s
 21950K .......... .......... .......... .......... .......... 87%  102M 0s
 22000K .......... .......... .......... .......... .......... 88%  167M 0s
 22050K .......... .......... .......... .......... .......... 88% 65.7M 0s
 22100K .......... .......... .......... .......... .......... 88%  185M 0s
 22150K .......... .......... .......... .......... .......... 88%  172M 0s
 22200K .......... .......... .......... .......... .......... 88% 98.7M 0s
 22250K .......... .......... .......... .......... .......... 89% 96.2M 0s
 22300K .......... .......... .......... .......... .......... 89%  160M 0s
 22350K .......... .......... .......... .......... .......... 89% 89.8M 0s
 22400K .......... .......... .......... .......... .......... 89%  111M 0s
 22450K .......... .......... .......... .......... .......... 89% 92.4M 0s
 22500K .......... .......... .......... .......... .......... 90%  169M 0s
 22550K .......... .......... .......... .......... .......... 90% 98.0M 0s
 22600K .......... .......... .......... .......... .......... 90% 96.0M 0s
 22650K .......... .......... .......... .......... .......... 90% 87.3M 0s
 22700K .......... .......... .......... .......... .......... 90% 98.7M 0s
 22750K .......... .......... .......... .......... .......... 91% 99.8M 0s
 22800K .......... .......... .......... .......... .......... 91%  199M 0s
 22850K .......... .......... .......... .......... .......... 91% 85.3M 0s
 22900K .......... .......... .......... .......... .......... 91%  106M 0s
 22950K .......... .......... .......... .......... .......... 91%  161M 0s
 23000K .......... .......... .......... .......... .......... 92%  191M 0s
 23050K .......... .......... .......... .......... .......... 92% 88.0M 0s
 23100K .......... .......... .......... .......... .......... 92% 94.8M 0s
 23150K .......... .......... .......... .......... .......... 92% 93.9M 0s
 23200K .......... .......... .......... .......... .......... 92%  103M 0s
 23250K .......... .......... .......... .......... .......... 93%  189M 0s
 23300K .......... .......... .......... .......... .......... 93% 66.4M 0s
 23350K .......... .......... .......... .......... .......... 93%  433M 0s
 23400K .......... .......... .......... .......... .......... 93% 73.2M 0s
 23450K .......... .......... .......... .......... .......... 93% 95.1M 0s
 23500K .......... .......... .......... .......... .......... 94%  165M 0s
 23550K .......... .......... .......... .......... .......... 94%  219M 0s
 23600K .......... .......... .......... .......... .......... 94% 83.3M 0s
 23650K .......... .......... .......... .......... .......... 94%  109M 0s
 23700K .......... .......... .......... .......... .......... 94% 89.1M 0s
 23750K .......... .......... .......... .......... .......... 95%  102M 0s
 23800K .......... .......... .......... .......... .......... 95% 94.4M 0s
 23850K .......... .......... .......... .......... .......... 95%  162M 0s
 23900K .......... .......... .......... .......... .......... 95%  150M 0s
 23950K .......... .......... .......... .......... .......... 95%  100M 0s
 24000K .......... .......... .......... .......... .......... 96%  112M 0s
 24050K .......... .......... .......... .......... .......... 96% 93.5M 0s
 24100K .......... .......... .......... .......... .......... 96% 3.15M 0s
 24150K .......... .......... .......... .......... .......... 96%  365M 0s
 24200K .......... .......... .......... .......... .......... 96%  456M 0s
 24250K .......... .......... .......... .......... .......... 97% 51.9M 0s
 24300K .......... .......... .......... .......... .......... 97%  350M 0s
 24350K .......... .......... .......... .......... .......... 97% 31.6M 0s
 24400K .......... .......... .......... .......... .......... 97%  454M 0s
 24450K .......... .......... .......... .......... .......... 97%  246M 0s
 24500K .......... .......... .......... .......... .......... 98%  207M 0s
 24550K .......... .......... .......... .......... .......... 98%  177M 0s
 24600K .......... .......... .......... .......... .......... 98%  206M 0s
 24650K .......... .......... .......... .......... .......... 98%  205M 0s
 24700K .......... .......... .......... .......... .......... 98% 47.0M 0s
 24750K .......... .......... .......... .......... .......... 99%  355M 0s
 24800K .......... .......... .......... .......... .......... 99% 77.1M 0s
 24850K .......... .......... .......... .......... .......... 99%  438M 0s
 24900K .......... .......... .......... .......... .......... 99% 58.7M 0s
 24950K .......... .......... .......... .......... .......... 99%  352M 0s
 25000K .......... .......... .......... ....                 100%  474M=0.4s

2026-09-29 18:48:33 (69.3 MB/s) - ‘vc_redist.x64.exe’ saved [25635768/25635768]

Executing cd /home/gregory/.cache/winetricks/vcrun2022
------------------------------------------------------
SHA256 mismatch!

URL: https://aka.ms/vs/17/release/vc_redist.x64.exe
Downloaded: cc0ff0eb1dc3f5188ae6300faef32bf5beeba4bdd6e8e445a9184072096b713b
Expected: 4dfe83c91124cd542f4222fe2c396cabeac617bb6f59bdcbdf89fd6f0df0a32f

This is often the result of an updated package such as vcrun2019.
If you are willing to accept the risk, you can bypass this check.
Alternatively, you may use the --force option to ignore this check entirely.

Continue anyway?
------------------------------------------------------
------------------------------------------------------
Unattended mode, not prompting for confirmation
------------------------------------------------------
Executing wine vc_redist.x64.exe /q
Provisioned.

=== Consumption (run type 0) ===
consumption: FAIL - exit 1, output/error file missing. Work dir: /tmp/tmp.q9eCKvDlOw/work

=== Soil (run type 1) ===
soil: FAIL - exit 1, output/error file missing. Work dir: /tmp/tmp.q9eCKvDlOw/work

=== Mortality (run type 2) ===
mortality: FAIL - exit 24. Work dir: /tmp/tmp.q9eCKvDlOw/work

=== Summary ===
Wine: wine-9.0 (Ubuntu 9.0~repack-4build3)
WINEARCH: win64
vcrun2022: provisioned via winetricks
Consumption: FAIL
Soil: FAIL
Mortality: FAIL
```

</details>

## Full corrected fresh-prefix console output

<details>
<summary>Complete combined stdout/stderr; exit code 0</summary>

```text
Work directory (kept): /tmp/tmp.WDSM21nPRu
wine: created the configuration directory '/tmp/tmp.WDSM21nPRu/wineprefix'
wine: configuration in L"/tmp/tmp.WDSM21nPRu/wineprefix" has been updated.
=== Environment ===
uname: Linux Gregory-Threadripper 6.17.0-20-generic #20~24.04.1-Ubuntu SMP PREEMPT_DYNAMIC Thu Mar 19 01:28:37 UTC 2 x86_64 x86_64 x86_64 GNU/Linux
wine: wine-9.0 (Ubuntu 9.0~repack-4build3)
winetricks: 20240105 - sha256sum: 17da748ce874adb2ee9fed79d2550c0c58e57d5969cc779a8779301350625c55
WINEPREFIX: /tmp/tmp.WDSM21nPRu/wineprefix
WINEARCH: win64
Bundle dir: /home/gregory/PycharmProjects/FuelAnalyst/src/fuel_analyst/supporting_data/fofem_694
FOFEM_DATA: Z:\tmp\tmp.WDSM21nPRu\app

=== Preflight: before winetricks vcrun2022 (expect failure) ===
preflight: UNEXPECTEDLY SUCCEEDED before vcrun2022 provisioning (exit 0).
  This host's Wine prefix may already have a usable VC++ runtime from elsewhere.

=== Provisioning: winetricks vcrun2022 ===
Executing cd /usr/bin
------------------------------------------------------
warning: You are using a 64-bit WINEPREFIX. Note that many verbs only install 32-bit versions of packages. If you encounter problems, please retest in a clean 32-bit WINEPREFIX before reporting a bug.
------------------------------------------------------
Using winetricks 20240105 - sha256sum: 17da748ce874adb2ee9fed79d2550c0c58e57d5969cc779a8779301350625c55 with wine-9.0 (Ubuntu 9.0~repack-4build3) and WINEARCH=win64
Executing w_do_call vcrun2022
------------------------------------------------------
warning: You are using a 64-bit WINEPREFIX. Note that many verbs only install 32-bit versions of packages. If you encounter problems, please retest in a clean 32-bit WINEPREFIX before reporting a bug.
------------------------------------------------------
Executing load_vcrun2022
Using native,builtin override for following DLLs: concrt140 msvcp140 msvcp140_1 msvcp140_2 msvcp140_atomic_wait msvcp140_codecvt_ids vcamp140 vccorlib140 vcomp140 vcruntime140
Executing wine C:\windows\syswow64\regedit.exe /S C:\windows\Temp\override-dll.reg
Executing /usr/lib/wine/wine64 C:\windows\regedit.exe /S C:\windows\Temp\override-dll.reg
------------------------------------------------------
warning: Checksum for /home/gregory/.cache/winetricks/vcrun2022/vc_redist.x86.exe did not match, retrying download
------------------------------------------------------
Executing cd /home/gregory/.cache/winetricks/vcrun2022
Downloading https://aka.ms/vs/17/release/vc_redist.x86.exe to /home/gregory/.cache/winetricks/vcrun2022
--2026-09-29 18:49:55--  https://aka.ms/vs/17/release/vc_redist.x86.exe
Resolving aka.ms (aka.ms)... 184.30.154.152
Connecting to aka.ms (aka.ms)|184.30.154.152|:443... connected.
HTTP request sent, awaiting response... 301 Moved Permanently
Location: https://download.visualstudio.microsoft.com/download/pr/bd1c8d9d-ba95-4eee-bc6e-df1fcc876373/0C09F2611660441084CE0DF425C51C11E147E6447963C3690F97E0B25C55ED64/VC_redist.x86.exe [following]
--2026-09-29 18:49:55--  https://download.visualstudio.microsoft.com/download/pr/bd1c8d9d-ba95-4eee-bc6e-df1fcc876373/0C09F2611660441084CE0DF425C51C11E147E6447963C3690F97E0B25C55ED64/VC_redist.x86.exe
Resolving download.visualstudio.microsoft.com (download.visualstudio.microsoft.com)... 2001:569:139::cfc2:c70b, 2001:569:139::cfc2:c73b, 207.194.199.59, ...
Connecting to download.visualstudio.microsoft.com (download.visualstudio.microsoft.com)|2001:569:139::cfc2:c70b|:443... connected.
HTTP request sent, awaiting response... 200 OK
Length: 13953392 (13M) [application/octet-stream]
Saving to: ‘vc_redist.x86.exe’

     0K .......... .......... .......... .......... ..........  0% 11.6M 1s
    50K .......... .......... .......... .......... ..........  0% 3.29M 3s
   100K .......... .......... .......... .......... ..........  1% 4.80M 3s
   150K .......... .......... .......... .......... ..........  1% 11.7M 2s
   200K .......... .......... .......... .......... ..........  1% 10.4M 2s
   250K .......... .......... .......... .......... ..........  2% 6.91M 2s
   300K .......... .......... .......... .......... ..........  2% 19.5M 2s
   350K .......... .......... .......... .......... ..........  2% 15.4M 2s
   400K .......... .......... .......... .......... ..........  3% 14.0M 2s
   450K .......... .......... .......... .......... ..........  3% 8.21M 2s
   500K .......... .......... .......... .......... ..........  4%  877K 3s
   550K .......... .......... .......... .......... ..........  4% 36.2M 3s
   600K .......... .......... .......... .......... ..........  4% 24.3M 2s
   650K .......... .......... .......... .......... ..........  5% 59.2M 2s
   700K .......... .......... .......... .......... ..........  5% 50.3M 2s
   750K .......... .......... .......... .......... ..........  5% 4.67M 2s
   800K .......... .......... .......... .......... ..........  6% 50.2M 2s
   850K .......... .......... .......... .......... ..........  6% 50.9M 2s
   900K .......... .......... .......... .......... ..........  6% 27.0M 2s
   950K .......... .......... .......... .......... ..........  7% 49.6M 2s
  1000K .......... .......... .......... .......... ..........  7% 5.02M 2s
  1050K .......... .......... .......... .......... ..........  8% 53.2M 2s
  1100K .......... .......... .......... .......... ..........  8% 64.7M 2s
  1150K .......... .......... .......... .......... ..........  8% 53.2M 2s
  1200K .......... .......... .......... .......... ..........  9% 48.6M 1s
  1250K .......... .......... .......... .......... ..........  9% 50.5M 1s
  1300K .......... .......... .......... .......... ..........  9% 42.7M 1s
  1350K .......... .......... .......... .......... .......... 10% 65.5M 1s
  1400K .......... .......... .......... .......... .......... 10% 5.76M 1s
  1450K .......... .......... .......... .......... .......... 11%  150M 1s
  1500K .......... .......... .......... .......... .......... 11% 40.7M 1s
  1550K .......... .......... .......... .......... .......... 11% 53.7M 1s
  1600K .......... .......... .......... .......... .......... 12%  190M 1s
  1650K .......... .......... .......... .......... .......... 12% 45.1M 1s
  1700K .......... .......... .......... .......... .......... 12% 65.6M 1s
  1750K .......... .......... .......... .......... .......... 13% 32.8M 1s
  1800K .......... .......... .......... .......... .......... 13%  143M 1s
  1850K .......... .......... .......... .......... .......... 13% 54.2M 1s
  1900K .......... .......... .......... .......... .......... 14% 50.2M 1s
  1950K .......... .......... .......... .......... .......... 14% 6.29M 1s
  2000K .......... .......... .......... .......... .......... 15%  179M 1s
  2050K .......... .......... .......... .......... .......... 15% 98.8M 1s
  2100K .......... .......... .......... .......... .......... 15% 57.5M 1s
  2150K .......... .......... .......... .......... .......... 16%  144M 1s
  2200K .......... .......... .......... .......... .......... 16% 69.1M 1s
  2250K .......... .......... .......... .......... .......... 16%  140M 1s
  2300K .......... .......... .......... .......... .......... 17% 74.7M 1s
  2350K .......... .......... .......... .......... .......... 17% 70.8M 1s
  2400K .......... .......... .......... .......... .......... 17% 73.7M 1s
  2450K .......... .......... .......... .......... .......... 18% 38.2M 1s
  2500K .......... .......... .......... .......... .......... 18% 72.1M 1s
  2550K .......... .......... .......... .......... .......... 19% 5.47M 1s
  2600K .......... .......... .......... .......... .......... 19%  107M 1s
  2650K .......... .......... .......... .......... .......... 19% 93.4M 1s
  2700K .......... .......... .......... .......... .......... 20%  159M 1s
  2750K .......... .......... .......... .......... .......... 20% 62.3M 1s
  2800K .......... .......... .......... .......... .......... 20%  188M 1s
  2850K .......... .......... .......... .......... .......... 21% 74.2M 1s
  2900K .......... .......... .......... .......... .......... 21%  129M 1s
  2950K .......... .......... .......... .......... .......... 22% 95.1M 1s
  3000K .......... .......... .......... .......... .......... 22%  186M 1s
  3050K .......... .......... .......... .......... .......... 22% 4.50M 1s
  3100K .......... .......... .......... .......... .......... 23%  189M 1s
  3150K .......... .......... .......... .......... .......... 23%  103M 1s
  3200K .......... .......... .......... .......... .......... 23%  158M 1s
  3250K .......... .......... .......... .......... .......... 24%  103M 1s
  3300K .......... .......... .......... .......... .......... 24% 95.6M 1s
  3350K .......... .......... .......... .......... .......... 24% 91.5M 1s
  3400K .......... .......... .......... .......... .......... 25%  106M 1s
  3450K .......... .......... .......... .......... .......... 25%  168M 1s
  3500K .......... .......... .......... .......... .......... 26% 94.9M 1s
  3550K .......... .......... .......... .......... .......... 26%  102M 1s
  3600K .......... .......... .......... .......... .......... 26% 80.8M 1s
  3650K .......... .......... .......... .......... .......... 27%  279M 1s
  3700K .......... .......... .......... .......... .......... 27% 91.9M 1s
  3750K .......... .......... .......... .......... .......... 27% 98.7M 1s
  3800K .......... .......... .......... .......... .......... 28%  161M 1s
  3850K .......... .......... .......... .......... .......... 28%  104M 1s
  3900K .......... .......... .......... .......... .......... 28% 95.7M 1s
  3950K .......... .......... .......... .......... .......... 29%  161M 1s
  4000K .......... .......... .......... .......... .......... 29% 98.3M 1s
  4050K .......... .......... .......... .......... .......... 30%  753K 1s
  4100K .......... .......... .......... .......... .......... 30%  132M 1s
  4150K .......... .......... .......... .......... .......... 30%  132M 1s
  4200K .......... .......... .......... .......... .......... 31% 92.8M 1s
  4250K .......... .......... .......... .......... .......... 31%  108M 1s
  4300K .......... .......... .......... .......... .......... 31% 94.6M 1s
  4350K .......... .......... .......... .......... .......... 32%  191M 1s
  4400K .......... .......... .......... .......... .......... 32% 96.3M 1s
  4450K .......... .......... .......... .......... .......... 33% 95.1M 1s
  4500K .......... .......... .......... .......... .......... 33%  164M 1s
  4550K .......... .......... .......... .......... .......... 33%  104M 1s
  4600K .......... .......... .......... .......... .......... 34% 1.32M 1s
  4650K .......... .......... .......... .......... .......... 34% 94.2M 1s
  4700K .......... .......... .......... .......... .......... 34%  110M 1s
  4750K .......... .......... .......... .......... .......... 35%  204M 1s
  4800K .......... .......... .......... .......... .......... 35% 89.1M 1s
  4850K .......... .......... .......... .......... .......... 35%  179M 1s
  4900K .......... .......... .......... .......... .......... 36% 99.3M 1s
  4950K .......... .......... .......... .......... .......... 36% 94.3M 1s
  5000K .......... .......... .......... .......... .......... 37%  103M 1s
  5050K .......... .......... .......... .......... .......... 37%  159M 1s
  5100K .......... .......... .......... .......... .......... 37% 96.6M 1s
  5150K .......... .......... .......... .......... .......... 38% 90.4M 1s
  5200K .......... .......... .......... .......... .......... 38% 99.6M 1s
  5250K .......... .......... .......... .......... .......... 38% 96.6M 1s
  5300K .......... .......... .......... .......... .......... 39%  198M 1s
  5350K .......... .......... .......... .......... .......... 39% 94.6M 1s
  5400K .......... .......... .......... .......... .......... 39% 96.1M 0s
  5450K .......... .......... .......... .......... .......... 40%  159M 0s
  5500K .......... .......... .......... .......... .......... 40%  105M 0s
  5550K .......... .......... .......... .......... .......... 41%  146M 0s
  5600K .......... .......... .......... .......... .......... 41% 9.63M 0s
  5650K .......... .......... .......... .......... .......... 41% 89.0M 0s
  5700K .......... .......... .......... .......... .......... 42%  126M 0s
  5750K .......... .......... .......... .......... .......... 42%  117M 0s
  5800K .......... .......... .......... .......... .......... 42%  106M 0s
  5850K .......... .......... .......... .......... .......... 43% 95.4M 0s
  5900K .......... .......... .......... .......... .......... 43%  171M 0s
  5950K .......... .......... .......... .......... .......... 44% 96.6M 0s
  6000K .......... .......... .......... .......... .......... 44% 99.9M 0s
  6050K .......... .......... .......... .......... .......... 44%  163M 0s
  6100K .......... .......... .......... .......... .......... 45%  192K 1s
  6150K .......... .......... .......... .......... .......... 45%  101M 1s
  6200K .......... .......... .......... .......... .......... 45%  175M 1s
  6250K .......... .......... .......... .......... .......... 46% 89.6M 1s
  6300K .......... .......... .......... .......... .......... 46%  103M 1s
  6350K .......... .......... .......... .......... .......... 46% 99.6M 1s
  6400K .......... .......... .......... .......... .......... 47%  198M 1s
  6450K .......... .......... .......... .......... .......... 47% 91.6M 1s
  6500K .......... .......... .......... .......... .......... 48% 99.4M 1s
  6550K .......... .......... .......... .......... .......... 48%  166M 1s
  6600K .......... .......... .......... .......... .......... 48%  106M 1s
  6650K .......... .......... .......... .......... .......... 49% 1.09M 1s
  6700K .......... .......... .......... .......... .......... 49%  103M 1s
  6750K .......... .......... .......... .......... .......... 49% 95.9M 1s
  6800K .......... .......... .......... .......... .......... 50%  168M 1s
  6850K .......... .......... .......... .......... .......... 50% 98.3M 1s
  6900K .......... .......... .......... .......... .......... 51%  166M 1s
  6950K .......... .......... .......... .......... .......... 51% 95.5M 1s
  7000K .......... .......... .......... .......... .......... 51% 97.9M 1s
  7050K .......... .......... .......... .......... .......... 52%  104M 1s
  7100K .......... .......... .......... .......... .......... 52% 95.7M 1s
  7150K .......... .......... .......... .......... .......... 52% 3.02M 1s
  7200K .......... .......... .......... .......... .......... 53% 95.2M 1s
  7250K .......... .......... .......... .......... .......... 53%  257M 1s
  7300K .......... .......... .......... .......... .......... 53% 98.4M 1s
  7350K .......... .......... .......... .......... .......... 54%  164M 1s
  7400K .......... .......... .......... .......... .......... 54% 96.8M 1s
  7450K .......... .......... .......... .......... .......... 55% 94.1M 1s
  7500K .......... .......... .......... .......... .......... 55%  103M 1s
  7550K .......... .......... .......... .......... .......... 55%  157M 1s
  7600K .......... .......... .......... .......... .......... 56% 94.1M 1s
  7650K .......... .......... .......... .......... .......... 56% 1.65M 1s
  7700K .......... .......... .......... .......... .......... 56%  104M 1s
  7750K .......... .......... .......... .......... .......... 57%  100M 1s
  7800K .......... .......... .......... .......... .......... 57%  113M 1s
  7850K .......... .......... .......... .......... .......... 57%  138M 1s
  7900K .......... .......... .......... .......... .......... 58% 92.5M 1s
  7950K .......... .......... .......... .......... .......... 58%  155M 0s
  8000K .......... .......... .......... .......... .......... 59%  105M 0s
  8050K .......... .......... .......... .......... .......... 59% 91.9M 0s
  8100K .......... .......... .......... .......... .......... 59%  105M 0s
  8150K .......... .......... .......... .......... .......... 60% 5.36M 0s
  8200K .......... .......... .......... .......... .......... 60% 95.8M 0s
  8250K .......... .......... .......... .......... .......... 60%  133M 0s
  8300K .......... .......... .......... .......... .......... 61% 73.4M 0s
  8350K .......... .......... .......... .......... .......... 61%  190M 0s
  8400K .......... .......... .......... .......... .......... 62% 95.4M 0s
  8450K .......... .......... .......... .......... .......... 62%  190M 0s
  8500K .......... .......... .......... .......... .......... 62% 91.2M 0s
  8550K .......... .......... .......... .......... .......... 63% 99.5M 0s
  8600K .......... .......... .......... .......... .......... 63%  165M 0s
  8650K .......... .......... .......... .......... .......... 63% 88.7M 0s
  8700K .......... .......... .......... .......... .......... 64% 1.93M 0s
  8750K .......... .......... .......... .......... .......... 64% 30.9M 0s
  8800K .......... .......... .......... .......... .......... 64%  315M 0s
  8850K .......... .......... .......... .......... .......... 65%  311M 0s
  8900K .......... .......... .......... .......... .......... 65%  361M 0s
  8950K .......... .......... .......... .......... .......... 66%  106M 0s
  9000K .......... .......... .......... .......... .......... 66%  360M 0s
  9050K .......... .......... .......... .......... .......... 66% 75.5M 0s
  9100K .......... .......... .......... .......... .......... 67%  152M 0s
  9150K .......... .......... .......... .......... .......... 67% 96.5M 0s
  9200K .......... .......... .......... .......... .......... 67%  162M 0s
  9250K .......... .......... .......... .......... .......... 68% 99.7M 0s
  9300K .......... .......... .......... .......... .......... 68%  104M 0s
  9350K .......... .......... .......... .......... .......... 68% 95.2M 0s
  9400K .......... .......... .......... .......... .......... 69%  191M 0s
  9450K .......... .......... .......... .......... .......... 69% 91.4M 0s
  9500K .......... .......... .......... .......... .......... 70% 99.8M 0s
  9550K .......... .......... .......... .......... .......... 70%  162M 0s
  9600K .......... .......... .......... .......... .......... 70% 96.3M 0s
  9650K .......... .......... .......... .......... .......... 71% 99.7M 0s
  9700K .......... .......... .......... .......... .......... 71%  160M 0s
  9750K .......... .......... .......... .......... .......... 71% 90.4M 0s
  9800K .......... .......... .......... .......... .......... 72%  102M 0s
  9850K .......... .......... .......... .......... .......... 72%  102M 0s
  9900K .......... .......... .......... .......... .......... 73% 92.8M 0s
  9950K .......... .......... .......... .......... .......... 73%  196M 0s
 10000K .......... .......... .......... .......... .......... 73% 93.7M 0s
 10050K .......... .......... .......... .......... .......... 74% 96.7M 0s
 10100K .......... .......... .......... .......... .......... 74%  166M 0s
 10150K .......... .......... .......... .......... .......... 74%  103M 0s
 10200K .......... .......... .......... .......... .......... 75% 9.01M 0s
 10250K .......... .......... .......... .......... .......... 75% 92.9M 0s
 10300K .......... .......... .......... .......... .......... 75%  143M 0s
 10350K .......... .......... .......... .......... .......... 76% 87.5M 0s
 10400K .......... .......... .......... .......... .......... 76%  129M 0s
 10450K .......... .......... .......... .......... .......... 77% 94.5M 0s
 10500K .......... .......... .......... .......... .......... 77%  160M 0s
 10550K .......... .......... .......... .......... .......... 77%  100M 0s
 10600K .......... .......... .......... .......... .......... 78%  100M 0s
 10650K .......... .......... .......... .......... .......... 78%  164M 0s
 10700K .......... .......... .......... .......... .......... 78% 97.2M 0s
 10750K .......... .......... .......... .......... .......... 79% 9.63M 0s
 10800K .......... .......... .......... .......... .......... 79%  108M 0s
 10850K .......... .......... .......... .......... .......... 79%  116M 0s
 10900K .......... .......... .......... .......... .......... 80%  164M 0s
 10950K .......... .......... .......... .......... .......... 80% 96.6M 0s
 11000K .......... .......... .......... .......... .......... 81% 92.9M 0s
 11050K .......... .......... .......... .......... .......... 81%  191M 0s
 11100K .......... .......... .......... .......... .......... 81% 95.5M 0s
 11150K .......... .......... .......... .......... .......... 82%  100M 0s
 11200K .......... .......... .......... .......... .......... 82% 97.5M 0s
 11250K .......... .......... .......... .......... .......... 82% 7.68M 0s
 11300K .......... .......... .......... .......... .......... 83% 96.0M 0s
 11350K .......... .......... .......... .......... .......... 83%  187M 0s
 11400K .......... .......... .......... .......... .......... 84% 90.4M 0s
 11450K .......... .......... .......... .......... .......... 84%  105M 0s
 11500K .......... .......... .......... .......... .......... 84% 91.2M 0s
 11550K .......... .......... .......... .......... .......... 85%  185M 0s
 11600K .......... .......... .......... .......... .......... 85% 89.3M 0s
 11650K .......... .......... .......... .......... .......... 85%  174M 0s
 11700K .......... .......... .......... .......... .......... 86% 93.2M 0s
 11750K .......... .......... .......... .......... .......... 86%  101M 0s
 11800K .......... .......... .......... .......... .......... 86%  106M 0s
 11850K .......... .......... .......... .......... .......... 87%  164M 0s
 11900K .......... .......... .......... .......... .......... 87% 98.2M 0s
 11950K .......... .......... .......... .......... .......... 88% 98.5M 0s
 12000K .......... .......... .......... .......... .......... 88% 94.1M 0s
 12050K .......... .......... .......... .......... .......... 88%  156M 0s
 12100K .......... .......... .......... .......... .......... 89%  108M 0s
 12150K .......... .......... .......... .......... .......... 89% 94.9M 0s
 12200K .......... .......... .......... .......... .......... 89%  164M 0s
 12250K .......... .......... .......... .......... .......... 90% 2.68M 0s
 12300K .......... .......... .......... .......... .......... 90%  131M 0s
 12350K .......... .......... .......... .......... .......... 91%  118M 0s
 12400K .......... .......... .......... .......... .......... 91%  157M 0s
 12450K .......... .......... .......... .......... .......... 91%  134M 0s
 12500K .......... .......... .......... .......... .......... 92% 96.2M 0s
 12550K .......... .......... .......... .......... .......... 92%  141M 0s
 12600K .......... .......... .......... .......... .......... 92%  112M 0s
 12650K .......... .......... .......... .......... .......... 93% 92.1M 0s
 12700K .......... .......... .......... .......... .......... 93%  172M 0s
 12750K .......... .......... .......... .......... .......... 93%  104M 0s
 12800K .......... .......... .......... .......... .......... 94% 7.85M 0s
 12850K .......... .......... .......... .......... .......... 94%  106M 0s
 12900K .......... .......... .......... .......... .......... 95%  115M 0s
 12950K .......... .......... .......... .......... .......... 95%  150M 0s
 13000K .......... .......... .......... .......... .......... 95%  107M 0s
 13050K .......... .......... .......... .......... .......... 96% 88.0M 0s
 13100K .......... .......... .......... .......... .......... 96%  172M 0s
 13150K .......... .......... .......... .......... .......... 96% 94.7M 0s
 13200K .......... .......... .......... .......... .......... 97%  110M 0s
 13250K .......... .......... .......... .......... .......... 97% 94.2M 0s
 13300K .......... .......... .......... .......... .......... 97% 91.5M 0s
 13350K .......... .......... .......... .......... .......... 98%  157M 0s
 13400K .......... .......... .......... .......... .......... 98%  106M 0s
 13450K .......... .......... .......... .......... .......... 99%  160M 0s
 13500K .......... .......... .......... .......... .......... 99% 97.0M 0s
 13550K .......... .......... .......... .......... .......... 99%  101M 0s
 13600K .......... .......... ......                          100%  181M=0.8s

2026-09-29 18:49:57 (16.0 MB/s) - ‘vc_redist.x86.exe’ saved [13953392/13953392]

Executing cd /home/gregory/PycharmProjects/FuelAnalyst
------------------------------------------------------
SHA256 mismatch!

URL: https://aka.ms/vs/17/release/vc_redist.x86.exe
Downloaded: 0c09f2611660441084ce0df425c51c11e147e6447963c3690f97e0b25c55ed64
Expected: c61cef97487536e766130fa8714dd1b4143f6738bfb71806018eee1b5fe6f057

This is often the result of an updated package such as vcrun2019.
If you are willing to accept the risk, you can bypass this check.
Alternatively, you may use the --force option to ignore this check entirely.

Continue anyway?
------------------------------------------------------
------------------------------------------------------
Unattended mode, not prompting for confirmation
------------------------------------------------------
Executing cd /home/gregory/.cache/winetricks/vcrun2022
Executing wine vc_redist.x86.exe /q
Using native,builtin override for following DLLs: vcruntime140_1
Executing wine C:\windows\syswow64\regedit.exe /S C:\windows\Temp\override-dll.reg
Executing /usr/lib/wine/wine64 C:\windows\regedit.exe /S C:\windows\Temp\override-dll.reg
------------------------------------------------------
warning: Checksum for /home/gregory/.cache/winetricks/vcrun2022/vc_redist.x64.exe did not match, retrying download
------------------------------------------------------
Executing cd /home/gregory/.cache/winetricks/vcrun2022
Downloading https://aka.ms/vs/17/release/vc_redist.x64.exe to /home/gregory/.cache/winetricks/vcrun2022
--2026-09-29 18:49:58--  https://aka.ms/vs/17/release/vc_redist.x64.exe
Resolving aka.ms (aka.ms)... 184.30.154.152
Connecting to aka.ms (aka.ms)|184.30.154.152|:443... connected.
HTTP request sent, awaiting response... 301 Moved Permanently
Location: https://download.visualstudio.microsoft.com/download/pr/bd1c8d9d-ba95-4eee-bc6e-df1fcc876373/CC0FF0EB1DC3F5188AE6300FAEF32BF5BEEBA4BDD6E8E445A9184072096B713B/VC_redist.x64.exe [following]
--2026-09-29 18:49:58--  https://download.visualstudio.microsoft.com/download/pr/bd1c8d9d-ba95-4eee-bc6e-df1fcc876373/CC0FF0EB1DC3F5188AE6300FAEF32BF5BEEBA4BDD6E8E445A9184072096B713B/VC_redist.x64.exe
Resolving download.visualstudio.microsoft.com (download.visualstudio.microsoft.com)... 2001:569:139::cfc2:c73b, 2001:569:139::cfc2:c70b, 207.194.199.11, ...
Connecting to download.visualstudio.microsoft.com (download.visualstudio.microsoft.com)|2001:569:139::cfc2:c73b|:443... connected.
HTTP request sent, awaiting response... 200 OK
Length: 25635768 (24M) [application/octet-stream]
Saving to: ‘vc_redist.x64.exe’

     0K .......... .......... .......... .......... ..........  0% 14.8M 2s
    50K .......... .......... .......... .......... ..........  0% 4.15M 4s
   100K .......... .......... .......... .......... ..........  0% 10.1M 3s
   150K .......... .......... .......... .......... ..........  0% 7.45M 3s
   200K .......... .......... .......... .......... ..........  0% 14.5M 3s
   250K .......... .......... .......... .......... ..........  1% 16.1M 3s
   300K .......... .......... .......... .......... ..........  1% 9.41M 3s
   350K .......... .......... .......... .......... ..........  1% 12.3M 3s
   400K .......... .......... .......... .......... ..........  1% 16.1M 2s
   450K .......... .......... .......... .......... ..........  1% 9.88M 2s
   500K .......... .......... .......... .......... ..........  2% 20.7M 2s
   550K .......... .......... .......... .......... ..........  2% 29.3M 2s
   600K .......... .......... .......... .......... ..........  2% 37.4M 2s
   650K .......... .......... .......... .......... ..........  2% 28.6M 2s
   700K .......... .......... .......... .......... ..........  2% 6.91M 2s
   750K .......... .......... .......... .......... ..........  3% 25.8M 2s
   800K .......... .......... .......... .......... ..........  3% 48.9M 2s
   850K .......... .......... .......... .......... ..........  3% 39.2M 2s
   900K .......... .......... .......... .......... ..........  3% 12.8M 2s
   950K .......... .......... .......... .......... ..........  3% 9.78M 2s
  1000K .......... .......... .......... .......... ..........  4%  102M 2s
  1050K .......... .......... .......... .......... ..........  4%  123M 2s
  1100K .......... .......... .......... .......... ..........  4% 49.0M 2s
  1150K .......... .......... .......... .......... ..........  4% 57.4M 2s
  1200K .......... .......... .......... .......... ..........  4% 51.0M 2s
  1250K .......... .......... .......... .......... ..........  5% 94.9M 1s
  1300K .......... .......... .......... .......... ..........  5% 15.5M 1s
  1350K .......... .......... .......... .......... ..........  5% 8.68M 2s
  1400K .......... .......... .......... .......... ..........  5% 91.7M 1s
  1450K .......... .......... .......... .......... ..........  5% 99.6M 1s
  1500K .......... .......... .......... .......... ..........  6% 64.4M 1s
  1550K .......... .......... .......... .......... ..........  6% 52.8M 1s
  1600K .......... .......... .......... .......... ..........  6% 77.6M 1s
  1650K .......... .......... .......... .......... ..........  6% 18.4M 1s
  1700K .......... .......... .......... .......... ..........  6%  149M 1s
  1750K .......... .......... .......... .......... ..........  7% 8.62M 1s
  1800K .......... .......... .......... .......... ..........  7%  232M 1s
  1850K .......... .......... .......... .......... ..........  7% 48.3M 1s
  1900K .......... .......... .......... .......... ..........  7%  217M 1s
  1950K .......... .......... .......... .......... ..........  7% 92.7M 1s
  2000K .......... .......... .......... .......... ..........  8% 2.10M 1s
  2050K .......... .......... .......... .......... ..........  8%  193M 1s
  2100K .......... .......... .......... .......... ..........  8% 85.7M 1s
  2150K .......... .......... .......... .......... ..........  8%  154M 1s
  2200K .......... .......... .......... .......... ..........  8% 86.7M 1s
  2250K .......... .......... .......... .......... ..........  9%  169M 1s
  2300K .......... .......... .......... .......... ..........  9%  102M 1s
  2350K .......... .......... .......... .......... ..........  9% 95.9M 1s
  2400K .......... .......... .......... .......... ..........  9%  167M 1s
  2450K .......... .......... .......... .......... ..........  9% 65.5M 1s
  2500K .......... .......... .......... .......... .......... 10%  200M 1s
  2550K .......... .......... .......... .......... .......... 10%  909K 2s
  2600K .......... .......... .......... .......... .......... 10%  130M 2s
  2650K .......... .......... .......... .......... .......... 10% 88.0M 2s
  2700K .......... .......... .......... .......... .......... 10%  122M 2s
  2750K .......... .......... .......... .......... .......... 11% 98.4M 1s
  2800K .......... .......... .......... .......... .......... 11%  144M 1s
  2850K .......... .......... .......... .......... .......... 11%  120M 1s
  2900K .......... .......... .......... .......... .......... 11% 93.2M 1s
  2950K .......... .......... .......... .......... .......... 11% 93.4M 1s
  3000K .......... .......... .......... .......... .......... 12%  162M 1s
  3050K .......... .......... .......... .......... .......... 12%  439K 2s
  3100K .......... .......... .......... .......... .......... 12%  119M 2s
  3150K .......... .......... .......... .......... .......... 12%  106M 2s
  3200K .......... .......... .......... .......... .......... 12%  209M 2s
  3250K .......... .......... .......... .......... .......... 13% 86.2M 2s
  3300K .......... .......... .......... .......... .......... 13% 95.6M 2s
  3350K .......... .......... .......... .......... .......... 13%  102M 2s
  3400K .......... .......... .......... .......... .......... 13% 95.0M 2s
  3450K .......... .......... .......... .......... .......... 13%  164M 2s
  3500K .......... .......... .......... .......... .......... 14% 97.1M 2s
  3550K .......... .......... .......... .......... .......... 14%  101M 2s
  3600K .......... .......... .......... .......... .......... 14% 95.5M 2s
  3650K .......... .......... .......... .......... .......... 14%  188M 2s
  3700K .......... .......... .......... .......... .......... 14% 95.9M 2s
  3750K .......... .......... .......... .......... .......... 15% 94.8M 2s
  3800K .......... .......... .......... .......... .......... 15%  194M 2s
  3850K .......... .......... .......... .......... .......... 15% 95.4M 2s
  3900K .......... .......... .......... .......... .......... 15% 92.6M 2s
  3950K .......... .......... .......... .......... .......... 15%  187M 2s
  4000K .......... .......... .......... .......... .......... 16% 11.6M 2s
  4050K .......... .......... .......... .......... .......... 16%  846K 2s
  4100K .......... .......... .......... .......... .......... 16%  197M 2s
  4150K .......... .......... .......... .......... .......... 16%  102M 2s
  4200K .......... .......... .......... .......... .......... 16%  144M 2s
  4250K .......... .......... .......... .......... .......... 17% 98.8M 2s
  4300K .......... .......... .......... .......... .......... 17% 70.4M 2s
  4350K .......... .......... .......... .......... .......... 17%  259M 2s
  4400K .......... .......... .......... .......... .......... 17% 82.5M 2s
  4450K .......... .......... .......... .......... .......... 17%  161M 2s
  4500K .......... .......... .......... .......... .......... 18%  112M 2s
  4550K .......... .......... .......... .......... .......... 18%  118M 2s
  4600K .......... .......... .......... .......... .......... 18%  567K 2s
  4650K .......... .......... .......... .......... .......... 18%  190M 2s
  4700K .......... .......... .......... .......... .......... 18% 96.6M 2s
  4750K .......... .......... .......... .......... .......... 19%  141M 2s
  4800K .......... .......... .......... .......... .......... 19% 91.1M 2s
  4850K .......... .......... .......... .......... .......... 19%  121M 2s
  4900K .......... .......... .......... .......... .......... 19% 98.8M 2s
  4950K .......... .......... .......... .......... .......... 19% 98.3M 2s
  5000K .......... .......... .......... .......... .......... 20%  100M 2s
  5050K .......... .......... .......... .......... .......... 20%  188M 2s
  5100K .......... .......... .......... .......... .......... 20% 1.25M 2s
  5150K .......... .......... .......... .......... .......... 20%  121M 2s
  5200K .......... .......... .......... .......... .......... 20%  115M 2s
  5250K .......... .......... .......... .......... .......... 21% 97.8M 2s
  5300K .......... .......... .......... .......... .......... 21%  191M 2s
  5350K .......... .......... .......... .......... .......... 21% 88.4M 2s
  5400K .......... .......... .......... .......... .......... 21%  136M 2s
  5450K .......... .......... .......... .......... .......... 21% 76.5M 2s
  5500K .......... .......... .......... .......... .......... 22%  164M 2s
  5550K .......... .......... .......... .......... .......... 22%  156M 2s
  5600K .......... .......... .......... .......... .......... 22%  103M 2s
  5650K .......... .......... .......... .......... .......... 22% 66.8M 2s
  5700K .......... .......... .......... .......... .......... 22%  193M 2s
  5750K .......... .......... .......... .......... .......... 23% 92.8M 2s
  5800K .......... .......... .......... .......... .......... 23%  165M 2s
  5850K .......... .......... .......... .......... .......... 23%  114M 2s
  5900K .......... .......... .......... .......... .......... 23%  117M 2s
  5950K .......... .......... .......... .......... .......... 23% 76.4M 2s
  6000K .......... .......... .......... .......... .......... 24%  179M 2s
  6050K .......... .......... .......... .......... .......... 24% 98.4M 2s
  6100K .......... .......... .......... .......... .......... 24%  774K 2s
  6150K .......... .......... .......... .......... .......... 24%  102M 2s
  6200K .......... .......... .......... .......... .......... 24%  221M 2s
  6250K .......... .......... .......... .......... .......... 25%  133M 2s
  6300K .......... .......... .......... .......... .......... 25% 93.3M 2s
  6350K .......... .......... .......... .......... .......... 25% 96.4M 2s
  6400K .......... .......... .......... .......... .......... 25%  114M 2s
  6450K .......... .......... .......... .......... .......... 25% 94.1M 2s
  6500K .......... .......... .......... .......... .......... 26%  153M 2s
  6550K .......... .......... .......... .......... .......... 26% 99.2M 2s
  6600K .......... .......... .......... .......... .......... 26%  134M 2s
  6650K .......... .......... .......... .......... .......... 26% 1.42M 2s
  6700K .......... .......... .......... .......... .......... 26%  196M 2s
  6750K .......... .......... .......... .......... .......... 27% 68.6M 2s
  6800K .......... .......... .......... .......... .......... 27%  158M 2s
  6850K .......... .......... .......... .......... .......... 27%  108M 2s
  6900K .......... .......... .......... .......... .......... 27%  155M 2s
  6950K .......... .......... .......... .......... .......... 27% 96.9M 2s
  7000K .......... .......... .......... .......... .......... 28%  105M 2s
  7050K .......... .......... .......... .......... .......... 28%  125M 2s
  7100K .......... .......... .......... .......... .......... 28% 76.5M 2s
  7150K .......... .......... .......... .......... .......... 28% 1019K 2s
  7200K .......... .......... .......... .......... .......... 28%  246M 2s
  7250K .......... .......... .......... .......... .......... 29%  106M 2s
  7300K .......... .......... .......... .......... .......... 29% 96.5M 2s
  7350K .......... .......... .......... .......... .......... 29%  132M 2s
  7400K .......... .......... .......... .......... .......... 29% 94.8M 2s
  7450K .......... .......... .......... .......... .......... 29%  145M 2s
  7500K .......... .......... .......... .......... .......... 30% 76.4M 2s
  7550K .......... .......... .......... .......... .......... 30%  164M 2s
  7600K .......... .......... .......... .......... .......... 30% 98.2M 2s
  7650K .......... .......... .......... .......... .......... 30%  163M 2s
  7700K .......... .......... .......... .......... .......... 30% 60.8M 2s
  7750K .......... .......... .......... .......... .......... 31%  244M 2s
  7800K .......... .......... .......... .......... .......... 31%  104M 1s
  7850K .......... .......... .......... .......... .......... 31%  149M 1s
  7900K .......... .......... .......... .......... .......... 31% 97.4M 1s
  7950K .......... .......... .......... .......... .......... 31% 97.3M 1s
  8000K .......... .......... .......... .......... .......... 32%  132M 1s
  8050K .......... .......... .......... .......... .......... 32% 78.5M 1s
  8100K .......... .......... .......... .......... .......... 32%  200M 1s
  8150K .......... .......... .......... .......... .......... 32%  643K 2s
  8200K .......... .......... .......... .......... .......... 32%  111M 2s
  8250K .......... .......... .......... .......... .......... 33%  136M 2s
  8300K .......... .......... .......... .......... .......... 33%  101M 2s
  8350K .......... .......... .......... .......... .......... 33%  168M 2s
  8400K .......... .......... .......... .......... .......... 33% 71.4M 1s
  8450K .......... .......... .......... .......... .......... 33%  284M 1s
  8500K .......... .......... .......... .......... .......... 34% 77.0M 1s
  8550K .......... .......... .......... .......... .......... 34%  102M 1s
  8600K .......... .......... .......... .......... .......... 34%  184M 1s
  8650K .......... .......... .......... .......... .......... 34% 90.2M 1s
  8700K .......... .......... .......... .......... .......... 34% 1.42M 1s
  8750K .......... .......... .......... .......... .......... 35%  184M 1s
  8800K .......... .......... .......... .......... .......... 35% 94.3M 1s
  8850K .......... .......... .......... .......... .......... 35%  194M 1s
  8900K .......... .......... .......... .......... .......... 35% 94.8M 1s
  8950K .......... .......... .......... .......... .......... 35% 91.7M 1s
  9000K .......... .......... .......... .......... .......... 36%  175M 1s
  9050K .......... .......... .......... .......... .......... 36% 94.5M 1s
  9100K .......... .......... .......... .......... .......... 36%  103M 1s
  9150K .......... .......... .......... .......... .......... 36%  115M 1s
  9200K .......... .......... .......... .......... .......... 36%  818K 1s
  9250K .......... .......... .......... .......... .......... 37%  143M 1s
  9300K .......... .......... .......... .......... .......... 37%  165M 1s
  9350K .......... .......... .......... .......... .......... 37% 82.8M 1s
  9400K .......... .......... .......... .......... .......... 37%  188M 1s
  9450K .......... .......... .......... .......... .......... 37% 96.5M 1s
  9500K .......... .......... .......... .......... .......... 38%  132M 1s
  9550K .......... .......... .......... .......... .......... 38%  102M 1s
  9600K .......... .......... .......... .......... .......... 38%  102M 1s
  9650K .......... .......... .......... .......... .......... 38%  119M 1s
  9700K .......... .......... .......... .......... .......... 38%  121M 1s
  9750K .......... .......... .......... .......... .......... 39%  102M 1s
  9800K .......... .......... .......... .......... .......... 39% 96.6M 1s
  9850K .......... .......... .......... .......... .......... 39%  103M 1s
  9900K .......... .......... .......... .......... .......... 39% 94.0M 1s
  9950K .......... .......... .......... .......... .......... 39%  190M 1s
 10000K .......... .......... .......... .......... .......... 40% 89.0M 1s
 10050K .......... .......... .......... .......... .......... 40%  105M 1s
 10100K .......... .......... .......... .......... .......... 40% 94.1M 1s
 10150K .......... .......... .......... .......... .......... 40%  165M 1s
 10200K .......... .......... .......... .......... .......... 40%  211K 2s
 10250K .......... .......... .......... .......... .......... 41%  127M 2s
 10300K .......... .......... .......... .......... .......... 41%  201M 2s
 10350K .......... .......... .......... .......... .......... 41%  140M 2s
 10400K .......... .......... .......... .......... .......... 41%  115M 2s
 10450K .......... .......... .......... .......... .......... 41% 95.4M 2s
 10500K .......... .......... .......... .......... .......... 42%  220M 2s
 10550K .......... .......... .......... .......... .......... 42% 84.8M 2s
 10600K .......... .......... .......... .......... .......... 42%  101M 2s
 10650K .......... .......... .......... .......... .......... 42%  192M 1s
 10700K .......... .......... .......... .......... .......... 42% 91.7M 1s
 10750K .......... .......... .......... .......... .......... 43%  655K 2s
 10800K .......... .......... .......... .......... .......... 43% 85.4M 2s
 10850K .......... .......... .......... .......... .......... 43%  200M 2s
 10900K .......... .......... .......... .......... .......... 43%  101M 2s
 10950K .......... .......... .......... .......... .......... 43%  118M 2s
 11000K .......... .......... .......... .......... .......... 44% 85.2M 2s
 11050K .......... .......... .......... .......... .......... 44%  158M 1s
 11100K .......... .......... .......... .......... .......... 44% 66.2M 1s
 11150K .......... .......... .......... .......... .......... 44%  137M 1s
 11200K .......... .......... .......... .......... .......... 44%  147M 1s
 11250K .......... .......... .......... .......... .......... 45%  452K 2s
 11300K .......... .......... .......... .......... .......... 45%  100M 2s
 11350K .......... .......... .......... .......... .......... 45%  201M 2s
 11400K .......... .......... .......... .......... .......... 45% 95.8M 2s
 11450K .......... .......... .......... .......... .......... 45% 96.0M 2s
 11500K .......... .......... .......... .......... .......... 46%  149M 2s
 11550K .......... .......... .......... .......... .......... 46%  113M 2s
 11600K .......... .......... .......... .......... .......... 46% 94.7M 2s
 11650K .......... .......... .......... .......... .......... 46%  149M 1s
 11700K .......... .......... .......... .......... .......... 46% 97.0M 1s
 11750K .......... .......... .......... .......... .......... 47%  108M 1s
 11800K .......... .......... .......... .......... .......... 47% 92.8M 1s
 11850K .......... .......... .......... .......... .......... 47%  170M 1s
 11900K .......... .......... .......... .......... .......... 47%  104M 1s
 11950K .......... .......... .......... .......... .......... 47% 87.9M 1s
 12000K .......... .......... .......... .......... .......... 48%  227M 1s
 12050K .......... .......... .......... .......... .......... 48% 95.5M 1s
 12100K .......... .......... .......... .......... .......... 48% 94.3M 1s
 12150K .......... .......... .......... .......... .......... 48% 96.1M 1s
 12200K .......... .......... .......... .......... .......... 48%  164M 1s
 12250K .......... .......... .......... .......... .......... 49% 1.44M 1s
 12300K .......... .......... .......... .......... .......... 49%  160M 1s
 12350K .......... .......... .......... .......... .......... 49%  103M 1s
 12400K .......... .......... .......... .......... .......... 49%  116M 1s
 12450K .......... .......... .......... .......... .......... 49% 95.4M 1s
 12500K .......... .......... .......... .......... .......... 50%  140M 1s
 12550K .......... .......... .......... .......... .......... 50%  103M 1s
 12600K .......... .......... .......... .......... .......... 50% 97.7M 1s
 12650K .......... .......... .......... .......... .......... 50% 90.7M 1s
 12700K .......... .......... .......... .......... .......... 50%  224M 1s
 12750K .......... .......... .......... .......... .......... 51% 92.2M 1s
 12800K .......... .......... .......... .......... .......... 51%  750K 1s
 12850K .......... .......... .......... .......... .......... 51%  135M 1s
 12900K .......... .......... .......... .......... .......... 51% 95.6M 1s
 12950K .......... .......... .......... .......... .......... 51% 91.9M 1s
 13000K .......... .......... .......... .......... .......... 52%  222M 1s
 13050K .......... .......... .......... .......... .......... 52% 88.6M 1s
 13100K .......... .......... .......... .......... .......... 52%  165M 1s
 13150K .......... .......... .......... .......... .......... 52% 67.0M 1s
 13200K .......... .......... .......... .......... .......... 52%  184M 1s
 13250K .......... .......... .......... .......... .......... 53%  134M 1s
 13300K .......... .......... .......... .......... .......... 53% 14.1M 1s
 13350K .......... .......... .......... .......... .......... 53% 82.4M 1s
 13400K .......... .......... .......... .......... .......... 53%  209M 1s
 13450K .......... .......... .......... .......... .......... 53% 91.9M 1s
 13500K .......... .......... .......... .......... .......... 54%  167M 1s
 13550K .......... .......... .......... .......... .......... 54% 91.5M 1s
 13600K .......... .......... .......... .......... .......... 54% 99.0M 1s
 13650K .......... .......... .......... .......... .......... 54%  103M 1s
 13700K .......... .......... .......... .......... .......... 54%  187M 1s
 13750K .......... .......... .......... .......... .......... 55% 96.2M 1s
 13800K .......... .......... .......... .......... .......... 55% 88.5M 1s
 13850K .......... .......... .......... .......... .......... 55%  103M 1s
 13900K .......... .......... .......... .......... .......... 55%  159M 1s
 13950K .......... .......... .......... .......... .......... 55% 98.3M 1s
 14000K .......... .......... .......... .......... .......... 56%  113M 1s
 14050K .......... .......... .......... .......... .......... 56%  140M 1s
 14100K .......... .......... .......... .......... .......... 56% 90.1M 1s
 14150K .......... .......... .......... .......... .......... 56%  110M 1s
 14200K .......... .......... .......... .......... .......... 56% 95.3M 1s
 14250K .......... .......... .......... .......... .......... 57% 95.8M 1s
 14300K .......... .......... .......... .......... .......... 57% 9.21M 1s
 14350K .......... .......... .......... .......... .......... 57% 94.6M 1s
 14400K .......... .......... .......... .......... .......... 57%  164M 1s
 14450K .......... .......... .......... .......... .......... 57%  102M 1s
 14500K .......... .......... .......... .......... .......... 58% 98.7M 1s
 14550K .......... .......... .......... .......... .......... 58% 92.6M 1s
 14600K .......... .......... .......... .......... .......... 58%  163M 1s
 14650K .......... .......... .......... .......... .......... 58%  117M 1s
 14700K .......... .......... .......... .......... .......... 58% 84.0M 1s
 14750K .......... .......... .......... .......... .......... 59%  165M 1s
 14800K .......... .......... .......... .......... .......... 59% 89.7M 1s
 14850K .......... .......... .......... .......... .......... 59%  165M 1s
 14900K .......... .......... .......... .......... .......... 59% 86.9M 1s
 14950K .......... .......... .......... .......... .......... 59%  136M 1s
 15000K .......... .......... .......... .......... .......... 60% 86.8M 1s
 15050K .......... .......... .......... .......... .......... 60%  141M 1s
 15100K .......... .......... .......... .......... .......... 60%  101M 1s
 15150K .......... .......... .......... .......... .......... 60%  100M 1s
 15200K .......... .......... .......... .......... .......... 60% 96.1M 1s
 15250K .......... .......... .......... .......... .......... 61%  200M 1s
 15300K .......... .......... .......... .......... .......... 61% 91.3M 1s
 15350K .......... .......... .......... .......... .......... 61% 95.8M 1s
 15400K .......... .......... .......... .......... .......... 61%  103M 1s
 15450K .......... .......... .......... .......... .......... 61% 95.4M 1s
 15500K .......... .......... .......... .......... .......... 62%  163M 1s
 15550K .......... .......... .......... .......... .......... 62% 95.0M 1s
 15600K .......... .......... .......... .......... .......... 62%  102M 1s
 15650K .......... .......... .......... .......... .......... 62% 97.4M 1s
 15700K .......... .......... .......... .......... .......... 62%  188M 1s
 15750K .......... .......... .......... .......... .......... 63% 95.5M 1s
 15800K .......... .......... .......... .......... .......... 63% 95.7M 1s
 15850K .......... .......... .......... .......... .......... 63%  140M 1s
 15900K .......... .......... .......... .......... .......... 63%  110M 1s
 15950K .......... .......... .......... .......... .......... 63% 97.3M 1s
 16000K .......... .......... .......... .......... .......... 64%  152M 1s
 16050K .......... .......... .......... .......... .......... 64%  101M 1s
 16100K .......... .......... .......... .......... .......... 64% 94.3M 1s
 16150K .......... .......... .......... .......... .......... 64%  104M 1s
 16200K .......... .......... .......... .......... .......... 64%  175M 1s
 16250K .......... .......... .......... .......... .......... 65% 92.0M 1s
 16300K .......... .......... .......... .......... .......... 65%  104M 1s
 16350K .......... .......... .......... .......... .......... 65%  163M 1s
 16400K .......... .......... .......... .......... .......... 65%  103M 1s
 16450K .......... .......... .......... .......... .......... 65%  138M 1s
 16500K .......... .......... .......... .......... .......... 66% 71.4M 1s
 16550K .......... .......... .......... .......... .......... 66% 93.8M 1s
 16600K .......... .......... .......... .......... .......... 66%  307M 1s
 16650K .......... .......... .......... .......... .......... 66% 90.8M 1s
 16700K .......... .......... .......... .......... .......... 66%  148M 1s
 16750K .......... .......... .......... .......... .......... 67% 87.3M 1s
 16800K .......... .......... .......... .......... .......... 67%  104M 1s
 16850K .......... .......... .......... .......... .......... 67% 15.3M 1s
 16900K .......... .......... .......... .......... .......... 67%  151M 1s
 16950K .......... .......... .......... .......... .......... 67%  112M 1s
 17000K .......... .......... .......... .......... .......... 68%  133M 1s
 17050K .......... .......... .......... .......... .......... 68% 73.1M 1s
 17100K .......... .......... .......... .......... .......... 68%  187M 1s
 17150K .......... .......... .......... .......... .......... 68% 94.5M 1s
 17200K .......... .......... .......... .......... .......... 68% 96.5M 1s
 17250K .......... .......... .......... .......... .......... 69%  137M 1s
 17300K .......... .......... .......... .......... .......... 69%  103M 1s
 17350K .......... .......... .......... .......... .......... 69%  109M 1s
 17400K .......... .......... .......... .......... .......... 69% 4.81M 1s
 17450K .......... .......... .......... .......... .......... 69%  102M 1s
 17500K .......... .......... .......... .......... .......... 70%  117M 1s
 17550K .......... .......... .......... .......... .......... 70%  105M 1s
 17600K .......... .......... .......... .......... .......... 70%  158M 1s
 17650K .......... .......... .......... .......... .......... 70% 98.0M 1s
 17700K .......... .......... .......... .......... .......... 70% 98.9M 1s
 17750K .......... .......... .......... .......... .......... 71%  135M 1s
 17800K .......... .......... .......... .......... .......... 71% 73.1M 1s
 17850K .......... .......... .......... .......... .......... 71%  209M 1s
 17900K .......... .......... .......... .......... .......... 71% 91.5M 1s
 17950K .......... .......... .......... .......... .......... 71%  136M 1s
 18000K .......... .......... .......... .......... .......... 72%  104M 1s
 18050K .......... .......... .......... .......... .......... 72%  102M 1s
 18100K .......... .......... .......... .......... .......... 72% 94.3M 1s
 18150K .......... .......... .......... .......... .......... 72%  163M 1s
 18200K .......... .......... .......... .......... .......... 72%  103M 1s
 18250K .......... .......... .......... .......... .......... 73% 94.7M 1s
 18300K .......... .......... .......... .......... .......... 73%  146M 1s
 18350K .......... .......... .......... .......... .......... 73%  120M 1s
 18400K .......... .......... .......... .......... .......... 73% 1.04M 1s
 18450K .......... .......... .......... .......... .......... 73%  206M 1s
 18500K .......... .......... .......... .......... .......... 74% 98.5M 1s
 18550K .......... .......... .......... .......... .......... 74%  145M 1s
 18600K .......... .......... .......... .......... .......... 74% 99.2M 1s
 18650K .......... .......... .......... .......... .......... 74%  155M 1s
 18700K .......... .......... .......... .......... .......... 74% 98.7M 1s
 18750K .......... .......... .......... .......... .......... 75%  141M 1s
 18800K .......... .......... .......... .......... .......... 75% 82.8M 1s
 18850K .......... .......... .......... .......... .......... 75% 92.9M 0s
 18900K .......... .......... .......... .......... .......... 75%  252K 1s
 18950K .......... .......... .......... .......... .......... 75%  124M 1s
 19000K .......... .......... .......... .......... .......... 76%  283M 1s
 19050K .......... .......... .......... .......... .......... 76%  121M 1s
 19100K .......... .......... .......... .......... .......... 76% 70.4M 1s
 19150K .......... .......... .......... .......... .......... 76%  154M 1s
 19200K .......... .......... .......... .......... .......... 76%  108M 1s
 19250K .......... .......... .......... .......... .......... 77%  140M 1s
 19300K .......... .......... .......... .......... .......... 77% 95.5M 1s
 19350K .......... .......... .......... .......... .......... 77%  102M 1s
 19400K .......... .......... .......... .......... .......... 77%  107M 0s
 19450K .......... .......... .......... .......... .......... 77%  328K 1s
 19500K .......... .......... .......... .......... .......... 78%  146M 1s
 19550K .......... .......... .......... .......... .......... 78%  132M 1s
 19600K .......... .......... .......... .......... .......... 78%  115M 1s
 19650K .......... .......... .......... .......... .......... 78%  115M 1s
 19700K .......... .......... .......... .......... .......... 78%  140M 1s
 19750K .......... .......... .......... .......... .......... 79% 90.8M 1s
 19800K .......... .......... .......... .......... .......... 79%  119M 0s
 19850K .......... .......... .......... .......... .......... 79% 85.7M 0s
 19900K .......... .......... .......... .......... .......... 79%  167M 0s
 19950K .......... .......... .......... .......... .......... 79%  102M 0s
 20000K .......... .......... .......... .......... .......... 80%  137M 0s
 20050K .......... .......... .......... .......... .......... 80% 95.0M 0s
 20100K .......... .......... .......... .......... .......... 80%  137M 0s
 20150K .......... .......... .......... .......... .......... 80% 91.9M 0s
 20200K .......... .......... .......... .......... .......... 80%  119M 0s
 20250K .......... .......... .......... .......... .......... 81% 93.1M 0s
 20300K .......... .......... .......... .......... .......... 81%  114M 0s
 20350K .......... .......... .......... .......... .......... 81% 95.7M 0s
 20400K .......... .......... .......... .......... .......... 81%  164M 0s
 20450K .......... .......... .......... .......... .......... 81%  369K 0s
 20500K .......... .......... .......... .......... .......... 82%  187M 0s
 20550K .......... .......... .......... .......... .......... 82%  152M 0s
 20600K .......... .......... .......... .......... .......... 82%  236M 0s
 20650K .......... .......... .......... .......... .......... 82% 91.8M 0s
 20700K .......... .......... .......... .......... .......... 82%  163M 0s
 20750K .......... .......... .......... .......... .......... 83% 71.6M 0s
 20800K .......... .......... .......... .......... .......... 83%  286M 0s
 20850K .......... .......... .......... .......... .......... 83% 89.6M 0s
 20900K .......... .......... .......... .......... .......... 83%  112M 0s
 20950K .......... .......... .......... .......... .......... 83% 1.22M 0s
 21000K .......... .......... .......... .......... .......... 84%  117M 0s
 21050K .......... .......... .......... .......... .......... 84%  168M 0s
 21100K .......... .......... .......... .......... .......... 84%  129M 0s
 21150K .......... .......... .......... .......... .......... 84% 99.8M 0s
 21200K .......... .......... .......... .......... .......... 84%  103M 0s
 21250K .......... .......... .......... .......... .......... 85%  131M 0s
 21300K .......... .......... .......... .......... .......... 85% 79.6M 0s
 21350K .......... .......... .......... .......... .......... 85%  186M 0s
 21400K .......... .......... .......... .......... .......... 85% 95.1M 0s
 21450K .......... .......... .......... .......... .......... 85%  102M 0s
 21500K .......... .......... .......... .......... .......... 86% 1.50M 0s
 21550K .......... .......... .......... .......... .......... 86%  180M 0s
 21600K .......... .......... .......... .......... .......... 86% 97.5M 0s
 21650K .......... .......... .......... .......... .......... 86% 95.3M 0s
 21700K .......... .......... .......... .......... .......... 86%  104M 0s
 21750K .......... .......... .......... .......... .......... 87%  154M 0s
 21800K .......... .......... .......... .......... .......... 87%  100M 0s
 21850K .......... .......... .......... .......... .......... 87% 94.5M 0s
 21900K .......... .......... .......... .......... .......... 87% 99.9M 0s
 21950K .......... .......... .......... .......... .......... 87%  229M 0s
 22000K .......... .......... .......... .......... .......... 88% 81.2M 0s
 22050K .......... .......... .......... .......... .......... 88%  166M 0s
 22100K .......... .......... .......... .......... .......... 88% 90.4M 0s
 22150K .......... .......... .......... .......... .......... 88% 99.3M 0s
 22200K .......... .......... .......... .......... .......... 88%  111M 0s
 22250K .......... .......... .......... .......... .......... 89%  145M 0s
 22300K .......... .......... .......... .......... .......... 89% 71.1M 0s
 22350K .......... .......... .......... .......... .......... 89%  162M 0s
 22400K .......... .......... .......... .......... .......... 89%  144M 0s
 22450K .......... .......... .......... .......... .......... 89% 74.8M 0s
 22500K .......... .......... .......... .......... .......... 90%  166M 0s
 22550K .......... .......... .......... .......... .......... 90% 95.0M 0s
 22600K .......... .......... .......... .......... .......... 90% 99.7M 0s
 22650K .......... .......... .......... .......... .......... 90%  155M 0s
 22700K .......... .......... .......... .......... .......... 90% 94.8M 0s
 22750K .......... .......... .......... .......... .......... 91%  109M 0s
 22800K .......... .......... .......... .......... .......... 91% 93.8M 0s
 22850K .......... .......... .......... .......... .......... 91%  134M 0s
 22900K .......... .......... .......... .......... .......... 91%  118M 0s
 22950K .......... .......... .......... .......... .......... 91%  166M 0s
 23000K .......... .......... .......... .......... .......... 92% 94.6M 0s
 23050K .......... .......... .......... .......... .......... 92% 99.1M 0s
 23100K .......... .......... .......... .......... .......... 92%  142M 0s
 23150K .......... .......... .......... .......... .......... 92%  111M 0s
 23200K .......... .......... .......... .......... .......... 92% 94.6M 0s
 23250K .......... .......... .......... .......... .......... 93% 87.1M 0s
 23300K .......... .......... .......... .......... .......... 93%  104M 0s
 23350K .......... .......... .......... .......... .......... 93% 94.0M 0s
 23400K .......... .......... .......... .......... .......... 93%  185M 0s
 23450K .......... .......... .......... .......... .......... 93%  129M 0s
 23500K .......... .......... .......... .......... .......... 94%  114M 0s
 23550K .......... .......... .......... .......... .......... 94% 89.1M 0s
 23600K .......... .......... .......... .......... .......... 94%  155M 0s
 23650K .......... .......... .......... .......... .......... 94%  103M 0s
 23700K .......... .......... .......... .......... .......... 94% 91.8M 0s
 23750K .......... .......... .......... .......... .......... 95%  109M 0s
 23800K .......... .......... .......... .......... .......... 95%  158M 0s
 23850K .......... .......... .......... .......... .......... 95% 70.2M 0s
 23900K .......... .......... .......... .......... .......... 95%  164M 0s
 23950K .......... .......... .......... .......... .......... 95% 93.2M 0s
 24000K .......... .......... .......... .......... .......... 96%  103M 0s
 24050K .......... .......... .......... .......... .......... 96%  159M 0s
 24100K .......... .......... .......... .......... .......... 96% 95.9M 0s
 24150K .......... .......... .......... .......... .......... 96%  101M 0s
 24200K .......... .......... .......... .......... .......... 96%  148M 0s
 24250K .......... .......... .......... .......... .......... 97%  131M 0s
 24300K .......... .......... .......... .......... .......... 97% 80.6M 0s
 24350K .......... .......... .......... .......... .......... 97%  158M 0s
 24400K .......... .......... .......... .......... .......... 97% 3.76M 0s
 24450K .......... .......... .......... .......... .......... 97%  336M 0s
 24500K .......... .......... .......... .......... .......... 98% 4.16M 0s
 24550K .......... .......... .......... .......... .......... 98%  141K 0s
 24600K .......... .......... .......... .......... .......... 98%  198M 0s
 24650K .......... .......... .......... .......... .......... 98%  285M 0s
 24700K .......... .......... .......... .......... .......... 98%  201M 0s
 24750K .......... .......... .......... .......... .......... 99%  112M 0s
 24800K .......... .......... .......... .......... .......... 99%  102M 0s
 24850K .......... .......... .......... .......... .......... 99% 94.8M 0s
 24900K .......... .......... .......... .......... .......... 99% 93.5M 0s
 24950K .......... .......... .......... .......... .......... 99%  189M 0s
 25000K .......... .......... .......... ....                 100%  218M=2.5s

2026-09-29 18:50:01 (9.68 MB/s) - ‘vc_redist.x64.exe’ saved [25635768/25635768]

Executing cd /home/gregory/.cache/winetricks/vcrun2022
------------------------------------------------------
SHA256 mismatch!

URL: https://aka.ms/vs/17/release/vc_redist.x64.exe
Downloaded: cc0ff0eb1dc3f5188ae6300faef32bf5beeba4bdd6e8e445a9184072096b713b
Expected: 4dfe83c91124cd542f4222fe2c396cabeac617bb6f59bdcbdf89fd6f0df0a32f

This is often the result of an updated package such as vcrun2019.
If you are willing to accept the risk, you can bypass this check.
Alternatively, you may use the --force option to ignore this check entirely.

Continue anyway?
------------------------------------------------------
------------------------------------------------------
Unattended mode, not prompting for confirmation
------------------------------------------------------
Executing wine vc_redist.x64.exe /q
Provisioned.

=== Consumption (run type 0) ===
consumption: PASS (80,74,80 columns, 3 lines)

=== Soil (run type 1) ===
soil: PASS (86,80,86 columns, 3 lines)

=== Mortality (run type 2) ===
mortality: PASS (11 lines)

=== Summary ===
Wine: wine-9.0 (Ubuntu 9.0~repack-4build3)
WINEARCH: win64
vcrun2022: provisioned via winetricks
Consumption: PASS
Soil: PASS
Mortality: PASS
```

</details>

## Approved implementation: complete integration and unit output

<details>
<summary>Initial combined run: 8 real integration tests passed; one unit fixture line-ending failure</summary>

```text
============================= test session starts ==============================
platform linux -- Python 3.13.2, pytest-9.1.1, pluggy-1.6.0 -- /home/gregory/miniconda3/envs/ProcessGeospatial/bin/python
cachedir: .pytest_cache
rootdir: /home/gregory/PycharmProjects/FuelAnalyst
configfile: pyproject.toml
plugins: anyio-4.8.0
collecting ... collected 41 items

tests/integration/test_fofem694_official_batch.py::test_process_emissions_consumption_mode_matches_direct_runfofem_output PASSED [  2%]
tests/integration/test_fofem694_official_batch.py::test_process_emissions_soil_mode PASSED [  4%]
tests/integration/test_fofem694_official_batch.py::test_process_emissions_windspeed_at_boundary_succeeds PASSED [  7%]
tests/integration/test_fofem694_official_batch.py::test_process_emissions_windspeed_over_range_reports_clear_error_unclipped PASSED [  9%]
tests/integration/test_fofem694_official_batch.py::test_process_emissions_equation_auto_selection_populates_real_values PASSED [ 12%]
tests/integration/test_fofem694_official_batch.py::test_process_emissions_missing_fofem_data_fails_before_rows PASSED [ 14%]
tests/integration/test_fofem694_official_batch.py::test_run_runfofem_invalid_input_raises_with_batch_error_message PASSED [ 17%]
tests/integration/test_fofem694_official_batch.py::test_gen_fofem_gui_app_tree_df_output_accepted_by_runfofem_mortality PASSED [ 19%]
tests/unit/test_fofem_gui_emissions.py::test_get_fofem_dir_uses_env_var_override PASSED [ 21%]
tests/unit/test_fofem_gui_emissions.py::test_get_fofem_dir_rejects_nonexistent_env_var_override PASSED [ 24%]
tests/unit/test_fofem_gui_emissions.py::test_get_fofem_dir_rejects_env_var_override_missing_runfofem_exe PASSED [ 26%]
tests/unit/test_fofem_gui_emissions.py::test_get_fofem_dir_rejects_env_var_override_missing_species_csv PASSED [ 29%]
tests/unit/test_fofem_gui_emissions.py::test_get_fofem_dir_resolves_bundled_directory_without_override PASSED [ 31%]
tests/unit/test_fofem_gui_emissions.py::test_get_fofem_dir_raises_clear_error_when_bundle_missing_runfofem_exe PASSED [ 34%]
tests/unit/test_fofem_gui_emissions.py::test_get_fofem_dir_resolves_installed_runtime_package_without_override PASSED [ 36%]
tests/unit/test_fofem_gui_emissions.py::test_get_fofem_dir_env_var_override_takes_priority_over_runtime_package PASSED [ 39%]
tests/unit/test_fofem_gui_emissions.py::test_get_fofem_dir_falls_back_to_bundle_when_runtime_package_incomplete PASSED [ 41%]
tests/unit/test_fofem_gui_emissions.py::test_ensure_worker_fofem_runtime_copies_required_files PASSED [ 43%]
tests/unit/test_fofem_gui_emissions.py::test_ensure_worker_fofem_runtime_raises_when_required_file_missing PASSED [ 46%]
tests/unit/test_fofem_gui_emissions.py::test_ensure_worker_fofem_runtime_does_not_recopy_existing_files PASSED [ 48%]
tests/unit/test_fofem_gui_emissions.py::test_convert_consume_row_to_imperial_converts_si_source_values PASSED [ 51%]
tests/unit/test_fofem_gui_emissions.py::test_convert_consume_row_to_imperial_passes_through_imperial_source_values PASSED [ 53%]
tests/unit/test_fofem_gui_emissions.py::test_convert_consume_row_to_imperial_does_not_add_or_remove_columns PASSED [ 56%]
tests/unit/test_fofem_gui_emissions.py::test_write_burnup_params_694_matches_verified_fixture_byte_for_byte FAILED [ 58%]
tests/unit/test_fofem_gui_emissions.py::test_write_burnup_params_694_substitutes_dynamic_values PASSED [ 60%]
tests/unit/test_fofem_gui_emissions.py::test_write_consumption_input_writes_expected_switches_and_field_order_for_consumption PASSED [ 63%]
tests/unit/test_fofem_gui_emissions.py::test_write_consumption_input_inserts_soil_fields_and_ambient_temp_before_equations PASSED [ 65%]
tests/unit/test_fofem_gui_emissions.py::test_write_consumption_input_writes_required_expanded_emission_factor_switches PASSED [ 68%]
tests/unit/test_fofem_gui_emissions.py::test_run_runfofem_uses_platform_launcher[win32] PASSED [ 70%]
tests/unit/test_fofem_gui_emissions.py::test_run_runfofem_uses_platform_launcher[linux] PASSED [ 73%]
tests/unit/test_fofem_gui_emissions.py::test_run_runfofem_raises_actionable_error_on_missing_vcredist_dll PASSED [ 75%]
tests/unit/test_fofem_gui_emissions.py::test_run_runfofem_reports_generic_exit_code_for_other_failures PASSED [ 78%]
tests/unit/test_fofem_gui_emissions.py::test_parse_runfofem_output_drops_std_after_validating_plot_identity PASSED [ 80%]
tests/unit/test_fofem_gui_emissions.py::test_parse_runfofem_output_rejects_unexpected_column_count PASSED [ 82%]
tests/unit/test_fofem_gui_emissions.py::test_parse_runfofem_output_rejects_plot_identity_mismatch PASSED [ 85%]
tests/unit/test_fofem_gui_emissions.py::test_process_emissions_rejects_invalid_units PASSED [ 87%]
tests/unit/test_fofem_gui_emissions.py::test_process_emissions_rejects_units_filename_mismatch PASSED [ 90%]
tests/unit/test_fofem_gui_emissions.py::test_process_emissions_threads_units_and_converts_si_final_result PASSED [ 92%]
tests/unit/test_fofem_gui_emissions.py::test_process_emissions_threads_units_and_passes_through_imperial_final_result PASSED [ 95%]
tests/unit/test_fofem_gui_emissions.py::test_process_emissions_defaults_to_si PASSED [ 97%]
tests/unit/test_fofem_gui_emissions.py::test_process_emissions_threads_units_via_process_map_path PASSED [100%]

=================================== FAILURES ===================================
_____ test_write_burnup_params_694_matches_verified_fixture_byte_for_byte ______

tmp_path = PosixPath('/tmp/pytest-of-gregory/pytest-0/test_write_burnup_params_694_m0')

    def test_write_burnup_params_694_matches_verified_fixture_byte_for_byte(tmp_path):
        """The verified tests/test_data/fofem694/burnup_parameters_694.brn fixture used these exact
        five dynamic values; regenerating with them must reproduce it byte-for-byte."""
        out_path = tmp_path / 'burnup.brn'
        fofem_gui_emissions._write_burnup_params_694(
            str(out_path), intensity=500, ig_time=60, windspeed=2, depth=0.3, ambient_temp=20,
        )
        fixture_path = os.path.join(_BUNDLE_FIXTURE_DIR, 'burnup_parameters_694.brn')
        with open(fixture_path, 'rb') as f:
            expected = f.read()
        with open(out_path, 'rb') as f:
            actual = f.read()
>       assert actual == expected
E       AssertionError: assert b'#MAX_TIMES ...t_20 0.05\r\n' == b'#MAX_TIMES ...Rot_20 0.05\n'
E
E         At index 15 diff: b'\r' != b'\n'
E
E         Full diff:
E         - (b'#MAX_TIMES 3000\n#INTENSITY 500\n#IG_TIME 60\n#WINDSPEED 2\n#DEPTH 0.3\n#'
E         ?                                                                        -----
E         + (b'#MAX_TIMES 3000\r\n#INTENSITY 500\r\n#IG_TIME 60\r\n#WINDSPEED 2\r\n#DEPTH 0'...
E
E         ...Full output truncated (97 lines hidden), use '-vv' to show

tests/unit/test_fofem_gui_emissions.py:218: AssertionError
=========================== short test summary info ============================
FAILED tests/unit/test_fofem_gui_emissions.py::test_write_burnup_params_694_matches_verified_fixture_byte_for_byte
======================== 1 failed, 40 passed in 12.91s =========================
```

</details>

<details>
<summary>Final unit run after fixture line-ending correction: 33 passed</summary>

```text
============================= test session starts ==============================
platform linux -- Python 3.13.2, pytest-9.1.1, pluggy-1.6.0 -- /home/gregory/miniconda3/envs/ProcessGeospatial/bin/python
cachedir: .pytest_cache
rootdir: /home/gregory/PycharmProjects/FuelAnalyst
configfile: pyproject.toml
plugins: anyio-4.8.0
collecting ... collected 33 items

tests/unit/test_fofem_gui_emissions.py::test_get_fofem_dir_uses_env_var_override PASSED [  3%]
tests/unit/test_fofem_gui_emissions.py::test_get_fofem_dir_rejects_nonexistent_env_var_override PASSED [  6%]
tests/unit/test_fofem_gui_emissions.py::test_get_fofem_dir_rejects_env_var_override_missing_runfofem_exe PASSED [  9%]
tests/unit/test_fofem_gui_emissions.py::test_get_fofem_dir_rejects_env_var_override_missing_species_csv PASSED [ 12%]
tests/unit/test_fofem_gui_emissions.py::test_get_fofem_dir_resolves_bundled_directory_without_override PASSED [ 15%]
tests/unit/test_fofem_gui_emissions.py::test_get_fofem_dir_raises_clear_error_when_bundle_missing_runfofem_exe PASSED [ 18%]
tests/unit/test_fofem_gui_emissions.py::test_get_fofem_dir_resolves_installed_runtime_package_without_override PASSED [ 21%]
tests/unit/test_fofem_gui_emissions.py::test_get_fofem_dir_env_var_override_takes_priority_over_runtime_package PASSED [ 24%]
tests/unit/test_fofem_gui_emissions.py::test_get_fofem_dir_falls_back_to_bundle_when_runtime_package_incomplete PASSED [ 27%]
tests/unit/test_fofem_gui_emissions.py::test_ensure_worker_fofem_runtime_copies_required_files PASSED [ 30%]
tests/unit/test_fofem_gui_emissions.py::test_ensure_worker_fofem_runtime_raises_when_required_file_missing PASSED [ 33%]
tests/unit/test_fofem_gui_emissions.py::test_ensure_worker_fofem_runtime_does_not_recopy_existing_files PASSED [ 36%]
tests/unit/test_fofem_gui_emissions.py::test_convert_consume_row_to_imperial_converts_si_source_values PASSED [ 39%]
tests/unit/test_fofem_gui_emissions.py::test_convert_consume_row_to_imperial_passes_through_imperial_source_values PASSED [ 42%]
tests/unit/test_fofem_gui_emissions.py::test_convert_consume_row_to_imperial_does_not_add_or_remove_columns PASSED [ 45%]
tests/unit/test_fofem_gui_emissions.py::test_write_burnup_params_694_matches_verified_fixture_byte_for_byte PASSED [ 48%]
tests/unit/test_fofem_gui_emissions.py::test_write_burnup_params_694_substitutes_dynamic_values PASSED [ 51%]
tests/unit/test_fofem_gui_emissions.py::test_write_consumption_input_writes_expected_switches_and_field_order_for_consumption PASSED [ 54%]
tests/unit/test_fofem_gui_emissions.py::test_write_consumption_input_inserts_soil_fields_and_ambient_temp_before_equations PASSED [ 57%]
tests/unit/test_fofem_gui_emissions.py::test_write_consumption_input_writes_required_expanded_emission_factor_switches PASSED [ 60%]
tests/unit/test_fofem_gui_emissions.py::test_run_runfofem_uses_platform_launcher[win32] PASSED [ 63%]
tests/unit/test_fofem_gui_emissions.py::test_run_runfofem_uses_platform_launcher[linux] PASSED [ 66%]
tests/unit/test_fofem_gui_emissions.py::test_run_runfofem_raises_actionable_error_on_missing_vcredist_dll PASSED [ 69%]
tests/unit/test_fofem_gui_emissions.py::test_run_runfofem_reports_generic_exit_code_for_other_failures PASSED [ 72%]
tests/unit/test_fofem_gui_emissions.py::test_parse_runfofem_output_drops_std_after_validating_plot_identity PASSED [ 75%]
tests/unit/test_fofem_gui_emissions.py::test_parse_runfofem_output_rejects_unexpected_column_count PASSED [ 78%]
tests/unit/test_fofem_gui_emissions.py::test_parse_runfofem_output_rejects_plot_identity_mismatch PASSED [ 81%]
tests/unit/test_fofem_gui_emissions.py::test_process_emissions_rejects_invalid_units PASSED [ 84%]
tests/unit/test_fofem_gui_emissions.py::test_process_emissions_rejects_units_filename_mismatch PASSED [ 87%]
tests/unit/test_fofem_gui_emissions.py::test_process_emissions_threads_units_and_converts_si_final_result PASSED [ 90%]
tests/unit/test_fofem_gui_emissions.py::test_process_emissions_threads_units_and_passes_through_imperial_final_result PASSED [ 93%]
tests/unit/test_fofem_gui_emissions.py::test_process_emissions_defaults_to_si PASSED [ 96%]
tests/unit/test_fofem_gui_emissions.py::test_process_emissions_threads_units_via_process_map_path PASSED [100%]

============================== 33 passed in 0.28s ==============================
```

</details>
