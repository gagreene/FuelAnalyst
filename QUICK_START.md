# FuelAnalyst quick start

This guide gets the included Survey123 example running with the fewest steps. Commands assume you start in a terminal outside the repository.

## 1. Check prerequisites

Install:

- Python 3.10 or newer
- Git

Confirm Python is available:

```shell
python --version
```

On some systems the command is `python3` instead of `python`. If so, substitute `python3` in the commands below.

## 2. Download FuelAnalyst

```shell
git clone https://github.com/gagreene/FuelAnalyst.git
cd FuelAnalyst
```

## 3. Create a virtual environment

```shell
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Activate it on macOS/Linux:

```shell
source .venv/bin/activate
```

Your terminal will usually show `(.venv)` after activation.

## 4. Install FuelAnalyst

```shell
python -m pip install --upgrade pip
python -m pip install -e .
```

The base installation is enough to process Survey123 data and generate ConPyro and FOFEM preparation files. It does not install or execute the external fire models.

## 5. Run the included example

```shell
python -m fuel_analyst.fuel_analyst
```

The command reads:

```text
examples/data/Survey123_Data/
```

and writes results to:

```text
examples/results/fuel_analyst/
```

The main files are:

- `master_fuel_df.csv` — plot-level results
- `master_tree_df.csv` — detailed tree results
- `conpyro_df.csv` — prepared ConPyro inputs
- `fbp_prep_df.csv` — prepared BC FBP fuel-typing inputs
- `fofem_tree_df.csv` — prepared FOFEM mortality inputs
- `fofem_consume_df.csv` — prepared FOFEM consumption inputs

If these files exist after the command finishes, the first run succeeded.

## 6. Run your own Survey123 data

Arrange the exported files like this:

```text
Survey123_Data/
|-- 1_Plot_Attributes/survey_0.csv
|-- 2_Plants_Regeneration/
|   |-- survey_0.csv
|   `-- regeneration_1.csv
|-- 3_Trees/
|   |-- survey_0.csv
|   |-- sapling_1.csv
|   `-- tree_plot_2.csv
|-- 4_Canopy_Cover/
|   |-- survey_0.csv
|   `-- canopy_cover_1.csv
`-- 5_Woody_Debris/
    |-- survey_0.csv
    |-- spp_comp_manual_1.csv
    |-- t1_woody_2.csv
    `-- t2_woody_3.csv
```

Create a file named `run_fuel_analyst.py` outside your input and output folders:

```python
from fuel_analyst import fuel_analyst

fuel_analyst(
    in_dir=r"C:\path\to\Survey123_Data",
    out_dir=r"C:\path\to\FuelAnalyst_results",
    surface_fire_intensity_model="Byram",
    gen_conpyro_df=True,
    gen_fofem_tree_df=True,
    gen_fofem_consume_df=True,
)
```

Replace the two example paths with your actual paths, then run:

```shell
python run_fuel_analyst.py
```

For macOS/Linux paths, use forms such as `/home/name/data/Survey123_Data` without the leading `r` requirement.

### If you only need the master FuelAnalyst tables

Model-preparation files are optional:

```python
from fuel_analyst import fuel_analyst

fuel_analyst(
    in_dir="path/to/Survey123_Data",
    out_dir="path/to/results",
    surface_fire_intensity_model="Byram",
)
```

## 7. Optional: install external fire models

Only do this if you need to execute ConPyro or FOFEM after preparing the FuelAnalyst tables:

```shell
python -m pip install -e ".[conpyro,fofem]"
```

Those optional packages are downloaded from GitHub. ConPyro also uses the flame-components package.

Before running ConPyro, merge weather fields into `conpyro_df.csv`. At minimum, the default workflow expects `ws`, `wd`, `ffmc`, `dmc`, `bui`, and `wx_date`; selected model settings may require additional fields.

See the [Public API](README.md#public-api) section of the main README for the FBP, weather merge, and model-running calls.

## 8. Optional: run the tests

Install the test dependencies:

```shell
python -m pip install -e ".[test]"
```

Run the complete suite:

```shell
python -m pytest -vv
```

## Common problems

### `python` is not recognized

Install Python and select the option to add it to `PATH`, or try `python3`.

### PowerShell blocks environment activation

You can call the environment's Python directly without activating it:

```powershell
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m fuel_analyst.fuel_analyst
```

### A Survey123 folder or CSV is missing

Compare your export with `examples/data/Survey123_Data`. Folder and repeat-table names must match the expected layout. When `gen_conpyro_df=True`, all four component-form folders are required.

### A date cannot be parsed

The `_date` field must use one of these formats:

```text
05/14/2025 19:00
05/14/2025 07:00:00 PM
```

### ConPyro reports missing weather columns

Preparing `conpyro_df.csv` does not attach weather. Extract or supply weather data, merge it with the prepared table, and then call `run_conpyro()`.

### Installation of optional dependencies fails

Confirm Git is installed and can access GitHub. The core FuelAnalyst workflow does not require the optional dependencies, so you can omit the extras until model execution is needed.

## Next steps

- Read the full [README](README.md).
- Review the checked-in [Survey123 example](examples/data/Survey123_Data).
- Review the [result-field reference](docs/reference).
- Read the [test-suite guide](tests/README.md).
