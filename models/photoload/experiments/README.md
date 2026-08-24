# PhotoLoad source-mask and range-bound experiment

This experiment documents the evidence used to define the image-processing
stages and the bounds of the parameter ranges used by the production PhotoLoad
workflow. Complete parameter-specific image panels are production outputs;
they are not duplicated here.

## Step 1 — source-mask comparison

For every species, the first panel compares:

1. CIELAB chroma body;
2. refined body plus connected saturation ridges; and
3. refined body plus connected saturation and dark ridges (Variation 3).

The photographs are first extracted and cropped by the production extraction
process. Printed borders, scan antialiasing, and visible foam-board edges are
removed during that one extraction operation; they are not separate candidate
methods. Variation 3 is the common source mask for Step 2.

## Step 2 — production-range bounds

Species are assigned to three morphology groups:

- Broadleaf (`AMAL`, `ARLA`, `MARE`, `SYAL`, `VAGL`) and fine-structure
  (`VASC`, `XETE`) masks are grown one pixel at a time until another dilation
  cannot alter the selected mask. The last growth step that changed each mask
  is recorded for every calibration photograph.
- For dense-mat species (`CARU`, `FESC`), the maximum Sato response is recorded
  among every provisionally removed pixel that satisfies the spatial rescue
  criteria.

The bounds are therefore defined by algorithm behavior rather than visual
selection. One pixel is the smallest nonzero seeded-growth operation. The
largest last-changing step establishes 30 px as the common upper bound. A
ridge threshold of 0.000 includes every positive eligible response. The
largest observed eligible response is rounded upward to the next 0.005 unit,
establishing 0.220 as the upper bound and exact no-rescue endpoint.

The experiment writes the per-image stabilization steps and eligible-response
maxima, a diagnostic figure, and a manifest containing both the observed
extrema and the resulting production bounds. The production workflow then
uses every integer growth step from 1 through 30 px and every ridge threshold
from 0.000 through 0.220 in increments of 0.005. Objective cover is the
arithmetic mean across the applicable complete range.

Any biomass-model refitting based on these ranges must use the documented
multi-criteria process for every species. Physical behavior, residual shape,
LOOCV RMSE, AICc/AIC/BIC, fitted RMSE, R-squared, and parsimony are considered
together. AICc may be reported as one diagnostic but cannot alone designate a
selected or final model.

## Run

From the repository root, install the PhotoLoad dependencies if needed, then
run the experiment:

```powershell
python -m pip install -e ".[photoload]"
```

```powershell
python models/photoload/experiments/run_range_experiment.py
```

The default output is the ignored `models/photoload/.work/range_experiment`
directory. A different location can be supplied without editing source code:

```powershell
python models/photoload/experiments/run_range_experiment.py --output-dir D:\analysis\photoload-range-experiment
```

The principal output files are:

- `01_source_mask_evaluation/source_mask_cover_by_image.csv`;
- `01_source_mask_evaluation/source_mask_agreement_summary.csv`;
- `02_parameter_bound_derivation/seeded_growth_last_change.csv`;
- `02_parameter_bound_derivation/eligible_ridge_response_maxima.csv`;
- `02_parameter_bound_derivation/parameter_bound_diagnostics.png`; and
- `range_experiment_manifest.json`.

Species-level source-mask panels are stored under
`01_source_mask_evaluation/panels`.
