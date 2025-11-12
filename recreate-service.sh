#!/bin/bash
# Script to recreate App Runner service after image is pushed to ECR

set -e

AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPOSITORY="${ECR_REPOSITORY:-ukp-app}"
APP_RUNNER_SERVICE="${APP_RUNNER_SERVICE:-ukp-service}"

echo "🔍 Checking for images in ECR..."

# Check if image exists
IMAGE_EXISTS=$(aws ecr describe-images --repository-name "$ECR_REPOSITORY" --region "$AWS_REGION" --query 'imageDetails[0].imageTags[0]' --output text 2>/dev/null || echo "")

if [ -z "$IMAGE_EXISTS" ] || [ "$IMAGE_EXISTS" == "None" ]; then
    echo "❌ No images found in ECR repository: $ECR_REPOSITORY"
    echo "   Please wait for GitHub Actions to push the image, or push manually."
    exit 1
fi

echo "✅ Found image: $IMAGE_EXISTS"

# Get ECR URI
ECR_URI=$(aws ecr describe-repositories --repository-names "$ECR_REPOSITORY" --region "$AWS_REGION" --query "repositories[0].repositoryUri" --output text)
ROLE_ARN=$(aws iam get-role --role-name "AppRunnerECRAccessRole" --query "Role.Arn" --output text)

echo "📦 ECR URI: $ECR_URI"
echo "🔐 Using role: $ROLE_ARN"

# Check if service already exists
EXISTING_SERVICE=$(aws apprunner list-services --region "$AWS_REGION" --query "ServiceSummaryList[?ServiceName=='$APP_RUNNER_SERVICE'].ServiceArn" --output text)

if [ -n "$EXISTING_SERVICE" ]; then
    echo "⚠️  Service already exists: $EXISTING_SERVICE"
    echo "   Use 'aws apprunner delete-service' to remove it first if needed."
    exit 1
fi

# Create service configuration
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

echo "🏃 Creating App Runner service..."
SERVICE_OUTPUT=$(aws apprunner create-service \
    --service-name "$APP_RUNNER_SERVICE" \
    --source-configuration file:///tmp/apprunner-ecr-config.json \
    --instance-configuration "Cpu=0.25 vCPU,Memory=0.5 GB" \
    --health-check-configuration Protocol=HTTP,Path=/_stcore/health,Interval=10,Timeout=5,HealthyThreshold=1,UnhealthyThreshold=5 \
    --region "$AWS_REGION")

SERVICE_ARN=$(echo "$SERVICE_OUTPUT" | jq -r '.Service.ServiceArn')
SERVICE_URL=$(echo "$SERVICE_OUTPUT" | jq -r '.Service.ServiceUrl')

echo "✅ Service created!"
echo "   ARN: $SERVICE_ARN"
echo "   URL: https://$SERVICE_URL"
echo ""
echo "⏳ Service is being created. This may take a few minutes..."
echo "   Check status: aws apprunner describe-service --service-arn $SERVICE_ARN --region $AWS_REGION"

rm -f /tmp/apprunner-ecr-config.json

