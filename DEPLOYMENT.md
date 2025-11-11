# AWS EC2 Deployment Guide for UKP

This guide will walk you through deploying the UKP Kickball Roster app to AWS EC2.

## Prerequisites

- AWS account
- EC2 instance (Ubuntu 22.04 LTS recommended)
- SSH access to your EC2 instance
- Domain name (optional, for custom domain)

## Option 1: Direct Python Deployment (Recommended for simplicity)

### Step 1: Launch EC2 Instance

1. Go to AWS Console → EC2 → Launch Instance
2. Choose **Ubuntu Server 22.04 LTS** (or latest)
3. Select instance type: **t2.micro** (free tier) or **t3.small** (recommended)
4. Configure security group:
   - SSH (port 22) from your IP
   - Custom TCP (port 8501) from anywhere (0.0.0.0/0) or your IP only
5. Launch and download key pair (.pem file)

### Step 2: Connect to EC2 Instance

```bash
# Set permissions on key file
chmod 400 your-key.pem

# Connect to instance
ssh -i your-key.pem ubuntu@<your-ec2-public-ip>
```

### Step 3: Deploy Application

#### Option A: Using the deployment script

```bash
# Clone your repository (or upload files)
git clone https://github.com/ddotevs/UKP.git
cd UKP

# Make deploy script executable
chmod +x deploy.sh

# Run deployment script
./deploy.sh
```

#### Option B: Manual deployment

```bash
# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install Python and pip
sudo apt-get install -y python3 python3-pip python3-venv

# Create application directory
sudo mkdir -p /opt/ukp
sudo chown $USER:$USER /opt/ukp
cd /opt/ukp

# Upload your application files (use scp, git clone, or other method)
# For example, using scp from your local machine:
# scp -i your-key.pem -r /path/to/UKP/* ubuntu@<ec2-ip>:/opt/ukp/

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create systemd service
sudo nano /etc/systemd/system/ukp.service
```

Paste this service configuration:

```ini
[Unit]
Description=UKP Kickball Roster Streamlit App
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/ukp
Environment="PATH=/opt/ukp/venv/bin"
ExecStart=/opt/ukp/venv/bin/streamlit run /opt/ukp/app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:

```bash
# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable ukp.service
sudo systemctl start ukp.service

# Check status
sudo systemctl status ukp.service
```

### Step 4: Configure Firewall

```bash
# Allow port 8501 through firewall
sudo ufw allow 8501/tcp
sudo ufw enable
```

### Step 5: Access Your App

Open your browser and navigate to:
```
http://<your-ec2-public-ip>:8501
```

## Option 2: Docker Deployment (Recommended for production)

### Step 1: Install Docker on EC2

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### Step 2: Deploy with Docker

```bash
# Clone repository
git clone https://github.com/ddotevs/UKP.git
cd UKP

# Build and run with Docker Compose
docker-compose up -d --build

# Check status
docker-compose ps
docker-compose logs -f
```

### Step 3: Create systemd service for Docker (optional)

```bash
sudo nano /etc/systemd/system/ukp-docker.service
```

```ini
[Unit]
Description=UKP Docker Container
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/ukp
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
Restart=always

[Install]
WantedBy=multi-user.target
```

## Option 3: Using Nginx Reverse Proxy (Recommended for production)

### Step 1: Install Nginx

```bash
sudo apt-get install -y nginx
```

### Step 2: Configure Nginx

```bash
sudo nano /etc/nginx/sites-available/ukp
```

```nginx
server {
    listen 80;
    server_name your-domain.com;  # or your EC2 IP

    location / {
        proxy_pass http://127.0.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/ukp /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Step 3: Set up SSL with Let's Encrypt (optional)

```bash
# Install Certbot
sudo apt-get install -y certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal is set up automatically
```

## Security Considerations

### 1. Update Security Group

- Only allow port 8501 from trusted IPs if possible
- Use SSH key pairs, not passwords
- Consider using a VPN or bastion host

### 2. Database Backup

```bash
# Create backup script
sudo nano /opt/ukp/backup.sh
```

```bash
#!/bin/bash
BACKUP_DIR="/opt/ukp/backups"
mkdir -p $BACKUP_DIR
cp /opt/ukp/kickball_roster.db $BACKUP_DIR/kickball_roster_$(date +%Y%m%d_%H%M%S).db
# Keep only last 7 days
find $BACKUP_DIR -name "*.db" -mtime +7 -delete
```

```bash
# Add to crontab (daily at 2 AM)
crontab -e
# Add: 0 2 * * * /opt/ukp/backup.sh
```

### 3. Firewall Rules

```bash
# Only allow necessary ports
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 8501/tcp
sudo ufw enable
```

## Monitoring and Maintenance

### View Logs

```bash
# Systemd service logs
sudo journalctl -u ukp.service -f

# Docker logs
docker-compose logs -f
```

### Restart Service

```bash
# Systemd
sudo systemctl restart ukp.service

# Docker
docker-compose restart
```

### Update Application

```bash
cd /opt/ukp
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart ukp.service
```

## Troubleshooting

### App not accessible

1. Check security group allows port 8501
2. Check firewall: `sudo ufw status`
3. Check service status: `sudo systemctl status ukp.service`
4. Check logs: `sudo journalctl -u ukp.service -n 50`

### Database issues

- Database file is at `/opt/ukp/kickball_roster.db`
- Ensure proper permissions: `sudo chown ubuntu:ubuntu /opt/ukp/kickball_roster.db`

### Port already in use

```bash
# Find process using port 8501
sudo lsof -i :8501
# Kill process if needed
sudo kill -9 <PID>
```

## Cost Optimization

- Use t2.micro for free tier (limited performance)
- Use t3.small for better performance (~$15/month)
- Consider Reserved Instances for long-term use
- Use CloudWatch to monitor usage
- Set up auto-shutdown during off-hours if needed

## Next Steps

1. Set up domain name (optional)
2. Configure SSL certificate
3. Set up automated backups
4. Configure CloudWatch monitoring
5. Set up email alerts for errors

