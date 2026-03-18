#!/bin/bash
# ============================================================
# Install Node.js and build the dashboard frontend
# Run as root: sudo bash deploy/build_dashboard.sh
# ============================================================
set -euo pipefail

APP_DIR="/opt/trade_fx"
APP_USER="trader"

echo "Installing Node.js 18 LTS..."

# Install Node.js 18 via NodeSource
curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
apt-get install -y -qq nodejs

echo "Node.js version: $(node --version)"
echo "npm version: $(npm --version)"

echo "Building dashboard frontend..."
cd "$APP_DIR/dashboard/frontend"

# Install dependencies and build
sudo -u "$APP_USER" npm install
sudo -u "$APP_USER" npm run build

echo ""
echo "Dashboard built successfully!"
echo "Start it with: sudo systemctl start forex-dashboard"
echo ""
