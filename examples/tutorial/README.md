# FuelAnalyst tutorial

`FuelAnalyst_Tutorial.ipynb` walks through the full FuelAnalyst workflow on the example dataset in
`examples/data/`: exploring Survey123 data, `fuel_analyst()`, FBP fuel typing, weather merging, and
`run_conpyro()` (ConPyro fire behaviour, FOFEM tree mortality, and FOFEM emissions).

Adapted from a tutorial by Sarah Smith-Tripp (UBC Centre for Wildfire Coexistence).

## Requirements

- A clone of this repository. The notebook reads the example data from `examples/data/`, and it can be opened from any
  folder inside the clone.
- Python 3.11 or newer with FuelAnalyst (which includes ConPyro) and its FOFEM component installed, plus `matplotlib` for the figures,
  `ipykernel` to run notebooks, and `ipywidgets` for notebook progress bars.
- A notebook front end: VS Code, PyCharm, or JupyterLab.

**[SETUP.md](SETUP.md)** walks through all of this from scratch, including installing Python and Git, creating the
environment, and configuring VS Code or PyCharm.

## Running it

Open `FuelAnalyst_Tutorial.ipynb`, select the Python environment you installed FuelAnalyst into as the kernel, and run
the cells in order. Results are written to `examples/results/tutorial/`, which Git ignores. The full run takes a few
minutes on a laptop.

The notebook is committed with its outputs cleared. It uses only the committed example data; weather extraction from a
gridded weather archive is shown but not run, because it needs data that is not distributed with the repository.
