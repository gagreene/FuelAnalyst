# Frozen PhotoLoad workflow

This directory contains only the production workflow used to derive the nine
PhotoLoad biomass equations reported by FuelAnalyst. The exploratory model and
mask benchmarks remain outside the repository.

The workflow starts from Keane and Dickinson's PhotoLoad report at
[`docs/reference/rmrs_gtr190.pdf`](../../docs/reference/rmrs_gtr190.pdf),
extracts the 81 appendix photographs, creates the final selected masks, measures
objective cover, fits the origin-constrained candidate equations, applies the
documented multi-criteria choice for every species, and produces the final
species panels and model report.

`data/paper_calibration.csv` is a frozen input/regression fixture. It preserves
the biomass labels and analyst means used in the paper, along with the final
objective-cover values. The run fails if newly generated cover differs from
those frozen values.

## Run

Install the package with the PhotoLoad dependencies, then run:

```powershell
python models/photoload/run_pipeline.py
```

The default output is the ignored `models/photoload/.work` directory. Use a
different location without editing source code:

```powershell
python models/photoload/run_pipeline.py --output-dir D:\analysis\photoload
```

The bundled source report is used by default. `--pdf PATH` is available to
verify another copy. The expected report SHA-256 is
`14eaeb69784e3f26dee23a67686fad9c86e50099aaca60bcc079f687d1c313c2`.

Outputs are staged as follows:

1. `01_extracted_images` — the 81 cropped board photographs;
2. `02_source_masks` — the frozen edge-cleaned dual-ridge masks;
3. `03_selected_masks` — the final morphology-group masks;
4. `04_objective_cover` — objective cover and reference differences;
5. `05_biomass_models` — candidate statistics, nine explicit selections, and
   the final overview;
6. `06_species_panels` — original-versus-selected-mask panels; and
7. `run_manifest.json` — input digest and reproducibility summary.

The source publication is:

> Keane, Robert E.; Dickinson, Laura J. 2007. The photoload sampling technique:
> estimating surface fuel loadings from downward-looking photographs of
> synthetic fuelbeds. RMRS-GTR-190. DOI: 10.2737/RMRS-GTR-190.

The visual evidence used to choose the final image methods—and an expanded
review grid—is documented separately in
[`experiments`](experiments/README.md). Those comparisons do not alter the
frozen production selections unless a new decision is explicitly adopted.
