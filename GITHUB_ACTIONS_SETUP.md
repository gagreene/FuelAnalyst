# GitHub Actions Auto-Deployment Setup Guide

This guide will help you set up automatic deployment to shinyapps.io using GitHub Actions.

## ⚡ Quick Setup (5 minutes)

### Step 1: Get shinyapps.io Credentials

1. Login to [shinyapps.io](https://www.shinyapps.io/)
2. Navigate to: **Account** → **Tokens**
3. Click **Show** or **Add Token**
4. Copy these 3 values:
   - **Account Name** (e.g., `yourname`)
   - **Token** (long string starting with letters)
   - **Secret** (long random string)

### Step 2: Add Secrets to GitHub

1. Go to your GitHub repository
2. Click: **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret** button
4. Add these 3 secrets:

   **Secret 1:**

   - Name: `SHINYAPPS_ACCOUNT`
   - Value: Your account name from Step 1

   **Secret 2:**

   - Name: `SHINYAPPS_TOKEN`
   - Value: Your token from Step 1

   **Secret 3:**

   - Name: `SHINYAPPS_SECRET`
   - Value: Your secret from Step 1

### Step 3: Enable GitHub Actions

1. Ensure the workflow file exists: `.github/workflows/deploy.yml`
2. Go to **Settings** → **Actions** → **General**
3. Under "Actions permissions", select **Allow all actions and reusable workflows**
4. Click **Save**

### Step 4: Test the Deployment

**Option A: Make a commit**

```bash
git add .
git commit -m "Test GitHub Actions deployment"
git push origin main
```

**Option B: Manual trigger**

1. Go to **Actions** tab
2. Select **Deploy to shinyapps.io**
3. Click **Run workflow** → **Run workflow**

### Step 5: Monitor Deployment

1. Go to the **Actions** tab in GitHub
2. Click on the running workflow
3. Watch the deployment progress
4. Look for the deployment URL in the logs

## ✅ Verification

Once deployment completes, your app will be available at:

```
https://[YOUR_ACCOUNT].shinyapps.io/fuelanalyst/
```

## 🔄 How It Works

After setup, every time you:

1. Make changes to your code
2. Commit and push to `main` or `master` branch
3. GitHub Actions automatically deploys to shinyapps.io

## 🔒 Security Notes

✅ **DO:**

- Keep your repository private for sensitive projects
- Store credentials ONLY in GitHub Secrets
- Rotate tokens every 90 days
- Enable 2FA on GitHub account

❌ **DON'T:**

- Never commit credentials to code
- Never share GitHub secrets
- Don't push sensitive data to repository

## 🐛 Troubleshooting

### Deployment fails immediately

**Check:**

- Are all 3 secrets set correctly?
- Are secret names spelled exactly as shown?
- Is your shinyapps.io token still valid?

### Deployment timeout

**Try:**

- Check app size (must be < 1GB)
- Verify `requirements.txt` is correct
- Test locally first: `shiny run app.py`

### App deploys but doesn't work

**Verify:**

- All dependencies in `requirements.txt`
- Python version compatibility
- Check logs at shinyapps.io dashboard

## 📚 Additional Resources

- [Full Deployment Guide](DEPLOYMENT_GUIDE.md)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [shinyapps.io Documentation](https://docs.posit.co/shinyapps.io/)

## 🆘 Need Help?

1. Check the [Actions tab](../../actions) for error logs
2. View the [Full Deployment Guide](DEPLOYMENT_GUIDE.md)
3. Check shinyapps.io dashboard logs

---

**Last Updated:** October 2025
