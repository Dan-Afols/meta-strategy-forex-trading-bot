#!/bin/bash
set -e

echo "=== Installing Wine Staging (has anti-detection patches) ==="

# Remove current Wine Stable
echo "Removing wine-stable..."
sudo apt-get remove -y --purge winehq-stable wine-stable wine-stable-amd64 wine-stable-i386 2>/dev/null || true
sudo apt-get autoremove -y 2>/dev/null || true

echo ""
echo "=== Installing wine-staging ==="
# Wine Staging should already have the repo configured from previous setup
sudo apt-get update -qq 2>/dev/null

# Try installing wine-staging
sudo apt-get install -y winehq-staging 2>&1 | tail -10

echo ""
echo "=== Verify Wine Staging version ==="
wine --version 2>/dev/null || echo "Wine not found on path"
/opt/wine-staging/bin/wine --version 2>/dev/null || echo "Not at /opt/wine-staging"

echo "=== Wine Staging installed ==="
