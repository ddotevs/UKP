# EC2 Quick Start Guide

## Step 1: Launch EC2 Instance

### Option A: Using AWS Console (Easiest)

1. Go to [AWS EC2 Console](https://console.aws.amazon.com/ec2/)
2. Click **Launch Instance**
3. Configure:
   - **Name**: `ukp-kickball-app`
   - **AMI**: Ubuntu Server 22.04 LTS (free tier eligible)
   - **Instance type**: `t2.micro` (free tier) or `t3.small` (recommended)
   - **Key pair**: Create new or select existing
   - **Network settings**: 
     - Create security group
     - Allow SSH (port 22) from your IP
     - Allow Custom TCP (port 8501) from anywhere (0.0.0.0/0)
   - **Storage**: 8 GB (free tier) is sufficient
4. Click **Launch Instance**

### Option B: Using AWS CLI

```bash
# Create security group
aws ec2 create-security-group \
  --group-name ukp-app-sg \
  --description "Security group for UKP Kickball app" \
  --region us-east-1

# Get your public IP
MY_IP=$(curl -s ifconfig.me)

# Allow SSH from your IP
aws ec2 authorize-security-group-ingress \
  --group-name ukp-app-sg \
  --protocol tcp \
  --port 22 \
  --cidr $MY_IP/32 \
  --region us-east-1

# Allow Streamlit port from anywhere
aws ec2 authorize-security-group-ingress \
  --group-name ukp-app-sg \
  --protocol tcp \
  --port 8501 \
  --cidr 0.0.0.0/0 \
  --region us-east-1

# Launch instance (replace with your key pair name)
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t2.micro \
  --key-name your-key-name \
  --security-groups ukp-app-sg \
  --region us-east-1
```

## Step 2: Connect to Instance

```bash
# Set permissions on key file
chmod 400 your-key.pem

# Connect (replace with your instance's public IP)
ssh -i your-key.pem ubuntu@<EC2-PUBLIC-IP>
```

## Step 3: Deploy the App

Once connected to the EC2 instance:

```bash
# Clone the repository
git clone https://github.com/ddotevs/UKP.git
cd UKP

# Make deploy script executable
chmod +x deploy.sh

# Run deployment (this will take a few minutes)
./deploy.sh
```

The script will:
- Install Python and dependencies
- Set up a virtual environment
- Install required packages
- Create a systemd service
- Start the app automatically

## Step 4: Access Your App

After deployment completes, access your app at:
```
http://<EC2-PUBLIC-IP>:8501
```

## Useful Commands

### Check if app is running
```bash
sudo systemctl status ukp.service
```

### View logs
```bash
sudo journalctl -u ukp.service -f
```

### Restart the app
```bash
sudo systemctl restart ukp.service
```

### Stop the app
```bash
sudo systemctl stop ukp.service
```

### Get your EC2 public IP
```bash
curl -s ifconfig.me
```

## Troubleshooting

### App not accessible
- Check security group allows port 8501
- Verify service is running: `sudo systemctl status ukp.service`
- Check logs: `sudo journalctl -u ukp.service -n 50`

### Port already in use
- Check what's using port 8501: `sudo lsof -i :8501`
- Kill the process if needed

### Permission errors
- Ensure files are owned by ubuntu user: `sudo chown -R ubuntu:ubuntu /opt/ukp`

## Cost

- **t2.micro**: Free tier eligible (750 hours/month for 12 months)
- **t3.small**: ~$0.0208/hour (~$15/month if running 24/7)

## Next Steps (Optional)

1. **Set up a domain**: Point your domain to the EC2 IP
2. **Add SSL/HTTPS**: Use Let's Encrypt with Nginx reverse proxy
3. **Set up auto-updates**: Configure GitHub Actions to deploy to EC2
4. **Add monitoring**: Set up CloudWatch alarms

