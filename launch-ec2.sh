#!/bin/bash
# Script to launch EC2 instance for UKP Kickball app

set -e

AWS_REGION="${AWS_REGION:-us-east-1}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t2.micro}"
KEY_NAME="${KEY_NAME:-}"
SECURITY_GROUP_NAME="ukp-app-sg"

echo "🚀 Launching EC2 instance for UKP Kickball app..."
echo "   Region: $AWS_REGION"
echo "   Instance Type: $INSTANCE_TYPE"
echo ""

# Get the latest Ubuntu 22.04 LTS AMI ID
echo "📦 Finding latest Ubuntu 22.04 LTS AMI..."
AMI_ID=$(aws ec2 describe-images \
  --owners 099720109477 \
  --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" \
            "Name=state,Values=available" \
  --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
  --output text \
  --region $AWS_REGION)

if [ -z "$AMI_ID" ] || [ "$AMI_ID" == "None" ]; then
  echo "❌ Could not find Ubuntu 22.04 AMI"
  exit 1
fi

echo "   ✅ Found AMI: $AMI_ID"
echo ""

# Check if security group exists
echo "🔒 Checking security group..."
SG_EXISTS=$(aws ec2 describe-security-groups \
  --group-names $SECURITY_GROUP_NAME \
  --region $AWS_REGION \
  --query 'SecurityGroups[0].GroupId' \
  --output text 2>/dev/null || echo "")

if [ -z "$SG_EXISTS" ] || [ "$SG_EXISTS" == "None" ]; then
  echo "   Creating security group..."
  
  # Get default VPC
  VPC_ID=$(aws ec2 describe-vpcs \
    --filters "Name=isDefault,Values=true" \
    --query 'Vpcs[0].VpcId' \
    --output text \
    --region $AWS_REGION)
  
  if [ -z "$VPC_ID" ] || [ "$VPC_ID" == "None" ]; then
    echo "❌ Could not find default VPC"
    exit 1
  fi
  
  # Create security group
  SG_ID=$(aws ec2 create-security-group \
    --group-name $SECURITY_GROUP_NAME \
    --description "Security group for UKP Kickball app" \
    --vpc-id $VPC_ID \
    --region $AWS_REGION \
    --query 'GroupId' \
    --output text)
  
  echo "   ✅ Created security group: $SG_ID"
  
  # Get current public IP
  MY_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s https://api.ipify.org)
  echo "   Your public IP: $MY_IP"
  
  # Allow SSH from your IP
  echo "   Adding SSH rule (port 22) from your IP..."
  aws ec2 authorize-security-group-ingress \
    --group-id $SG_ID \
    --protocol tcp \
    --port 22 \
    --cidr $MY_IP/32 \
    --region $AWS_REGION 2>/dev/null || echo "   (SSH rule may already exist)"
  
  # Allow Streamlit port from anywhere
  echo "   Adding Streamlit rule (port 8501) from anywhere..."
  aws ec2 authorize-security-group-ingress \
    --group-id $SG_ID \
    --protocol tcp \
    --port 8501 \
    --cidr 0.0.0.0/0 \
    --region $AWS_REGION 2>/dev/null || echo "   (Streamlit rule may already exist)"
  
  echo "   ✅ Security group configured"
else
  SG_ID=$SG_EXISTS
  echo "   ✅ Using existing security group: $SG_ID"
fi

echo ""

# Check for key pair
if [ -z "$KEY_NAME" ]; then
  echo "🔑 Checking for existing key pairs..."
  EXISTING_KEYS=$(aws ec2 describe-key-pairs --region $AWS_REGION --query 'KeyPairs[*].KeyName' --output text 2>/dev/null || echo "")
  
  if [ -n "$EXISTING_KEYS" ] && [ "$EXISTING_KEYS" != "None" ]; then
    echo "   Available key pairs:"
    echo "$EXISTING_KEYS" | tr '\t' '\n' | sed 's/^/     - /'
    echo ""
    echo "   Using first available key pair..."
    KEY_NAME=$(echo "$EXISTING_KEYS" | awk '{print $1}')
    echo "   ✅ Using: $KEY_NAME"
  else
    KEY_NAME="ukp-key-$(date +%s)"
    echo "   No existing key pairs found."
    echo "   Creating new key pair: $KEY_NAME"
    aws ec2 create-key-pair \
      --key-name $KEY_NAME \
      --region $AWS_REGION \
      --query 'KeyMaterial' \
      --output text > ${KEY_NAME}.pem 2>/dev/null || {
      echo "   ⚠️  Could not create key pair automatically"
      echo "   Please create one manually or specify with: KEY_NAME=your-key-name ./launch-ec2.sh"
      exit 1
    }
    
    chmod 400 ${KEY_NAME}.pem
    echo "   ✅ Key pair created and saved to: ${KEY_NAME}.pem"
    echo "   ⚠️  IMPORTANT: Save this file securely! You'll need it to SSH into the instance."
  fi
fi

echo ""
echo "🚀 Launching EC2 instance..."
echo "   AMI: $AMI_ID"
echo "   Instance Type: $INSTANCE_TYPE"
echo "   Key Pair: $KEY_NAME"
echo "   Security Group: $SG_ID"
echo ""

# Launch instance
INSTANCE_OUTPUT=$(aws ec2 run-instances \
  --image-id $AMI_ID \
  --instance-type $INSTANCE_TYPE \
  --key-name $KEY_NAME \
  --security-group-ids $SG_ID \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=ukp-kickball-app}]" \
  --region $AWS_REGION \
  --query 'Instances[0].[InstanceId,State.Name]' \
  --output text)

INSTANCE_ID=$(echo $INSTANCE_OUTPUT | awk '{print $1}')
STATE=$(echo $INSTANCE_OUTPUT | awk '{print $2}')

if [ -z "$INSTANCE_ID" ] || [ "$INSTANCE_ID" == "None" ]; then
  echo "❌ Failed to launch instance"
  exit 1
fi

echo "   ✅ Instance launched: $INSTANCE_ID"
echo "   State: $STATE"
echo ""

# Wait for instance to be running
echo "⏳ Waiting for instance to be running..."
aws ec2 wait instance-running --instance-ids $INSTANCE_ID --region $AWS_REGION

# Get public IP
echo "📡 Getting public IP address..."
sleep 5  # Give it a moment to get an IP
PUBLIC_IP=$(aws ec2 describe-instances \
  --instance-ids $INSTANCE_ID \
  --region $AWS_REGION \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)

if [ -z "$PUBLIC_IP" ] || [ "$PUBLIC_IP" == "None" ]; then
  echo "   ⚠️  Instance is running but doesn't have a public IP yet"
  echo "   Wait a moment and check: aws ec2 describe-instances --instance-ids $INSTANCE_ID --region $AWS_REGION"
else
  echo "   ✅ Public IP: $PUBLIC_IP"
fi

echo ""
echo "✅ Instance is ready!"
echo ""
echo "📋 Next Steps:"
echo ""
echo "1. Connect to the instance:"
if [ -f "${KEY_NAME}.pem" ]; then
  echo "   ssh -i ${KEY_NAME}.pem ubuntu@$PUBLIC_IP"
else
  echo "   ssh -i <your-key-file>.pem ubuntu@$PUBLIC_IP"
fi
echo ""
echo "2. Once connected, deploy the app:"
echo "   git clone https://github.com/ddotevs/UKP.git"
echo "   cd UKP"
echo "   chmod +x deploy.sh"
echo "   ./deploy.sh"
echo ""
echo "3. Access your app at:"
echo "   http://$PUBLIC_IP:8501"
echo ""
echo "📝 Instance Details:"
echo "   Instance ID: $INSTANCE_ID"
echo "   Public IP: $PUBLIC_IP"
echo "   Region: $AWS_REGION"
echo "   Security Group: $SG_ID"
echo ""
echo "💡 Useful commands:"
echo "   Check status: aws ec2 describe-instances --instance-ids $INSTANCE_ID --region $AWS_REGION"
echo "   Stop instance: aws ec2 stop-instances --instance-ids $INSTANCE_ID --region $AWS_REGION"
echo "   Terminate instance: aws ec2 terminate-instances --instance-ids $INSTANCE_ID --region $AWS_REGION"

