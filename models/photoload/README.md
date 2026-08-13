# Frozen PhotoLoad workflow

This directory contains the production workflow used to derive the nine
PhotoLoad biomass equations reported by FuelAnalyst. The scientific methods
are documented in
[`methods/photoload_model_development.md`](methods/photoload_model_development.md).

Starting from Keane and Dickinson's PhotoLoad report at
[`docs/reference/rmrs_gtr190_Kean_and_Dickinson_2007.pdf`](../../docs/reference/rmrs_gtr190_Kean_and_Dickinson_2007.pdf),
the workflow extracts 81 appendix photographs, creates a common source mask,
calculates morphology-group ensemble cover, fits origin-constrained candidate
equations, applies the explicit multi-criteria choice for every species, and
produces the final model reports.

For broadleaf and fine-structure species, cover is averaged over seeded-growth
masks from 1 through 30 px. For dense-mat species, cover is averaged over Sato
ridge-rescue masks at thresholds from 0.000 through 0.220 in increments of
0.005. The stored selection-frequency images preserve each pixel's fraction of
ensemble masks rather than reducing the result to one binary threshold choice.

`data/paper_calibration.csv` is the frozen regression fixture. It preserves the
biomass labels and analyst means, together with the final ensemble-cover
values. A production run fails if regenerated cover differs from the fixture.

## Run

Install the package with the PhotoLoad dependencies, then run:

```powershell
python models/photoload/run_pipeline.py
```

The default output is the ignored `models/photoload/.work` directory. A
different location can be supplied without editing source code:

```powershell
python models/photoload/run_pipeline.py --output-dir D:\analysis\photoload
```

The bundled report is used by default. `--pdf PATH` can verify another copy.
Its expected SHA-256 digest is
`14eaeb69784e3f26dee23a67686fad9c86e50099aaca60bcc079f687d1c313c2`.

Outputs are staged as follows:

1. `01_extracted_images` — 81 cropped board photographs;
2. `02_source_masks` — edge-cleaned dual-ridge source masks;
3. `03_ensemble_frequency` — morphology-ensemble selection frequencies;
4. `04_objective_cover` — ensemble cover and regression-fixture differences;
5. `05_biomass_models` — candidate statistics, nine explicit multi-criteria
   selections, and the final overview;
6. `06_species_panels` — originals and ensemble-frequency visualizations;
7. `07_parameter_panels` — paginated, low-to-high biomass panels showing every
   parameter-specific mask in the production ensemble; and
8. `run_manifest.json` — input digest and reproducibility summary.

The source publication is:

> Keane, Robert E.; Dickinson, Laura J. 2007. The photoload sampling technique:
> estimating surface fuel loadings from downward-looking photographs of
> synthetic fuelbeds. RMRS-GTR-190. DOI: 10.2737/RMRS-GTR-190.

The separate [`experiments`](experiments/README.md) workflow records how the
30 px and 0.220 range limits were established. The complete masks within those
ranges are rendered by the production workflow.
