# Setting up FuelAnalyst for the tutorial

This guide takes you from a computer with nothing installed to a working copy of the tutorial notebook. It assumes no
programming tools are installed yet. If you already have Python, Git, and an editor, skip to
[Step 4](#4-create-an-environment-and-install-fuelanalyst).

The steps are the same for everyone except the editor. You only need **one** of the two supported editors:
[VS Code](#vs-code) or [PyCharm](#pycharm). Both run notebooks, and the tutorial works the same in either.

## 1. Install Python

FuelAnalyst needs **Python 3.11 or newer** (3.11 to 3.14 are supported).

- Download Python from [python.org/downloads](https://www.python.org/downloads/).
- On Windows, tick **Add python.exe to PATH** on the first screen of the installer.
- Check the install by opening a terminal (PowerShell on Windows, Terminal on Mac or Linux) and running:

  ```
  python --version
  ```

  On Mac and Linux the command may be `python3 --version`. If a command says it is not found, see
  [Troubleshooting](#troubleshooting).

## 2. Install Git and Git LFS

Git downloads the repository. **Git LFS** is needed because the example weather file (about 22 MB) is stored with Git
LFS; without it you get a small placeholder file and the tutorial fails.

- Download Git from [git-scm.com/downloads](https://git-scm.com/downloads). The Windows installer includes Git LFS. On
  Mac and Linux, install Git LFS separately ([git-lfs.com](https://git-lfs.com/) or your package manager).
- Turn on Git LFS once per computer:

  ```
  git lfs install
  ```

## 3. Download the repository

Choose a folder for your work, open a terminal there, and clone the repository (replace the address with the one you
were given):

```
git clone <repository-address>
cd FuelAnalyst
```

Every command from here on is run from this folder, the top of the repository.

## 4. Create an environment and install FuelAnalyst

A **virtual environment** is a private copy of Python for one project. Packages you install go into it and do not
affect anything else on your computer. Create one named `.venv` inside the repository.

**Windows (PowerShell):**

```
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Mac or Linux:**

```
python3 -m venv .venv
source .venv/bin/activate
```

When the environment is active, `(.venv)` appears at the start of your terminal prompt. Run the rest of this step
with it active. Then install FuelAnalyst and the packages the tutorial uses:

```
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install "pyfofem-fire-effects>=0.1.1,<0.2" matplotlib ipykernel ipywidgets
```

What each line does:

| Command | What it does |
|---|---|
| `pip install --upgrade pip` | Updates the package installer itself |
| `pip install -e .` | Installs FuelAnalyst, its bundled ConPyro crown fire model, and its scientific Python dependencies, including the flame geometry package (this takes a few minutes) |
| `pip install pyfofem-fire-effects matplotlib ipykernel ipywidgets` | Installs the FOFEM fire effects package, the plotting library the tutorial's figures use, the component that lets editors run notebooks, and the one that draws notebook progress bars (without it, a harmless `TqdmWarning: IProgress not found` appears) |

Check that everything installed:

```
python -c "import fuel_analyst, pyfofem, flame_components, matplotlib; from fuel_analyst._vendor import conpyro; print('FuelAnalyst is ready')"
```

## 5. Open the tutorial in your editor

Install **one** editor, open the **repository folder** in it (not a single file), and point it at the `.venv` you just
made.

### VS Code

1. Install [VS Code](https://code.visualstudio.com/download).
2. Open the **Extensions** view (`Ctrl+Shift+X`, or `Cmd+Shift+X` on Mac) and install **Python** and **Jupyter** (both
   from Microsoft). Close and reopen VS Code.
3. Choose **File > Open Folder** and select the `FuelAnalyst` folder. If VS Code asks whether you trust the authors of
   the folder, choose **Trust**; cells will not run in Restricted Mode.
4. Open `examples/tutorial/FuelAnalyst_Tutorial.ipynb`.
5. Click **Select Kernel** at the top right of the notebook, choose **Python Environments...**, and pick the entry
   for **`.venv`**. Read the paths carefully, because several Python installations may be listed.
6. Run the first code cell with `Shift+Enter`. It should print `FuelAnalyst and companion packages loaded.`

### PyCharm

1. Install [PyCharm](https://www.jetbrains.com/pycharm/download/). Notebook support is included in the free version of
   PyCharm 2025.1 and later.
2. Choose **File > Open** and select the `FuelAnalyst` folder.
3. Tell PyCharm to use your environment: click the **Python interpreter** selector in the status bar at the bottom
   right, choose **Add New Interpreter > Add Local Interpreter**, select **Python**, and choose the interpreter
   inside the environment (`.venv\Scripts\python.exe` on Windows, `.venv/bin/python` on Mac or Linux). Click **OK**.
   You can also do this from **Settings > Python > Interpreter**. PyCharm sometimes detects `.venv` on its own and offers
   it.
4. Open `examples/tutorial/FuelAnalyst_Tutorial.ipynb` and run the first code cell. If PyCharm offers to install or
   configure Jupyter, accept. It should print `FuelAnalyst and companion packages loaded.`
5. If cells do not run, click the Jupyter server widget in the notebook toolbar and choose **Configure Jupyter
   Server**, then select a local server that uses the project interpreter from step 3. The exact options vary between
   PyCharm versions; see JetBrains' [Jupyter notebook documentation](https://www.jetbrains.com/help/pycharm/jupyter-notebook-support.html).

### Other editors

Any tool that can run `.ipynb` files works. For a browser-based option, run `python -m pip install jupyterlab` in the
active environment, then `jupyter lab` from the repository folder.

## 6. Run the tutorial

Run the cells in order. The whole notebook takes a few minutes. See [`README.md`](README.md) for what it covers and
where results are written.

## Troubleshooting

**`python` is not found (Windows).** Reinstall Python and tick **Add python.exe to PATH**, or try `py -m venv .venv`
in place of `python -m venv .venv`. Open a new terminal afterwards.

**The activation script is blocked (Windows PowerShell).** It may say that running scripts is disabled. Run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, answer `Y`, and activate again. Alternatively, use Command
Prompt and run `.venv\Scripts\activate.bat`.

**`ImportError` or `ModuleNotFoundError` in the first cell.** The notebook is using a different Python than the one
you installed into. Check the kernel (VS Code) or interpreter (PyCharm) is the `.venv` one, then restart the kernel.

**The environment is missing from the VS Code kernel list.** Open the Command Palette (`Ctrl+Shift+P`), run
**Developer: Reload Window**, and look again. You can also run **Python: Select Interpreter** and pick `.venv`.

**VS Code cells will not run, or outputs are hidden.** The folder is in Restricted Mode. Open the Command Palette, run
**Workspaces: Manage Workspace Trust**, and choose **Trust**.

**The kernel is found but hangs when you run a cell (VS Code).** Run **Python: Select Interpreter**, choose `.venv`,
then select the kernel again.

**`FileNotFoundError` for a weather file, or a file that starts with `version https://git-lfs`.** Git LFS was not
active when you cloned. From the repository folder run `git lfs install` and then `git lfs pull`.

**The tutorial cannot find the example data.** Open the notebook from inside the cloned repository. The data is part of
the repository (in `examples/data/`), not part of the installed package.

**The install fails on a package with a build error.** Update pip first (`python -m pip install --upgrade pip`) and
check that your Python version is between 3.11 and 3.14.
