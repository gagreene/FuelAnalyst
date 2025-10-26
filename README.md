# Fuel Analyst Dashboard

A Shiny-based web application for analyzing forest fuel data from field surveys.

## 🔥 Features

- **Data Upload**: Upload survey data via ZIP files
- **Fuel Analysis**: Comprehensive fuel loading and tree analysis
- **FOFEM Integration**: Generate FOFEM tree and consumption dataframes
- **Results Download**: Download all results as ZIP or individual CSV files
- **Customizable Parameters**: Configure DBH thresholds, summary categories, and woody debris classifications
- **Data Preview**: View uploaded and analyzed data in interactive tables

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Deployment](#deployment)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Requirements](#requirements)

## 🚀 Quick Start

### Local Development

1. **Clone the repository**

   ```bash
   git clone <your-repo-url>
   cd FuelAnalyst
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Run the app**

   ```bash
   shiny run app.py
   ```

4. **Open in browser**
   - Navigate to `http://localhost:8000`

## 🌐 Deployment

### Automated Deployment (Recommended)

Set up automatic deployment to shinyapps.io using GitHub Actions:

👉 **[GitHub Actions Setup Guide](GITHUB_ACTIONS_SETUP.md)** (5 minutes)

Every time you push to `main` or `master`, the app automatically deploys!

### Manual Deployment

For manual deployment instructions:

👉 **[Full Deployment Guide](DEPLOYMENT_GUIDE.md)**

## 📖 Usage

### 1. Prepare Your Data

Create a ZIP file with this structure:

```
your_data.zip
├── 1_Plot_Attributes/
│   └── survey_0.csv          [REQUIRED]
├── 2_Plants_Regeneration/
│   ├── survey_0.csv          [Optional]
│   └── regeneration_1.csv    [Optional]
├── 3_Trees/
│   ├── survey_0.csv          [Optional]
│   ├── sapling_1.csv         [Optional]
│   └── tree_plot_2.csv       [Optional]
├── 4_Canopy_Cover/
│   ├── survey_0.csv          [Optional]
│   └── canopy_cover_1.csv    [Optional]
└── 5_Woody_Debris/
    └── survey_0.csv          [Optional]
```

### 2. Upload and Analyze

1. **Upload** your ZIP file
2. **Configure** analysis parameters
3. **Run** the analysis
4. **Download** results

### 3. Review Results

- **Master Fuel DataFrame**: Combined fuel analysis results
- **Master Tree DataFrame**: Individual tree measurements and calculations
- **FOFEM Tree DataFrame**: Formatted for FOFEM tree mortality models
- **FOFEM Consume DataFrame**: Formatted for FOFEM fuel consumption models

## 📁 Project Structure

```
FuelAnalyst/
├── app.py                      # Main Shiny application
├── fuel_analyst.py             # Core analysis engine
├── helper.py                   # Utility functions
├── plot_attributes.py          # Plot data processing
├── plants_regen.py             # Plants & regeneration processing
├── trees.py                    # Tree measurements processing
├── canopy_cover.py             # Canopy cover analysis
├── woody_debris.py             # Woody debris analysis
├── fofem_attributes.py         # FOFEM output formatting
├── requirements.txt            # Python dependencies
├── Supporting_Data/            # Reference data files
│   ├── plant_photoload.csv
│   └── tree_parameters.csv
├── .github/
│   └── workflows/
│       └── deploy.yml          # GitHub Actions workflow
├── DEPLOYMENT_GUIDE.md         # Detailed deployment instructions
├── GITHUB_ACTIONS_SETUP.md     # Quick GitHub Actions setup
└── README.md                   # This file
```

## 🛠 Requirements

### Python Version

- Python 3.11 or higher

### Dependencies

```
numpy>=2.3.0
pandas>=2.3.0
scipy>=1.16.0
shiny>=1.0.0
```

See `requirements.txt` for complete list.

## 🔧 Configuration Options

### Analysis Parameters

- Surface Fire Intensity Model (Byram/Other)
- FOFEM Region (InteriorWest/PacificWest/NorthEast/SouthEast)
- Season (Spring/Summer/Fall/Winter)
- Moisture Regime (Wet/Moderate/Dry/Very Dry)

### Stand Summary Settings

- DBH thresholds (small/medium/large)
- Summary categories (total/live/dead/conifer/broadleaf)
- Height metrics (max/mean)
- Crown & fire metrics (min/max/mean)
- Canopy fuel load metrics (min/max/mean/sum)

### Woody Debris Settings

- Canadian classification
- U.S. classification
- Modified classification
- QMD comparison options

## 🔒 Security

- All data is temporary and session-based
- No persistent storage on server
- HTTPS encryption via shinyapps.io
- GitHub Secrets for deployment credentials
- See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for security best practices

## 📊 Outputs

The app generates these output files:

1. **master_fuel_df.csv** - Plot-level fuel summaries
2. **master_tree_df.csv** - Individual tree data with calculated attributes
3. **fofem_tree_df.csv** - FOFEM-formatted tree data
4. **fofem_consume_df.csv** - FOFEM-formatted consumption data
5. **Subfolder outputs** - Intermediate processing results

## 🆘 Support

- **Deployment Issues**: See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- **GitHub Actions**: See [GITHUB_ACTIONS_SETUP.md](GITHUB_ACTIONS_SETUP.md)
- **App Issues**: Check logs in shinyapps.io dashboard

## 📝 License

[Add your license information here]

## 👥 Contributors

[Add contributor information here]

---

**Last Updated:** October 2025

