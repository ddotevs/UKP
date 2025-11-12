#!/bin/bash
# AWS App Runner Setup Script
# This script sets up the initial AWS infrastructure for automated deployment

set -e

# Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPOSITORY="${ECR_REPOSITORY:-ukp-app}"
APP_RUNNER_SERVICE="${APP_RUNNER_SERVICE:-ukp-service}"
GITHUB_REPO="${GITHUB_REPO:-ddotevs/UKP}"

echo "🚀 Setting up AWS infrastructure for UKP deployment..."
echo "Region: $AWS_REGION"
echo "ECR Repository: $ECR_REPOSITORY"
echo "App Runner Service: $APP_RUNNER_SERVICE"
echo ""

# Check AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not found. Please install it first:"
    echo "   https://aws.amazon.com/cli/"
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    echo "❌ AWS credentials not configured. Please run:"
    echo "   aws configure"
    exit 1
fi

echo "✅ AWS CLI configured"

# Step 1: Create ECR repository
echo ""
echo "📦 Creating ECR repository..."
if aws ecr describe-repositories --repository-names "$ECR_REPOSITORY" --region "$AWS_REGION" &> /dev/null; then
    echo "   Repository already exists"
else
    aws ecr create-repository \
        --repository-name "$ECR_REPOSITORY" \
        --region "$AWS_REGION" \
        --image-scanning-configuration scanOnPush=true \
        --encryption-configuration encryptionType=AES256
    echo "   ✅ Repository created"
fi

ECR_URI=$(aws ecr describe-repositories --repository-names "$ECR_REPOSITORY" --region "$AWS_REGION" --query "repositories[0].repositoryUri" --output text)
echo "   ECR URI: $ECR_URI"

# Step 2: Create IAM role for App Runner
echo ""
echo "🔐 Creating IAM role for App Runner..."
ROLE_NAME="AppRunnerECRAccessRole"

# Check if role exists
if aws iam get-role --role-name "$ROLE_NAME" &> /dev/null; then
    echo "   Role already exists"
    ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query "Role.Arn" --output text)
else
    # Create trust policy
    cat > /tmp/apprunner-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "build.apprunner.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

    # Create role
    aws iam create-role \
        --role-name "$ROLE_NAME" \
        --assume-role-policy-document file:///tmp/apprunner-trust-policy.json

    # Attach ECR access policy
    aws iam attach-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess

    ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query "Role.Arn" --output text)
    echo "   ✅ Role created: $ROLE_ARN"
fi

# Step 3: Create App Runner service
echo ""
echo "🏃 Creating App Runner service..."

# Check if service already exists
if aws apprunner list-services --region "$AWS_REGION" --query "ServiceSummaryList[?ServiceName=='$APP_RUNNER_SERVICE']" --output text | grep -q "$APP_RUNNER_SERVICE"; then
    echo "   Service already exists"
    SERVICE_ARN=$(aws apprunner list-services --region "$AWS_REGION" --query "ServiceSummaryList[?ServiceName=='$APP_RUNNER_SERVICE'].ServiceArn" --output text)
    SERVICE_URL=$(aws apprunner describe-service --service-arn "$SERVICE_ARN" --region "$AWS_REGION" --query "Service.ServiceUrl" --output text)
    echo "   Service URL: $SERVICE_URL"
else
    # Create service configuration
    cat > /tmp/apprunner-config.json <<EOF
{
  "CodeRepository": {
    "RepositoryUrl": "https://github.com/$GITHUB_REPO",
    "SourceCodeVersion": {
      "Type": "BRANCH",
      "Value": "main"
    },
    "CodeConfiguration": {
      "ConfigurationSource": "API",
      "CodeConfigurationValues": {
        "Runtime": "DOCKER",
        "BuildCommand": "docker build -t ukp-app .",
        "StartCommand": "streamlit run app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true",
        "RuntimeEnvironmentVariables": {
          "STREAMLIT_SERVER_PORT": "8501",
          "STREAMLIT_SERVER_ADDRESS": "0.0.0.0",
          "STREAMLIT_SERVER_HEADLESS": "true"
        }
      }
    }
  },
  "AutoDeploymentsEnabled": true,
  "InstanceConfiguration": {
    "Cpu": "0.25 vCPU",
    "Memory": "0.5 GB"
  },
  "HealthCheckConfiguration": {
    "Protocol": "HTTP",
    "Path": "/_stcore/health",
    "Interval": 10,
    "Timeout": 5,
    "HealthyThreshold": 1,
    "UnhealthyThreshold": 5
  }
}
EOF

    # Alternative: Use ECR instead of GitHub (for automated deployments)
    cat > /tmp/apprunner-ecr-config.json <<EOF
{
  "ImageRepository": {
    "ImageIdentifier": "$ECR_URI:latest",
    "ImageConfiguration": {
      "Port": "8501",
      "RuntimeEnvironmentVariables": {
        "STREAMLIT_SERVER_PORT": "8501",
        "STREAMLIT_SERVER_ADDRESS": "0.0.0.0",
        "STREAMLIT_SERVER_HEADLESS": "true"
      }
    },
    "ImageRepositoryType": "ECR"
  },
  "AutoDeploymentsEnabled": false,
  "AuthenticationConfiguration": {
    "AccessRoleArn": "$ROLE_ARN"
  }
}
EOF

    echo "   Creating service with ECR source..."
    SERVICE_OUTPUT=$(aws apprunner create-service \
        --service-name "$APP_RUNNER_SERVICE" \
        --source-configuration file:///tmp/apprunner-ecr-config.json \
        --instance-configuration "Cpu=0.25 vCPU,Memory=0.5 GB" \
        --health-check-configuration Protocol=HTTP,Path=/_stcore/health,Interval=10,Timeout=5,HealthyThreshold=1,UnhealthyThreshold=5 \
        --region "$AWS_REGION")

    SERVICE_ARN=$(echo "$SERVICE_OUTPUT" | jq -r '.Service.ServiceArn')
    echo "   ✅ Service created: $SERVICE_ARN"
    echo ""
    echo "   ⏳ Service is being created. This may take a few minutes..."
    echo "   Check status: aws apprunner describe-service --service-arn $SERVICE_ARN --region $AWS_REGION"
fi

# Step 4: Create IAM role for GitHub Actions (OIDC)
echo ""
echo "🔐 Setting up GitHub Actions OIDC role..."

GITHUB_ROLE_NAME="GitHubActionsAppRunnerRole"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Check if role exists
if aws iam get-role --role-name "$GITHUB_ROLE_NAME" &> /dev/null; then
    echo "   Role already exists"
    GITHUB_ROLE_ARN=$(aws iam get-role --role-name "$GITHUB_ROLE_NAME" --query "Role.Arn" --output text)
else
    # Create trust policy for GitHub OIDC
    cat > /tmp/github-oidc-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::$ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:$GITHUB_REPO:*"
        }
      }
    }
  ]
}
EOF

    # Create role
    aws iam create-role \
        --role-name "$GITHUB_ROLE_NAME" \
        --assume-role-policy-document file:///tmp/github-oidc-trust-policy.json

    # Create and attach policy for ECR and App Runner access
    cat > /tmp/github-actions-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "apprunner:ListServices",
        "apprunner:DescribeService",
        "apprunner:StartDeployment"
      ],
      "Resource": "*"
    }
  ]
}
EOF

    aws iam put-role-policy \
        --role-name "$GITHUB_ROLE_NAME" \
        --policy-name GitHubActionsDeployPolicy \
        --policy-document file:///tmp/github-actions-policy.json

    GITHUB_ROLE_ARN=$(aws iam get-role --role-name "$GITHUB_ROLE_NAME" --query "Role.Arn" --output text)
    echo "   ✅ Role created: $GITHUB_ROLE_ARN"
fi

# Cleanup temp files
rm -f /tmp/apprunner-*.json /tmp/github-*.json

echo ""
echo "✅ Setup complete!"
echo ""
echo "📋 Next steps:"
echo ""
echo "1. Add GitHub secrets:"
echo "   Go to: https://github.com/$GITHUB_REPO/settings/secrets/actions"
echo "   Add secrets:"
echo "   - AWS_ROLE_ARN = $GITHUB_ROLE_ARN"
echo "   - AWS_APP_RUNNER_ROLE_ARN = $ROLE_ARN"
echo ""
echo "2. Configure GitHub OIDC provider (if not already done):"
echo "   https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services"
echo ""
echo "3. Push to main branch to trigger deployment:"
echo "   git push origin main"
echo ""
echo "4. Check service status:"
if [ -n "$SERVICE_ARN" ]; then
    echo "   aws apprunner describe-service --service-arn $SERVICE_ARN --region $AWS_REGION"
fi

