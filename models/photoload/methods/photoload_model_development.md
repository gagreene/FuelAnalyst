# Development of objective-cover PhotoLoad biomass models for FuelAnalyst

## Scope

This document describes the derivation of nine species-specific equations used
by FuelAnalyst to estimate live surface-plant biomass from percent cover and
plant height. The procedure applied reproducible image classification to the
published PhotoLoad calibration photographs of Keane and Dickinson [1] and
fitted biomass–cover relationships constrained to predict zero biomass at zero
cover. It documents the production workflow used for the FuelAnalyst
paper.

The complete implementation is documented in the
[`models/photoload` README](../README.md).
The source publication is stored at
[the bundled PhotoLoad report](../../../docs/reference/rmrs_gtr190_Kean_and_Dickinson_2007.pdf), and the
81-image calibration fixture is stored at
[`data/paper_calibration.csv`](../data/paper_calibration.csv).

## Source data

The source dataset comprised nine synthetic-fuelbed photographs for each of
nine vascular plant species (81 photographs total) reproduced in Appendix A of
the PhotoLoad report [1]. Within each species series, the photographs
represented increasing dry biomass per unit area. The analysed species were
*Amelanchier alnifolia* (AMAL), *Berberis repens* (MARE),
*Symphoricarpos albus* (SYAL), *Vaccinium globulare* (VAGL),
*Vaccinium scoparium* (VASC), *Arnica latifolia* (ARLA),
*Calamagrostis rubescens* (CARU), *Festuca scabrella* (FESC), and
*Xerophyllum tenax* (XETE).

Biomass values were recorded in kg m⁻². The predictor was objective percent
cover measured from the morphology-specific ensemble selection frequency.

## Photograph extraction and cropping

The embedded raster image was extracted from each of the nine relevant PDF
pages with PyMuPDF. The page layout was divided into its 3 × 3 photograph grid
by detecting near-white row and column gaps. Each square fuelbed photograph
was then isolated through one deterministic cropping procedure with three
components:

1. the dark printed border was detected from near-continuous horizontal and
   vertical runs and excluded;
2. residual scan or print antialiasing was removed independently from each
   edge, with trimming stopped when a clean interior line was reached; and
3. a visible physical foam-board edge or shadow was removed when a local edge
   intensity minimum recovered by more than 15 digital-number units within
   the following four pixels.

The third component used local contrast rather than a fixed brightness
threshold so that dark plant material reaching an image boundary would not be
systematically removed. All border and foam-board-edge corrections therefore
occurred during a single extraction operation and were not evaluated as
alternative segmentation models. Cropped RGB images were saved as JPEG at
quality 95.

Upon inspection of the original Photoload series images, the published SYAL 
sequence was observed to contain an ordering issue. We applied the following 
reassignments to the SYAL series as a correction: 0.08 kg/m^2→0.15 kg/m^2, 
0.10→0.08, 0.12→0.10, and 0.15→0.12 kg m⁻². This correction was performed 
after initial JPEG export to ensure the correct calibration images were used 
in the analysis.

## Objective-cover classification

### Species-level calibration threshold

For each species, RGB values were transformed to CIELAB coordinates. Chroma
was calculated as:

```text
C*ab = sqrt(a*² + b*²)
```

An Otsu threshold was calculated from the lowest-biomass photograph in the
species series and then held constant for all nine photographs of that
species. This avoided independently tuning a threshold to each biomass level.

### Step 1: selection of a common source mask

Three nested source-mask variations were reviewed for all nine species:

1. **CIELAB body:** pixels with chroma greater than the species-level Otsu
   threshold;
2. **refined body + saturation ridges:** the CIELAB body was eroded by one
   pixel, except where boundary chroma exceeded 1.08 times the Otsu threshold,
   and connected saturation ridges were restored; and
3. **refined body + saturation + dark ridges (Variation 3):** connected dark
   lightness ridges were added to Variation 2.

Ridge responses were calculated with the multiscale Meijering filter at
scales 1 and 2. Saturation and dark-lightness ridge responses were retained
when greater than 0.03. A ridge candidate also had to differ from the estimated
foam-board colour. Board colour was estimated as the median CIELAB value of
bright, weakly saturated non-body pixels (HSV saturation <0.12 and value >0.75).
The minimum accepted colour distance was the larger of 6 CIELAB units
or the 99th percentile of colour distances among board-seed pixels.

Small ridge objects containing fewer than three pixels were removed. Remaining
ridge candidates had to begin within two pixels of an existing plant body and
could then be extended through connected candidate pixels for as many as 12
iterations. Neutral ridge detections within 20 pixels of an image edge were
excluded when their chroma was less than 0.75 times the species threshold,
reducing recovery of residual edge cross-hatching. Visual comparison across
the full low-to-high biomass sequence supported Variation 3 as the shared
source mask for the subsequent morphology-specific review.

### Step 2: morphology-specific ensembles

Species were assigned to three morphology groups. Rather than selecting one
refinement parameter, every photograph was processed over a complete,
prespecified parameter range and the resulting cover values were averaged.

#### Broadleaf group

AMAL, ARLA, MARE, SYAL, and VAGL were classified as broadleaf species. Within
Variation 3, high-confidence plant seeds were pixels meeting at least one of
the following CIELAB criteria: lightness `L* < 70`, green direction
`a* < 0`, or strong yellow direction `b* > 25`. Seeds were expanded by
binary dilation but were permitted to grow only through pixels already present
in Variation 3. The range-bound experiment grew each mask one pixel at a time
until another dilation could no longer change it and recorded the last step
that changed every broadleaf and fine-structure calibration mask. One pixel
was the lower bound because it is the smallest nonzero growth operation. The
largest observed last-changing step was 30 px, which established the common
upper bound. Production masks were therefore calculated after every integer
growth step from 1 through 30 px, including the complete observed response.

#### Fine-structure group

VASC and XETE were classified as fine-structure species and evaluated with the
same seeded CIELAB rule and complete 1–30 px growth range.

#### Dense-mat group

CARU and FESC were classified as dense-mat species. A 15-pixel local window
was used to recover dark pixels omitted from Variation 3 when `L* < 50` and
more than 40% of the local window belonged to the source mask. Bright,
weakly-yellow source pixels (`L* > 64` and `b* < 18`) were provisionally
removed as neutral backing material.

Because pale grass blades overlapped the foam board in colour, a structural
rescue was then applied. The maximum bright-ridge and dark-ridge response from
a Sato filter at scales 1, 2, and 3 was calculated. A provisionally removed
pixel was restored only if it (i) exceeded the evaluated ridge threshold, (ii)
was within two dilation steps of the cleaned plant mask, and (iii) occurred
where cleaned plant occupied more than 20% of a 15-pixel local window. The
range-bound experiment recorded the maximum Sato response among pixels that
satisfied all other rescue criteria in every dense-mat photograph. A threshold
of 0.000 was the lower bound because it includes every eligible pixel with a
positive ridge response. The largest eligible response was 0.218704; rounding
upward to the next 0.005 unit established 0.220 as the upper bound and exact
no-rescue endpoint. Production masks were therefore calculated at thresholds
from 0.000 through 0.220 in increments of 0.005.

The production workflow rendered the parameter-specific masks and ensemble
means in paginated panels, with the lowest biomass at the top and highest at
the bottom. The separate
[PhotoLoad source-mask and range-bound experiment](../experiments/README.md)
preserved the per-image measurements and diagnostic plot used to establish
both upper bounds.

### Calculation of objective cover

For each photograph, the binary masks across its morphology-specific parameter
range were averaged pixel by pixel. The resulting selection frequency lies
between zero and one and expresses the fraction of parameter-specific masks in
which a pixel was classified as plant. Objective percent cover was calculated
from the mean selection frequency:

```text
x = 100 × sum(selection frequency) / Ntotal
```

where `Ntotal` was the number of pixels in the cropped photograph. This is
algebraically identical to averaging the objective-cover values across all
parameter-specific masks.

## Biomass-model development

### Candidate equations

Dry biomass `y` (kg m⁻²) was modelled as a function of objective percent
cover `x`. Each candidate was constrained analytically to satisfy
`y(0) = 0`; a synthetic observation at the origin was not added. Five
candidate forms were evaluated:

| Model | Equation | Free coefficients |
|---|---|---:|
| Linear through origin | `y = ax` | 1 |
| Power | `y = ax^b` | 2 |
| Quadratic through origin | `y = ax + bx²` | 2 |
| Saturating | `y = a[1 − exp(−bx)]` | 2 |
| Shifted exponential | `y = a[exp(bx) − 1]` | 2 |

The nine observations for each species were fitted by nonlinear least squares
on the untransformed biomass scale. Power-model starting values were obtained
by log-linear regression, but the reported model was fitted on the original
scale. The residual sum of squares (RSS) was used to calculate fitted RMSE and
the information criteria. For a fitted equation with `p` coefficients, the
effective parameter count was `k = p + 1`, including residual variance:

```text
AIC = n × ln(RSS / n) + 2k
```

```text
AICc = AIC + [2k(k + 1) / (n − k − 1)]
```

and

```text
BIC = n × ln(RSS / n) + k × ln(n)
```

Predictive stability was assessed by leave-one-out cross-validation (LOOCV).
For each of the nine folds, the model was refitted to eight observations and
used to predict the omitted biomass; the nine omitted-observation residuals
were summarized as LOOCV RMSE.

### Multi-criteria model selection

Minimum AICc was treated as one source of evidence rather than an automatic
selection rule. Each final choice considered:

1. nonnegative, physically plausible behaviour over the observed cover range;
2. visual representation of the observed relationship and residual pattern;
3. LOOCV RMSE;
4. AICc, AIC, and BIC, including the magnitude of criterion differences;
5. fitted RMSE and coefficient of determination (R²); and
6. parsimony when competing models received comparable support.

This rule applies to production fitting, sensitivity analyses, and any later
refitting. A minimum-AICc model may be identified for comparison, but no model
may be designated selected or final from AICc alone.

No weighted composite score was used. A model and written rationale were
specified explicitly for each species. Eight selections agreed with the
minimum-AICc model. For SYAL, the quadratic-through-origin model was selected
instead of the linear AICc minimum because it represented the observed
curvature and improved LOOCV RMSE, fitted RMSE, R², and AIC; its ΔAICc of 2.71
was not considered decisive with only nine observations.

The species-level selection evidence was recorded explicitly:

| Code | Selection evidence |
|---|---|
| AMAL | The shifted exponential represented pronounced positive curvature and had the strongest information-criterion support, lowest fitted and LOOCV RMSE, and highest R². |
| MARE | The power model represented modest positive curvature, removed the systematic residual progression of the linear model, and had the strongest overall statistical support. |
| SYAL | The quadratic represented visible curvature and improved predictive and fitted errors relative to the linear AICc minimum; ΔAICc was 2.71. |
| VAGL | The shifted exponential and quadratic were nearly tied; the shifted exponential was marginally better for AICc, AIC, BIC, fitted RMSE, R², and LOOCV RMSE. |
| VASC | The linear model had the strongest AICc support and lowest LOOCV RMSE; curved models added complexity without improving prediction. |
| ARLA | The power model represented modest positive curvature and had the strongest information-criterion, fitted-error, and predictive-error support. |
| CARU | The shifted exponential represented the strong convex rise associated with cover saturation and performed best across the statistical criteria; the fitted quadratic was negative at low positive cover. |
| FESC | The shifted exponential represented the convex relationship and performed best across fitted error, predictive error, and information criteria; the fitted quadratic was negative at low positive cover. |
| XETE | The linear model had the best AICc and effectively tied the shifted exponential for LOOCV RMSE with one fewer coefficient; parsimony and stability favoured the linear form. |

## Final equations and fit statistics

The selected equations estimate biomass at the reference height of the
corresponding PhotoLoad series. Values below are calculated on the raw biomass
scale from the nine objective-cover observations per species.

| Code | Species | Selected model and equation | R² | RMSE (kg m⁻²) | LOOCV RMSE (kg m⁻²) | ΔAICc |
|---|---|---|---:|---:|---:|---:|
| AMAL | *Amelanchier alnifolia* | `y = 0.0690181[exp(0.0240242x) − 1]` | 0.9927 | 0.00625 | 0.01200 | 0.00 |
| MARE | *Berberis repens* | `y = 0.000733871x^1.16779` | 0.9916 | 0.00237 | 0.00379 | 0.00 |
| SYAL | *Symphoricarpos albus* | `y = 0.00119555x + 1.69686 × 10⁻⁵x²` | 0.9174 | 0.01305 | 0.01801 | 2.71 |
| VAGL | *Vaccinium globulare* | `y = 0.398329[exp(0.0109776x) − 1]` | 0.9957 | 0.00480 | 0.00800 | 0.00 |
| VASC | *Vaccinium scoparium* | `y = 0.0025455x` | 0.9588 | 0.01454 | 0.01978 | 0.00 |
| ARLA | *Arnica latifolia* | `y = 0.0005745x^1.16228` | 0.9981 | 0.00110 | 0.00149 | 0.00 |
| CARU | *Calamagrostis rubescens* | `y = 0.0117766[exp(0.0379728x) − 1]` | 0.8155 | 0.05545 | 0.06941 | 0.00 |
| FESC | *Festuca scabrella* | `y = 0.0161917[exp(0.0330081x) − 1]` | 0.9444 | 0.03044 | 0.03896 | 0.00 |
| XETE | *Xerophyllum tenax* | `y = 0.00366616x` | 0.9601 | 0.01459 | 0.01927 | 0.00 |

CARU produced the weakest fit and greatest cross-validated error, consistent
with cover saturation in the dense high-biomass photographs. Consequently,
its estimates should be interpreted with greater uncertainty than those of
the better-fitting broadleaf and forb series.

## Operational height adjustment

The PhotoLoad equations describe biomass at the reference height represented
by each source series. FuelAnalyst adjusts the base prediction linearly for an
observed plant height `H`:

```text
yfield = f(x) × H / Href
```

where `f(x)` is the selected species equation and `Href` is the
series-specific reference height. The reference heights used operationally
are 35.56 cm for AMAL, SYAL, and VAGL; 10.16 cm for MARE; 17.78 cm for VASC;
30.48 cm for ARLA; 20.30 cm for CARU; 30.50 cm for FESC; and 25.40 cm for
XETE. This adjustment preserves the zero-cover constraint and scales all
equation comparisons proportionally with height.

## Reproducibility and quality assurance

The workflow is run from the repository root with:

```powershell
python models/photoload/run_pipeline.py
```

The default source is the bundled report and the default output is the ignored
`../.work` directory. Both the PDF and output path may be
overridden explicitly. The stored report has SHA-256 digest
`14eaeb69784e3f26dee23a67686fad9c86e50099aaca60bcc079f687d1c313c2`.

The production run writes the extracted photographs, source masks, ensemble
selection-frequency images, objective-cover table, candidate statistics,
selected-model summary, model plots, and nine original-versus-ensemble panels.
It also compares all 81
newly calculated cover values with the versioned reference dataset and stops if
the maximum absolute difference exceeds `10⁻⁹` percentage points. The
verified run reproduced the reference objective-cover values with a maximum
difference of `2.84 × 10⁻¹⁴` percentage points.

## Methodological limitations

Each species equation was derived from nine staged photographs, and LOOCV was
performed within this small calibration set. The reported errors therefore
measure internal calibration and cross-validation performance rather than
independent field validation. Extrapolation beyond the observed cover and
biomass ranges is not supported, particularly for convex exponential models.

The residual foam-board cross-hatching in dense-mat photographs represents an
information limitation because its colour and line structure overlap real
grass blades. Averaging the complete ridge-response range incorporates
parameter sensitivity but cannot distinguish cross-hatching from blades when
their image features coincide.

## Reference

1. Keane RE, Dickinson LJ. 2007. *The photoload sampling technique: estimating
   surface fuel loadings from downward-looking photographs of synthetic
   fuelbeds*. General Technical Report RMRS-GTR-190. Fort Collins, CO: U.S.
   Department of Agriculture, Forest Service, Rocky Mountain Research Station;
   https://doi.org/10.2737/RMRS-GTR-190.
