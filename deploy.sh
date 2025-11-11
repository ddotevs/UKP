#!/bin/bash
# Deployment script for AWS EC2

set -e

echo "🚀 Starting UKP deployment..."

# Update system
echo "📦 Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Install Python and pip if not already installed
echo "🐍 Installing Python and dependencies..."
sudo apt-get install -y python3 python3-pip python3-venv

# Install Docker (optional, for Docker deployment)
if command -v docker &> /dev/null; then
    echo "🐳 Docker already installed"
else
    echo "🐳 Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
fi

# Create application directory
APP_DIR="/opt/ukp"
echo "📁 Creating application directory at $APP_DIR..."
sudo mkdir -p $APP_DIR
sudo chown $USER:$USER $APP_DIR

# Copy application files (assuming you're running this from the project directory)
echo "📋 Copying application files..."
cp -r . $APP_DIR/
cd $APP_DIR

# Create virtual environment
echo "🔧 Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create systemd service file
echo "⚙️  Creating systemd service..."
sudo tee /etc/systemd/system/ukp.service > /dev/null <<EOF
[Unit]
Description=UKP Kickball Roster Streamlit App
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
ExecStart=$APP_DIR/venv/bin/streamlit run $APP_DIR/app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and start service
echo "🔄 Starting service..."
sudo systemctl daemon-reload
sudo systemctl enable ukp.service
sudo systemctl start ukp.service

# Check service status
echo "✅ Checking service status..."
sudo systemctl status ukp.service --no-pager

echo "🎉 Deployment complete!"
echo "📝 Next steps:"
echo "   1. Configure security group to allow port 8501"
echo "   2. Access app at http://$(curl -s ifconfig.me):8501"
echo "   3. Check logs: sudo journalctl -u ukp.service -f"

