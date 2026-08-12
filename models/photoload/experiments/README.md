# PhotoLoad method-selection experiments

This directory preserves only the visual comparisons that support the final
PhotoLoad image-method decisions. It does not restore the discarded early
classification attempts or the broader exploratory work.

The experiment is deliberately separated from the frozen production workflow
in the parent directory. Its current selections remain 2 px for broadleaf
species, 4 px for fine-structure species, and ridge rescue 0.045 for dense-mat
species, but the expanded panels allow those decisions to be reviewed again.

## Step 1 — source-mask comparison

For every species, the first panel compares:

1. CIELAB chroma body;
2. refined body plus connected saturation ridges; and
3. refined body plus connected saturation and dark ridges (Variation 3).

The photographs are first extracted and cropped by the production extraction
process. Printed borders, scan antialiasing, and visible foam-board edges are
removed during that one extraction operation; they are not presented as
separate candidate methods.

## Step 2 — morphology-group comparisons

Variation 3 is the common input to all Step 2 candidates:

- Broadleaf (`AMAL`, `ARLA`, `MARE`, `SYAL`, `VAGL`): seeded CIELAB color
  support grown 2 through 12 px. The current selection is 2 px.
- Fine structure (`VASC`, `XETE`): the same 2 through 12 px sweep. The current
  selection is 4 px.
- Dense mat (`CARU`, `FESC`): expanded neutral cleanup without rescue, followed
  by Sato ridge-rescue thresholds 0.010 through 0.095 in increments of 0.005.
  The current selection is 0.045.

The historically saved comparisons used 2, 4, 6, 8, and 12 px and ridge
thresholds 0.045, 0.055, and 0.070. The denser grids are intentional additions
for the new review; the underlying algorithms are unchanged.

Each species panel places the lowest-biomass image at the top and the
highest-biomass image at the bottom. Masks show selected pixels from the
original photograph on white, with objective cover printed above every result.
Analyst cover is shown only as a comparison guide, not as ground truth.

## Run

From the repository root:

```powershell
python models/photoload/experiments/run_comparisons.py
```

The default output is the ignored `models/photoload/.work/experiments`
directory. A different location can be provided without changing source code:

```powershell
python models/photoload/experiments/run_comparisons.py --output-dir D:\analysis\photoload-review
```

The command writes the extracted photographs, nine Step 1 panels, nine Step 2
panels, per-image cover values, analyst-agreement summaries, and a manifest
that distinguishes historically reviewed values from the expanded review grid.
