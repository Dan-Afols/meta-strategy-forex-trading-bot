#!/bin/bash
# ============================================================
# Forex Trading System — VPS Deployment Script
# Run as root or with sudo on Ubuntu 20.04+
# ============================================================
set -euo pipefail

APP_DIR="/opt/trade_fx"
APP_USER="trader"
SERVICE_NAME="forex-trading"

echo "=========================================="
echo " Forex Trading System - VPS Setup"
echo "=========================================="

# 1. System packages
echo "[1/7] Installing system packages..."
apt-get update -qq
apt-get install -y -qq python3.11 python3.11-venv python3-pip git postgresql

# 2. Create app user
echo "[2/7] Creating application user..."
if ! id -u "$APP_USER" &>/dev/null; then
    useradd -m -s /bin/bash "$APP_USER"
fi

# 3. Deploy application
echo "[3/7] Setting up application directory..."
mkdir -p "$APP_DIR"
cp -r . "$APP_DIR/"
cd "$APP_DIR"

# 4. Python virtual environment
echo "[4/7] Creating Python virtual environment..."
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 5. Environment file
echo "[5/7] Configuring environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo ">>> IMPORTANT: Edit /opt/trade_fx/.env with your credentials <<<"
fi

# 6. Create directories and set permissions
echo "[6/7] Setting up directories and permissions..."
mkdir -p data/charts logs ml_models/saved
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# 7. Install systemd service
echo "[7/7] Installing systemd service..."
cp deploy/forex-trading.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo ""
echo "=========================================="
echo " Setup Complete!"
echo "=========================================="
echo ""
echo " Next steps:"
echo "  1. Edit /opt/trade_fx/.env with your credentials"
echo "  2. Start the service: sudo systemctl start $SERVICE_NAME"
echo "  3. Check status: sudo systemctl status $SERVICE_NAME"
echo "  4. View logs: sudo journalctl -u $SERVICE_NAME -f"
echo "  5. Dashboard: http://your-vps-ip:8000"
echo ""
