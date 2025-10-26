# Fuel Analyst - Deployment Guide for shinyapps.io

## Overview

This guide explains how to deploy the Fuel Analyst Shiny app to shinyapps.io. The app has been updated to work without local file paths by using ZIP file upload/download functionality.

---

## Changes for shinyapps.io Compatibility

### What Changed

1. **Removed hardcoded file paths** - No more `input_folder` and `output_folder` text boxes
2. **Added ZIP upload** - Users upload a ZIP file containing their survey data
3. **Added ZIP download** - Users download all results as a ZIP file
4. **Temporary file storage** - Uses Python's `tempfile` module for temporary directories
5. **In-memory processing** - All file operations work in temporary locations

### Key Features

- ✅ **Upload**: Single ZIP file with all survey data
- ✅ **Process**: Analysis runs on uploaded data
- ✅ **Download**: Get all results as ZIP or individual CSV files
- ✅ **Preview**: View data before and after analysis
- ✅ **No persistence required**: Everything is session-based

---

## Prerequisites

1. **shinyapps.io Account**

   - Create free account at https://www.shinyapps.io/
   - Get your account token and secret

2. **Install Required Python Packages**

   ```bash
   pip install rsconnect-python shiny pandas numpy scipy
   ```

3. **Verify App Works Locally**
   ```bash
   shiny run app.py
   ```

---

## Deployment Steps

### Step 1: Prepare Your Project

Ensure your project has these files:

```
FuelAnalyst/
├── app.py                          # Main Shiny app
├── fuel_analyst.py                 # Core analysis functions
├── helper.py                       # Helper functions
├── plot_attributes.py              # Plot processing
├── plants_regen.py                 # Plants processing
├── trees.py                        # Tree processing
├── canopy_cover.py                 # Canopy cover processing
├── woody_debris.py                 # Woody debris processing
├── fofem_attributes.py             # FOFEM processing
├── requirements.txt                # Python dependencies
└── Supporting_Data/
    ├── plant_photoload.csv
    └── tree_parameters.csv
```

### Step 2: Configure rsconnect

```bash
# Set up your shinyapps.io account
rsconnect add \
    --account <YOUR_ACCOUNT_NAME> \
    --name <YOUR_ACCOUNT_NAME> \
    --token <YOUR_TOKEN> \
    --secret <YOUR_SECRET>
```

Replace placeholders with your actual credentials from shinyapps.io Account Settings.

### Step 3: Deploy to shinyapps.io

```bash
# From your project directory
rsconnect deploy shiny . \
    --name <YOUR_ACCOUNT_NAME> \
    --title FuelAnalyst
```

Or use the shorter command:

```bash
rsconnect deploy shiny . --title FuelAnalyst
```

### Step 4: Monitor Deployment

- Watch the console for deployment progress
- Look for deployment URL (e.g., `https://<account>.shinyapps.io/fuelanalyst/`)
- First deployment may take 5-10 minutes

---

## requirements.txt for Deployment

Make sure your `requirements.txt` includes:

```
numpy>=2.3.0
pandas>=2.3.0
scipy>=1.16.0
shiny>=1.0.0
```

---

## User Workflow on shinyapps.io

### For Users

1. **Prepare ZIP File**

   - Create folder structure:
     ```
     Survey_Data/
     ├── 1_Plot_Attributes/
     │   └── survey_0.csv
     ├── 2_Plants_Regeneration/
     │   └── survey_0.csv
     ├── 3_Trees/
     │   ├── survey_0.csv
     │   ├── sapling_1.csv
     │   └── tree_plot_2.csv
     ├── 4_Canopy_Cover/
     │   └── survey_0.csv
     └── 5_Woody_Debris/
         └── survey_0.csv
     ```
   - Compress into ZIP file

2. **Upload Data**

   - Go to deployed app URL
   - Click "Upload Input Data (ZIP)"
   - Select your prepared ZIP file
   - Wait for extraction confirmation

3. **Configure Analysis**

   - Set Fire Intensity Model
   - Choose FOFEM options
   - (Optional) Expand Advanced Settings

4. **Run Analysis**

   - Click "Run Analysis" button
   - Monitor progress in "Analysis Status" tab
   - Wait for completion (may take several minutes)

5. **Download Results**
   - Go to "Results Summary" tab
   - Click "Download All Results (ZIP)" for everything
   - Or download individual CSV files

---

## Troubleshooting

### GitHub Actions Deployment Issues

**Workflow not running**

- Check if `.github/workflows/deploy.yml` exists in your repo
- Ensure you pushed to `main` or `master` branch
- Check Actions tab for error messages
- Verify repository has Actions enabled (Settings → Actions)

**Error: "Secret not found"**

- Verify secrets are set in repository Settings → Secrets and variables → Actions
- Check secret names match exactly: `SHINYAPPS_ACCOUNT`, `SHINYAPPS_TOKEN`, `SHINYAPPS_SECRET`
- Secrets are case-sensitive

**Error: "rsconnect deploy failed"**

- Check that your shinyapps.io token is still valid
- Token may have expired - regenerate in shinyapps.io and update GitHub secret
- View full logs in Actions tab for detailed error messages

**Error: "No space left on device"**

- Your app may be too large for shinyapps.io
- Check deployed size (should be under 1GB)
- Remove unnecessary files from deployment
- Add `.gitignore` patterns for large data files

**Deployment succeeds but app doesn't work**

- Check requirements.txt includes all dependencies
- View app logs in shinyapps.io dashboard
- Test locally with `shiny run app.py` before pushing
- Check Python version compatibility (workflow uses 3.11)

### Manual Deployment Issues

**Error: "Could not find rsconnect"**

```bash
pip install rsconnect-python
```

**Error: "Invalid token"**

- Regenerate token in shinyapps.io settings
- Re-run `rsconnect add` command

**Error: "Deployment timeout"**

- Check file sizes (keep under 1GB)
- Ensure requirements.txt is correct
- Try deploying again

### Runtime Issues

**Error: "Please upload a ZIP file first"**

- Users must upload data before running analysis
- Check ZIP file structure matches requirements

**Error: "Invalid ZIP file"**

- Ensure file is properly zipped
- Avoid nested ZIP files
- Use standard compression (no encryption)

**Error: "Memory exceeded"**

- Large datasets may exceed shinyapps.io limits
- Free tier: 1GB RAM
- Consider upgrading plan or reducing data size

**Download buttons not working**

- Ensure analysis completed successfully
- Check browser console for errors
- Try different browser

---

## Limits and Considerations

### shinyapps.io Free Tier Limits

- **Active hours**: 25 hours/month
- **RAM**: 1 GB
- **Concurrent connections**: 5
- **Idle timeout**: 15 minutes
- **Max deployment size**: 1 GB

### Best Practices

1. **File Size**: Keep ZIP files under 100MB
2. **Processing Time**: Large analyses may timeout (15 min limit)
3. **Concurrent Users**: Limited to 5 on free tier
4. **Data Privacy**: Data is temporary (deleted after session)
5. **Session Management**: Users should download results before closing

### Upgrading

For larger projects, consider:

- **Paid tiers**: More RAM, longer timeouts, more users
- **Alternative hosting**: RStudio Connect, AWS, Heroku
- **Local deployment**: Run on internal server

---

## Automated Deployment with GitHub Actions (Recommended)

### Overview

GitHub Actions can automatically deploy your app to shinyapps.io whenever you push changes to your repository. This is the most efficient way to keep your deployed app up-to-date.

### Setup Steps

#### 1. Get Your shinyapps.io Credentials

1. Log in to https://www.shinyapps.io/
2. Go to **Account Settings** → **Tokens**
3. Click **Show** on an existing token or **Add Token** for a new one
4. Copy these three values:
   - Account Name
   - Token
   - Secret

#### 2. Add Secrets to GitHub Repository

1. Go to your GitHub repository
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret** and add these three secrets:

   | Secret Name         | Value             |
   | ------------------- | ----------------- |
   | `SHINYAPPS_ACCOUNT` | Your account name |
   | `SHINYAPPS_TOKEN`   | Your token value  |
   | `SHINYAPPS_SECRET`  | Your secret value |

⚠️ **Important**: Never commit these credentials to your code!

#### 3. Workflow File

The workflow file is already set up at `.github/workflows/deploy.yml`. It will:

- ✅ Trigger on every push to `main` or `master` branch
- ✅ Set up Python environment
- ✅ Install all dependencies
- ✅ Deploy to shinyapps.io
- ✅ Provide deployment status

#### 4. How It Works

1. **Make changes** to your code locally
2. **Commit and push** to GitHub:
   ```bash
   git add .
   git commit -m "Update feature X"
   git push origin main
   ```
3. **GitHub Actions automatically**:
   - Detects the push
   - Runs the deployment workflow
   - Deploys to shinyapps.io
   - Reports success/failure

#### 5. Monitor Deployments

- Go to your GitHub repository
- Click the **Actions** tab
- View deployment progress and logs
- Check for success ✅ or failure ❌

#### 6. Manual Deployment Trigger

You can also trigger deployment manually:

1. Go to **Actions** tab in GitHub
2. Select **Deploy to shinyapps.io** workflow
3. Click **Run workflow**
4. Choose branch and click **Run workflow**

### Benefits of GitHub Actions

- 🚀 **Automatic**: Deploy on every push
- 🔒 **Secure**: Credentials stored as GitHub secrets
- 📊 **Visible**: See deployment history and logs
- ⏪ **Rollback**: Easy to revert to previous commits
- 🔄 **Consistent**: Same deployment process every time

---

## Manual Deployment (Alternative)

If you prefer to deploy manually instead of using GitHub Actions:

### Method 1: Manual Redeploy

```bash
# Make your changes locally
# Test locally: shiny run app.py
# Deploy updates
rsconnect deploy shiny . --title FuelAnalyst
```

### Method 2: Version Control

```bash
# Tag your version
git tag -a v1.0.0 -m "Initial production release"

# Deploy
rsconnect deploy shiny . --title FuelAnalyst

# If issues, rollback in shinyapps.io dashboard
```

---

## Monitoring

### View Logs

```bash
rsconnect show logs --name <YOUR_ACCOUNT_NAME> --title FuelAnalyst
```

### Dashboard Metrics

- Visit https://www.shinyapps.io/admin
- View usage statistics
- Monitor errors
- Check active connections

---

## Example Deployment

```bash
# Full deployment example
cd /path/to/FuelAnalyst

# Test locally first
shiny run app.py

# Configure rsconnect (first time only)
rsconnect add \
    --account myaccount \
    --name myaccount \
    --token abc123... \
    --secret xyz789...

# Deploy
rsconnect deploy shiny . \
    --name myaccount \
    --title FuelAnalyst

# View logs
rsconnect show logs \
    --name myaccount \
    --title FuelAnalyst
```

---

## Security Considerations

1. **Data Privacy**: All uploaded data is temporary
2. **No Persistence**: Data deleted when session ends
3. **HTTPS**: All traffic encrypted via shinyapps.io
4. **Token Security**: Keep deployment tokens secure
5. **Access Control**: Configure in shinyapps.io dashboard

### GitHub Actions Security

When using GitHub Actions for deployment:

1. **Never commit credentials** to your repository
2. **Use GitHub Secrets** for all sensitive information
3. **Limit secret access** to necessary workflows only
4. **Rotate tokens regularly** (every 90 days recommended)
5. **Use branch protection** to control who can trigger deployments
6. **Review workflow runs** in the Actions tab regularly
7. **Enable notifications** for failed deployments

### Protecting Your Private Repository

1. **Repository Access**: Keep repo private, control collaborators
2. **GitHub Secrets**: Only accessible to repository admins
3. **Workflow Permissions**: Configure in repository settings
4. **Audit Logs**: Review Actions logs for unauthorized access attempts
5. **Two-Factor Authentication**: Enable on your GitHub account

---

## Support and Resources

- **Shiny Documentation**: https://shiny.posit.co/py/
- **shinyapps.io Docs**: https://docs.posit.co/shinyapps.io/
- **rsconnect-python**: https://github.com/rstudio/rsconnect-python
- **Community Forum**: https://community.rstudio.com/

---

## Quick Reference

### Deploy Command

```bash
rsconnect deploy shiny . --title FuelAnalyst
```

### Check Status

```bash
rsconnect list
```

### View Logs

```bash
rsconnect show logs --title FuelAnalyst
```

### Terminate App

```bash
rsconnect terminate --title FuelAnalyst
```

---

_Last Updated: October 2025_
