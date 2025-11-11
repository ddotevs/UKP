# Quick Setup Guide - AWS App Runner Deployment

## Option 1: Automated Setup (Recommended)

Run the setup script to create all AWS resources automatically:

```bash
# 1. Configure AWS CLI (if not already done)
aws configure

# 2. Run setup script
./setup-aws.sh

# 3. Add GitHub secret (from script output)
# Go to: https://github.com/ddotevs/UKP/settings/secrets/actions
# Add: AWS_ROLE_ARN = <value from script>

# 4. Push to deploy
git push origin main
```

## Option 2: AWS Console Setup (Simpler, Manual)

If you prefer using the AWS Console:

### Step 1: Create ECR Repository

1. Go to AWS Console → ECR → Repositories → Create repository
2. Name: `ukp-app`
3. Enable "Scan on push"
4. Click "Create repository"

### Step 2: Create App Runner Service

1. Go to AWS Console → App Runner → Create service
2. Choose **"Container registry"** → **"Amazon ECR"**
3. Select repository: `ukp-app`
4. Image tag: `latest` (initially, GitHub Actions will push here)
5. Service name: `ukp-service`
6. Configure:
   - **CPU**: 0.25 vCPU
   - **Memory**: 0.5 GB
   - **Port**: 8501
   - **Health check path**: `/_stcore/health`
7. Click "Create & deploy"

**Note**: The service will fail initially until you push an image. That's expected!

### Step 3: Set Up GitHub Actions

1. **Configure OIDC Provider** (one-time, if not done):
   - Go to IAM → Identity providers → Add provider
   - Provider: `https://token.actions.githubusercontent.com`
   - Audience: `sts.amazonaws.com`

2. **Create IAM Role for GitHub**:
   ```bash
   # Run this script to create the role
   ./setup-aws.sh
   # Or manually create role with trust policy allowing GitHub OIDC
   ```

3. **Add GitHub Secret**:
   - Go to: https://github.com/ddotevs/UKP/settings/secrets/actions
   - Add secret: `AWS_ROLE_ARN` = (ARN from step 2)

### Step 4: Deploy

Push to main branch:
```bash
git push origin main
```

GitHub Actions will build and deploy automatically!

## Option 3: Direct GitHub Integration (Easiest Initial Setup)

App Runner can connect directly to GitHub (no ECR needed initially):

1. Go to AWS Console → App Runner → Create service
2. Choose **"Source code repository"** → **"GitHub"**
3. Connect your GitHub account
4. Select repository: `ddotevs/UKP`
5. Branch: `main`
6. Build settings:
   - Build command: `docker build -t ukp-app .`
   - Start command: `streamlit run app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true`
7. Configure service (same as Option 2)
8. Click "Create & deploy"

**Note**: This method auto-deploys on every push but doesn't use GitHub Actions.

## Which Option Should I Choose?

- **Option 1**: Best for full automation and CI/CD control
- **Option 2**: Good balance of automation and control
- **Option 3**: Simplest setup, but less control over deployment process

## After Setup

Your app will be available at:
```
https://<service-id>.<region>.awsapprunner.com
```

Find the URL in AWS Console → App Runner → Your service → Default domain.

## Troubleshooting

### Service fails to start
- Check that Dockerfile builds locally: `docker build -t test .`
- Verify port is 8501 in both Dockerfile and App Runner config
- Check CloudWatch logs in AWS Console

### GitHub Actions fails
- Verify `AWS_ROLE_ARN` secret is set correctly
- Check OIDC provider is configured
- Review GitHub Actions logs for specific errors

### Can't access app
- Wait 2-3 minutes for initial deployment
- Check service status is "Running"
- Verify health check path is correct

