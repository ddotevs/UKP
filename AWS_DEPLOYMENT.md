# Automated AWS Deployment Guide

This guide will help you set up automated deployment of the UKP app to AWS App Runner using GitHub Actions.

## Overview

The automated deployment setup includes:
- **AWS App Runner**: Fully managed container service (auto-scaling, HTTPS)
- **ECR (Elastic Container Registry)**: Docker image storage
- **GitHub Actions**: CI/CD pipeline that builds and deploys on every push
- **OIDC Authentication**: Secure AWS access from GitHub without storing credentials

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **AWS CLI** installed and configured (`aws configure`)
3. **GitHub repository** (already set up: `ddotevs/UKP`)
4. **jq** installed (for JSON parsing in scripts)

## Quick Start

### Step 1: Run Setup Script

The setup script will create all necessary AWS resources:

```bash
# Make sure AWS CLI is configured
aws configure

# Run the setup script
./setup-aws.sh
```

The script will:
- Create ECR repository for Docker images
- Create IAM roles for App Runner and GitHub Actions
- Create App Runner service
- Output the GitHub secret you need to add

### Step 2: Configure GitHub Secrets

1. Go to your GitHub repository: https://github.com/ddotevs/UKP/settings/secrets/actions
2. Click "New repository secret"
3. Add the secret:
   - **Name**: `AWS_ROLE_ARN`
   - **Value**: (Copy from setup script output)

### Step 3: Configure GitHub OIDC Provider (One-time setup)

If you haven't set up OIDC for GitHub Actions before:

1. Go to AWS IAM Console → Identity providers
2. Click "Add provider" → "OpenID Connect"
3. Provider URL: `https://token.actions.githubusercontent.com`
4. Audience: `sts.amazonaws.com`
5. Click "Add provider"

The setup script will create the IAM role, but you need the OIDC provider first.

### Step 4: Deploy!

Simply push to the `main` branch:

```bash
git add .
git commit -m "Trigger deployment"
git push origin main
```

GitHub Actions will automatically:
1. Build the Docker image
2. Push to ECR
3. Deploy to App Runner

## Manual Setup (Alternative)

If you prefer to set up manually or the script doesn't work:

### 1. Create ECR Repository

```bash
aws ecr create-repository \
  --repository-name ukp-app \
  --region us-east-1 \
  --image-scanning-configuration scanOnPush=true
```

### 2. Create App Runner Service

Use the AWS Console:
1. Go to AWS App Runner → Create service
2. Choose "Container registry" → ECR
3. Select your ECR repository
4. Configure:
   - Service name: `ukp-service`
   - CPU: 0.25 vCPU
   - Memory: 0.5 GB
   - Port: 8501
   - Health check: `/_stcore/health`

### 3. Set Up GitHub Actions

The workflow file (`.github/workflows/deploy-aws.yml`) is already configured. You just need:
- Add `AWS_ROLE_ARN` secret to GitHub
- Ensure OIDC provider is configured in AWS

## Configuration

### Environment Variables

You can customize these in `setup-aws.sh`:

```bash
export AWS_REGION=us-east-1          # Your preferred AWS region
export ECR_REPOSITORY=ukp-app        # ECR repository name
export APP_RUNNER_SERVICE=ukp-service # App Runner service name
```

### GitHub Actions Workflow

The workflow (`.github/workflows/deploy-aws.yml`) triggers on:
- Push to `main` branch
- Manual workflow dispatch

To modify, edit `.github/workflows/deploy-aws.yml`.

## Monitoring

### Check Deployment Status

```bash
# Get service ARN
SERVICE_ARN=$(aws apprunner list-services \
  --region us-east-1 \
  --query "ServiceSummaryList[?ServiceName=='ukp-service'].ServiceArn" \
  --output text)

# Check service status
aws apprunner describe-service \
  --service-arn $SERVICE_ARN \
  --region us-east-1
```

### View Logs

```bash
# Get service ARN (as above)
aws apprunner list-operations \
  --service-arn $SERVICE_ARN \
  --region us-east-1
```

### GitHub Actions Logs

View deployment logs in GitHub:
- Go to: https://github.com/ddotevs/UKP/actions
- Click on the latest workflow run

## Cost Estimation

AWS App Runner pricing (approximate):
- **Free tier**: First 5 GB-hours/month free
- **After free tier**: ~$0.007/vCPU-hour + $0.0008/GB-hour
- **Estimated monthly cost**: $5-15/month for light usage

ECR pricing:
- **Storage**: $0.10/GB/month (first 500MB free)
- **Data transfer**: Free within same region

## Troubleshooting

### Deployment Fails

1. **Check GitHub Actions logs**: Look for error messages
2. **Verify AWS credentials**: Ensure GitHub Actions role has correct permissions
3. **Check ECR access**: Ensure the App Runner role can pull from ECR
4. **Verify Dockerfile**: Test locally: `docker build -t test .`

### App Not Accessible

1. **Check service status**: Service must be in "Running" state
2. **Verify health check**: Ensure `/_stcore/health` endpoint responds
3. **Check security**: App Runner automatically provides HTTPS

### Build Failures

1. **Test Docker build locally**:
   ```bash
   docker build -t ukp-test .
   docker run -p 8501:8501 ukp-test
   ```

2. **Check requirements.txt**: Ensure all dependencies are listed
3. **Review Dockerfile**: Check for syntax errors

## Updating the App

Simply push changes to `main` branch:

```bash
git add .
git commit -m "Update app"
git push origin main
```

GitHub Actions will automatically rebuild and redeploy.

## Rollback

To rollback to a previous version:

1. **Via AWS Console**:
   - Go to App Runner → Your service → Deployments
   - Select previous deployment → Deploy

2. **Via CLI**:
   ```bash
   # List deployments
   aws apprunner list-operations --service-arn $SERVICE_ARN
   
   # Deploy specific image
   aws apprunner start-deployment --service-arn $SERVICE_ARN
   ```

## Security Best Practices

1. **IAM Roles**: Use least privilege principle
2. **Secrets**: Never commit AWS credentials
3. **Image Scanning**: ECR automatically scans images
4. **HTTPS**: App Runner provides HTTPS automatically
5. **Access Control**: Consider adding authentication to your app

## Next Steps

- Set up custom domain (optional)
- Configure CloudWatch alarms for monitoring
- Set up automated backups for database
- Add staging environment (separate App Runner service)

## Support

For issues:
1. Check GitHub Actions logs
2. Review AWS CloudWatch logs
3. Verify IAM permissions
4. Test Docker build locally



