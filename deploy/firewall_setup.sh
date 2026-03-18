#!/bin/bash
# ============================================================
# Oracle Cloud — Firewall Configuration
# Run as root: sudo bash deploy/firewall_setup.sh
# ============================================================
# Oracle Cloud uses iptables by default (not ufw)
# This script opens only the necessary ports
# ============================================================
set -euo pipefail

echo "Configuring firewall rules..."

# Allow SSH (port 22)
iptables -I INPUT 1 -p tcp --dport 22 -j ACCEPT

# Allow HTTP (port 80) — Nginx
iptables -I INPUT 2 -p tcp --dport 80 -j ACCEPT

# Allow HTTPS (port 443) — Nginx + SSL
iptables -I INPUT 3 -p tcp --dport 443 -j ACCEPT

# Save rules (Ubuntu/Oracle Linux)
if command -v netfilter-persistent &>/dev/null; then
    netfilter-persistent save
elif [ -f /etc/iptables/rules.v4 ]; then
    iptables-save > /etc/iptables/rules.v4
else
    apt-get install -y -qq iptables-persistent
    netfilter-persistent save
fi

echo ""
echo "Firewall configured:"
echo "  ✓ Port 22  (SSH)"
echo "  ✓ Port 80  (HTTP)"
echo "  ✓ Port 443 (HTTPS)"
echo ""
echo "IMPORTANT: You also need to open ports 80 and 443 in the"
echo "Oracle Cloud Console → Networking → Security Lists!"
echo ""
echo "Steps:"
echo "  1. Go to Oracle Cloud Console"
echo "  2. Networking → Virtual Cloud Networks → your VCN"
echo "  3. Subnets → your subnet → Security Lists"
echo "  4. Add Ingress Rules for TCP ports 80 and 443"
echo "     Source CIDR: 0.0.0.0/0"
echo ""
