#!/bin/bash
# deploy.sh — skopíruje portal súbory do produkcie a voliteľne reštartuje API
set -e

PORTAL_DIR="/var/www/portal.innovativeit.sk"
API_SRC="/root/soc-project/soc-portal/soc-swprobe-api.py"
API_DST="/opt/soc/swprobe/soc-swprobe-api.py"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== SOC Portal Deploy ==="
echo "Zdroj: $SCRIPT_DIR"
echo "Cieľ:  $PORTAL_DIR"
echo ""

# Portal frontend
for f in index.html ui.js auth.js dashboard.js canvas.js operator.html partner.html; do
    if [ -f "$SCRIPT_DIR/$f" ]; then
        cp "$SCRIPT_DIR/$f" "$PORTAL_DIR/$f"
        echo "  ✓ $f"
    fi
done

# Flask API (voliteľné — len ak sa zmenil)
if [ "$1" = "--api" ]; then
    cp "$API_SRC" "$API_DST"
    echo "  ✓ soc-swprobe-api.py"
    systemctl restart flask-soc.service
    sleep 2
    systemctl is-active flask-soc.service && echo "  ✓ flask-soc reštartovaný" || echo "  ✗ flask-soc FAILED"
fi

echo ""
echo "Deploy hotový: $(date '+%Y-%m-%d %H:%M:%S')"
