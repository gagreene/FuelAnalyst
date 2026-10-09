# Release notes

## 0.1.1 (unreleased)

- Fuel-bed depth now uses the cover-weighted heights of all usable recorded plant species. Missing species or height observations no longer erase earlier contributions. Empty usable observations remain missing in the plant output.
- Plot canopy cover now averages usable records for transect IDs 1 and 2. A single transect retains its measured percentage; wholly excluded or absent observations do not count as zero cover.
- Duplicate eligible canopy records receive one weight per record rather than summed contributions divided by two. Per-transect diagnostic columns retain their sums; duplicate-heavy inputs can therefore disagree with plot means. No automatic deduplication is performed.
- Tallied woody-debris biomass and both optional QMD comparison masses now convert volume using specific gravity once. Their volume already includes slope-corrected transect length, so the repeated slope multiplier has been removed.
- Woody transect slope correction now uses the exact horizontal projection, `sqrt(1 + (slope_percent / 100)^2)`, instead of squaring the angle in radians. This changes measured and tallied woody loads on sloped plots. The pooled horizontal-length aggregation remains unchanged; flat-transect results are unchanged.
- The consumption CSV still rounds fuel-bed depth to two decimals and replaces missing depth with 0 m. Numeric zero reaches both emissions routes; it does not invoke pyfofem's 0.3 m missing-value fallback. Tree fuel strata gap continues to use the separate field-measured tree fuel-bed height.
- Missing canopy remains missing in the canopy component. The existing ConPyro behavior of exporting zero cover with no density class remains unchanged.

Regenerate previously processed plant, canopy, woody, ConPyro, and FOFEM outputs where these corrections apply. Rebuild weather/plot merges from fresh plot attributes before rerunning fire behavior and emissions; an existing weather-merged file can contain stale fuel values. Existing weather observations do not need to be re-extracted.
