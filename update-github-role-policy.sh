#!/bin/bash
# Quick script to update the GitHub Actions role policy with missing ECR permissions

set -e

GITHUB_ROLE_NAME="GitHubActionsAppRunnerRole"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "🔧 Updating GitHub Actions role policy..."
echo "   Role: $GITHUB_ROLE_NAME"

# Create updated policy with all required ECR permissions
cat > /tmp/github-actions-policy-updated.json <<EOF
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
        "ecr:CompleteLayerUpload",
        "ecr:DescribeImages",
        "ecr:DescribeRepositories"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "apprunner:ListServices",
        "apprunner:DescribeService",
        "apprunner:StartDeployment",
        "apprunner:CreateService",
        "apprunner:UpdateService"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::$ACCOUNT_ID:role/AppRunnerECRAccessRole",
      "Condition": {
        "StringEquals": {
          "iam:PassedToService": "apprunner.amazonaws.com"
        }
      }
    }
  ]
}
EOF

# Update the role policy
aws iam put-role-policy \
    --role-name "$GITHUB_ROLE_NAME" \
    --policy-name GitHubActionsDeployPolicy \
    --policy-document file:///tmp/github-actions-policy-updated.json

echo "✅ Policy updated successfully!"
echo ""
echo "The role now has the following permissions:"
echo "  - ECR: DescribeImages, DescribeRepositories, and all push/pull permissions"
echo "  - App Runner: CreateService, UpdateService, and all management permissions"
echo "  - IAM: PassRole (for AppRunnerECRAccessRole to App Runner service)"
echo ""
echo "You can now retry the GitHub Actions workflow."

rm -f /tmp/github-actions-policy-updated.json

