# Survey123 forms

The five field forms that collect the data FuelAnalyst reads. Each folder is one Survey123 form: the XLSForm
(`.xlsx`), its `media/` folder, and an empty `.xml` placeholder.

| Folder | Form |
|---|---|
| `CWC Fuels 1 - Plot Attributes` | Plot attributes (also selects which of the other forms apply to each plot) |
| `CWC Fuels 2 - Plants and Regen` | Surface substrate, plant species cover, and tree regeneration |
| `CWC Fuels 3 - Trees` | Trees and saplings |
| `CWC Fuels 4 - Canopy Cover` | Canopy cover transects |
| `CWC Fuels 5 - Woody Debris` | Woody debris transects |

## Recording sampled forms and tree presence

Plot Attributes `form_select` records which forms were collected. Tick `trees` only when the Trees sampling was completed. If Trees is unticked, FuelAnalyst ignores tree inputs for fire-model preparation and selects the surface model from dominant substrate; a missing Trees form is not an error.

The Trees form asks `tree_large_present`, `tree_small_present`, and `sapling_present` as yes/no radio questions. Answer **N** for each sampling class confirmed absent. Three N answers on a uniquely identified parent establish no trees without synthetic repeat records. Fully covered observations containing only dead trees can also establish no live trees. Without valid live observations, missing class evidence or unknown live counts cannot establish absence. A ticked Trees form with unresolved observations or a missing parent is omitted from ConPyro and FOFEM consumption model inputs and reported in `fuelanalyst_errors.csv`. Existing species/protocol errors serve as that plot's diagnostic; other unresolved observations use `tree_model_inputs_unknown`.

See [surface-model assignment](../../TECHNICAL_REFERENCE.md#surface-model-assignment-and-grass-inputs) for the complete rules and the distinction between inventory summaries and model inputs.

## Trees sampling protocol metadata

Trees form version `2026.11.06` includes a hidden string question named `sampling_protocol`, defaulting to `CWC`, immediately before `tree_large_present`. It is stored on the parent survey record. Republish the form to collect this field. For imported non-CWC observations, supply their actual protocol label in the processing input. FuelAnalyst's default `protocol_column=None` is unchanged, so older exports without this field still work with default settings.

## Opening a form in Survey123 Connect

1. Copy the form's whole folder into `ArcGIS\My Survey Designs` in your user folder (a subfolder of it also works).
2. Start Survey123 Connect, or refresh its survey list. The form is listed once the folder is there.
3. Open the form. Connect compiles it from the `.xlsx` and creates the files it needs.

Connect lists a folder only if it contains a `<form name>.xml` file, so the empty placeholder must stay beside the
`.xlsx`. It can be empty: Connect replaces it with the compiled form when the form is opened.

Keep the `media/` folder with the `.xlsx`. The Plants form builds its species list from `media/plant_photoload.csv`, and
the Trees form looks up each tree's type in `media/Tree_Types.csv`. Without them the form does not compile.

## Publishing the forms

The forms do not work for your crews until they are published through ArcGIS Online. Opening a form in Survey123
Connect only lets you review and edit it. Publish every form your crews will use to your own ArcGIS Online account (Connect
asks you to sign in to it), and publish a form again after you change it, for example to add a species, so that crews get
the new version. For the steps, see ESRI's instructions:
[Publish a survey](https://doc.arcgis.com/en/survey123/create/connect/publishsurvey.htm).

The data that crews send are stored in the account that publishes the form, so publish from the account that should own
your data.

## What belongs in the repository

Only the `.xlsx`, the `media/` folder, and the empty `.xml` placeholder. Connect generates the rest when it opens a form
(`.gpkg`, `.info`, `.itemInfo`, `.webform`, `debug/`, `scripts/`), and the `.itemInfo` also holds the identifiers of the
portal item and its owner, so these files are ignored (see `.gitignore`).

Opening a form in place changes the placeholder `.xml` (Connect fills it in). To put it back, run
`git checkout -- "docs/survey123/survey123_forms/*/*.xml"`.

To change a form, edit it in Survey123 Connect, then copy only the `.xlsx` and `media/` back here.

## Species lists

The Plants form's species list is `media/plant_photoload.csv`, which must stay identical to
`src/fuel_analyst/supporting_data/plant_photoload.csv`, and the Trees form's tree types come from
`media/Tree_Types.csv`. To add a species, follow
[Updating plant_photoload.csv and tree_parameters.csv](../../CONTRIBUTION_PROCEDURES.md#updating-plant_photoloadcsv-and-tree_parameterscsv).
