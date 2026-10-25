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

## Opening a form in Survey123 Connect

1. Copy the form's whole folder into `ArcGIS\My Survey Designs` in your user folder (a subfolder of it also works).
2. Start Survey123 Connect, or refresh its survey list. The form is listed once the folder is there.
3. Open the form. Connect compiles it from the `.xlsx` and creates the files it needs.

Connect lists a folder only if it contains a `<form name>.xml` file, so the empty placeholder must stay beside the
`.xlsx`. It can be empty: Connect replaces it with the compiled form when the form is opened.

Keep the `media/` folder with the `.xlsx`. The Plants form builds its species list from `media/plant_photoload.csv`, and
the Trees form looks up each tree's type in `media/Tree_Types.csv`. Without them the form does not compile.

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
