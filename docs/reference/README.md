# References

`Appendix 1 Results Data Frames Field Names Description.xlsx` documents fields
in the generated FuelAnalyst result tables. Because some outputs use
model-required U.S. units while the core calculations are primarily metric,
consult the workbook before downstream analysis.

The [Keane and Dickinson (2007) PhotoLoad report](https://doi.org/10.2737/RMRS-GTR-190)
is the source publication for the production PhotoLoad workflow in
[`models/photoload`](../../models/photoload/README.md). The
[US Forest Service PDF](https://research.fs.usda.gov/download/treesearch/26755.pdf)
is downloaded and verified on each default run.

Keane, Robert E.; Dickinson, Laura J. 2007. *The photoload sampling technique:
estimating surface fuel loadings from downward-looking photographs of synthetic
fuelbeds.* General Technical Report RMRS-GTR-190. Fort Collins, CO: U.S.
Department of Agriculture, Forest Service, Rocky Mountain Research Station.
DOI: [10.2737/RMRS-GTR-190](https://doi.org/10.2737/RMRS-GTR-190).

The workflow expects SHA-256 digest
`14eaeb69784e3f26dee23a67686fad9c86e50099aaca60bcc079f687d1c313c2`.

The derivation of the objective-cover biomass equations is documented in
[the PhotoLoad model-development methods](../../models/photoload/methods/photoload_model_development.md).
