#!/bin/bash
# ============================================================
# Forex Trading Bot — Oracle Cloud Linux Deployment Script
# ============================================================
# This script sets up a Ubuntu x86 VM on Oracle Cloud to run:
#   1. MetaTrader 5 via Wine (headless, no GUI needed)
#   2. The Python trading bot under Wine's Python
#   3. Nginx reverse proxy (dashboard + API on port 80)
#   4. Systemd services for auto-start on reboot
#
# Run as root:  sudo bash deploy/oracle_setup.sh
# ============================================================
set -euo pipefail

APP_DIR="/opt/trade_fx"
APP_USER="trader"
WINE_PYTHON_VERSION="3.11.9"
LOG_FILE="/var/log/trade_fx_setup.log"

log() { echo "[$(date '+%H:%M:%S')] $1" | tee -a "$LOG_FILE"; }

echo "=========================================="
echo " Forex Trading Bot - Oracle Cloud Setup"
echo "=========================================="
echo ""
log "Starting setup..."

# ── 1. System packages ──────────────────────────────────────

log "[1/10] Installing system packages..."
dpkg --add-architecture i386
apt-get update -qq
apt-get install -y -qq \
    software-properties-common \
    wget curl git unzip \
    xvfb x11-utils \
    cabextract \
    nginx \
    supervisor \
    certbot python3-certbot-nginx \
    build-essential \
    2>&1 | tail -5

# ── 2. Install Wine ─────────────────────────────────────────

log "[2/10] Installing Wine..."
mkdir -pm755 /etc/apt/keyrings
wget -qO- https://dl.winehq.org/wine-builds/winehq.key | gpg --dearmor -o /etc/apt/keyrings/winehq-archive.key 2>/dev/null || true

# Detect Ubuntu version
UBUNTU_VERSION=$(lsb_release -sc)
wget -qO /etc/apt/sources.list.d/winehq-${UBUNTU_VERSION}.sources \
    "https://dl.winehq.org/wine-builds/ubuntu/dists/${UBUNTU_VERSION}/winehq-${UBUNTU_VERSION}.sources" 2>/dev/null || {
    log "WARN: Could not add Wine repo for ${UBUNTU_VERSION}, trying manual install..."
    apt-get install -y -qq wine wine64 wine32
}

apt-get update -qq
apt-get install -y -qq --install-recommends winehq-stable 2>/dev/null || \
    apt-get install -y -qq wine wine64 wine32 || true

log "Wine version: $(wine --version 2>/dev/null || echo 'not found')"

# ── 3. Create app user ──────────────────────────────────────

log "[3/10] Creating application user..."
if ! id -u "$APP_USER" &>/dev/null; then
    useradd -m -s /bin/bash "$APP_USER"
    log "User '$APP_USER' created"
else
    log "User '$APP_USER' already exists"
fi

# ── 4. Deploy application files ─────────────────────────────

log "[4/10] Deploying application to $APP_DIR..."
mkdir -p "$APP_DIR"
# If running from the repo directory:
if [ -f "main.py" ]; then
    rsync -a --exclude='.venv' --exclude='node_modules' --exclude='.next' \
        --exclude='__pycache__' --exclude='.git' \
        . "$APP_DIR/"
elif [ -d "/tmp/trade_fx" ]; then
    rsync -a --exclude='.venv' --exclude='node_modules' --exclude='.next' \
        --exclude='__pycache__' --exclude='.git' \
        /tmp/trade_fx/ "$APP_DIR/"
else
    log "ERROR: Cannot find source code. Copy it to /tmp/trade_fx first."
    exit 1
fi

mkdir -p "$APP_DIR"/{data/charts,logs,ml_models/saved}

# ── 5. Set up Wine + Python for the trader user ─────────────

log "[5/10] Setting up Wine environment for $APP_USER..."

# Initialize Wine prefix
sudo -u "$APP_USER" bash -c '
    export WINEPREFIX="$HOME/.wine"
    export WINEDEBUG=-all
    export DISPLAY=:99

    # Start virtual display for Wine init
    Xvfb :99 -screen 0 1024x768x16 &
    XVFB_PID=$!
    sleep 2

    # Initialize Wine (accept defaults)
    wineboot --init 2>/dev/null
    sleep 5

    kill $XVFB_PID 2>/dev/null || true
'

# Download and install Python for Windows under Wine
log "Installing Windows Python ${WINE_PYTHON_VERSION} under Wine..."
PYTHON_URL="https://www.python.org/ftp/python/${WINE_PYTHON_VERSION}/python-${WINE_PYTHON_VERSION}-amd64.exe"
PYTHON_INSTALLER="/tmp/python-installer.exe"
wget -q -O "$PYTHON_INSTALLER" "$PYTHON_URL"

sudo -u "$APP_USER" bash -c "
    export WINEPREFIX=\"\$HOME/.wine\"
    export WINEDEBUG=-all
    export DISPLAY=:99

    Xvfb :99 -screen 0 1024x768x16 &
    XVFB_PID=\$!
    sleep 2

    # Silent install Python
    wine \"$PYTHON_INSTALLER\" /quiet InstallAllUsers=0 \
        PrependPath=1 Include_test=0 Include_launcher=0 2>/dev/null
    sleep 10

    kill \$XVFB_PID 2>/dev/null || true
"

# Verify Python
WINE_PYTHON_PATH="/home/${APP_USER}/.wine/drive_c/users/${APP_USER}/AppData/Local/Programs/Python/Python311/python.exe"
if sudo -u "$APP_USER" bash -c "WINEPREFIX=\$HOME/.wine WINEDEBUG=-all wine '$WINE_PYTHON_PATH' --version 2>/dev/null"; then
    log "Wine Python installed successfully"
else
    log "WARN: Python path may differ, checking alternatives..."
    find /home/${APP_USER}/.wine -name "python.exe" 2>/dev/null | head -5
fi

# ── 6. Install Python packages under Wine ───────────────────

log "[6/10] Installing Python packages under Wine..."
sudo -u "$APP_USER" bash -c "
    export WINEPREFIX=\"\$HOME/.wine\"
    export WINEDEBUG=-all
    export DISPLAY=:99

    Xvfb :99 -screen 0 1024x768x16 &
    XVFB_PID=\$!
    sleep 2

    # Upgrade pip
    wine '$WINE_PYTHON_PATH' -m pip install --upgrade pip 2>/dev/null

    # Install requirements (skip torch for now to save space, install CPU-only version)
    wine '$WINE_PYTHON_PATH' -m pip install --no-cache-dir \
        -r '$APP_DIR/requirements.txt' 2>/dev/null || {
        echo 'Full install failed, trying without torch...'
        grep -v '^torch' '$APP_DIR/requirements.txt' > /tmp/req_no_torch.txt
        wine '$WINE_PYTHON_PATH' -m pip install --no-cache-dir \
            -r /tmp/req_no_torch.txt 2>/dev/null
        # Install CPU-only torch (much smaller)
        wine '$WINE_PYTHON_PATH' -m pip install --no-cache-dir \
            torch --index-url https://download.pytorch.org/whl/cpu 2>/dev/null || true
    }

    # Install MetaTrader5 (Windows-only package, works under Wine)
    wine '$WINE_PYTHON_PATH' -m pip install MetaTrader5 2>/dev/null

    kill \$XVFB_PID 2>/dev/null || true
"

# ── 7. Install MetaTrader 5 terminal under Wine ─────────────

log "[7/10] Installing MetaTrader 5 terminal..."
MT5_INSTALLER="/tmp/mt5setup.exe"
wget -q -O "$MT5_INSTALLER" "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe"

sudo -u "$APP_USER" bash -c "
    export WINEPREFIX=\"\$HOME/.wine\"
    export WINEDEBUG=-all
    export DISPLAY=:99

    Xvfb :99 -screen 0 1024x768x16 &
    XVFB_PID=\$!
    sleep 2

    wine '$MT5_INSTALLER' /auto 2>/dev/null
    sleep 30

    # MT5 installs to Program Files
    MT5_DIR=\"\$HOME/.wine/drive_c/Program Files/MetaTrader 5\"
    if [ -f \"\$MT5_DIR/terminal64.exe\" ]; then
        echo 'MT5 installed successfully at: '\"\$MT5_DIR\"
    else
        echo 'WARN: MT5 may have installed to a different location'
        find \$HOME/.wine -name 'terminal64.exe' 2>/dev/null | head -3
    fi

    kill \$XVFB_PID 2>/dev/null || true
"

# ── 8. Configure .env ───────────────────────────────────────

log "[8/10] Configuring environment..."
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    # Generate a random secret key
    SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || openssl rand -base64 32)
    sed -i "s|SECRET_KEY=CHANGE_ME_TO_A_RANDOM_SECRET|SECRET_KEY=$SECRET|" "$APP_DIR/.env"
    # Update MT5 path for Wine
    sed -i "s|MT5_PATH=.*|MT5_PATH=C:/Program Files/MetaTrader 5/terminal64.exe|" "$APP_DIR/.env"
    log ">>> IMPORTANT: Edit $APP_DIR/.env with your MT5 and Telegram credentials! <<<"
else
    log ".env already exists, skipping"
fi

# Set ownership
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chown -R "$APP_USER:$APP_USER" "/home/$APP_USER/.wine"

# ── 9. Install systemd services ─────────────────────────────

log "[9/10] Installing systemd services..."

# Virtual display service (needed for Wine/MT5)
cat > /etc/systemd/system/xvfb.service << 'XVFB_EOF'
[Unit]
Description=Xvfb Virtual Display
After=network.target

[Service]
Type=simple
User=trader
ExecStart=/usr/bin/Xvfb :99 -screen 0 1024x768x16 -ac
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
XVFB_EOF

# MT5 terminal service (runs under Wine)
cat > /etc/systemd/system/mt5-terminal.service << 'MT5_EOF'
[Unit]
Description=MetaTrader 5 Terminal (Wine)
After=xvfb.service
Requires=xvfb.service

[Service]
Type=simple
User=trader
Environment=WINEPREFIX=/home/trader/.wine
Environment=WINEDEBUG=-all
Environment=DISPLAY=:99
ExecStart=/usr/bin/wine "/home/trader/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe" /portable
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
MT5_EOF

# Trading bot service (runs Python under Wine)
cat > /etc/systemd/system/forex-trading.service << 'BOT_EOF'
[Unit]
Description=Forex Trading Bot
After=mt5-terminal.service
Requires=mt5-terminal.service

[Service]
Type=simple
User=trader
WorkingDirectory=/opt/trade_fx
EnvironmentFile=/opt/trade_fx/.env
Environment=WINEPREFIX=/home/trader/.wine
Environment=WINEDEBUG=-all
Environment=DISPLAY=:99
ExecStartPre=/bin/sleep 15
ExecStart=/usr/bin/wine "/home/trader/.wine/drive_c/users/trader/AppData/Local/Programs/Python/Python311/python.exe" main.py
Restart=always
RestartSec=10
StartLimitIntervalSec=300
StartLimitBurst=5

# Security hardening
NoNewPrivileges=true
PrivateTmp=true

# Resource limits
MemoryMax=3G
CPUQuota=200%

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=forex-trading

[Install]
WantedBy=multi-user.target
BOT_EOF

# Next.js dashboard service (native Node.js)
cat > /etc/systemd/system/forex-dashboard.service << 'DASH_EOF'
[Unit]
Description=Forex Dashboard (Next.js)
After=forex-trading.service

[Service]
Type=simple
User=trader
WorkingDirectory=/opt/trade_fx/dashboard/frontend
ExecStart=/usr/bin/node node_modules/.bin/next start --port 3000
Restart=always
RestartSec=5
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
DASH_EOF

systemctl daemon-reload
systemctl enable xvfb mt5-terminal forex-trading forex-dashboard

# ── 10. Configure Nginx reverse proxy ───────────────────────

log "[10/10] Configuring Nginx..."

cat > /etc/nginx/sites-available/forex-trading << 'NGINX_EOF'
# Forex Trading Bot - Nginx Reverse Proxy
# Dashboard (Next.js) on / and API on /api, /health, /docs

server {
    listen 80;
    server_name _;  # Replace with your domain if you have one

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # API and health endpoints → FastAPI (port 8000)
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }

    location /health {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    location /docs {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    location /openapi.json {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    # Dashboard → Next.js (port 3000)
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Deny access to sensitive files
    location ~ /\. { deny all; }
    location ~ \.env$ { deny all; }
}
NGINX_EOF

ln -sf /etc/nginx/sites-available/forex-trading /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

echo ""
echo "=========================================="
echo " Setup Complete!"
echo "=========================================="
echo ""
echo " NEXT STEPS:"
echo "  1. Edit /opt/trade_fx/.env with your credentials:"
echo "     sudo nano /opt/trade_fx/.env"
echo ""
echo "  2. Build the dashboard frontend:"
echo "     cd /opt/trade_fx/dashboard/frontend"
echo "     npm install && npm run build"
echo ""
echo "  3. Start all services:"
echo "     sudo systemctl start xvfb"
echo "     sudo systemctl start mt5-terminal"
echo "     sleep 15  # Wait for MT5 to initialize"
echo "     sudo systemctl start forex-trading"
echo "     sudo systemctl start forex-dashboard"
echo ""
echo "  4. Check status:"
echo "     sudo systemctl status forex-trading"
echo "     curl http://localhost/health"
echo ""
echo "  5. View logs:"
echo "     sudo journalctl -u forex-trading -f"
echo ""
echo "  6. Dashboard: http://YOUR_SERVER_IP"
echo ""
echo "  7. (Optional) Enable HTTPS:"
echo "     sudo certbot --nginx -d yourdomain.com"
echo ""
log "Setup complete!"
