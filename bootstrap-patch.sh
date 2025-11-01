#!/bin/bash
#
# Bootstrap Patch Script für Glowf1sh Remote
# Fixes systemd service ReadWritePaths to enable update system
#
# USAGE: Manuell ausführen auf catbox.oc-concepts.de -P 69
#   ssh -p 69 catbox.oc-concepts.de
#   bash /path/to/bootstrap-patch.sh
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Glowf1sh Remote - Bootstrap Patch${NC}"
echo -e "${BLUE}  Fixes update system deadlock${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}❌ This script must be run as root${NC}"
   exit 1
fi

echo -e "${YELLOW}[1/5]${NC} Checking systemd service..."

# Backup existing service
if [ -f /etc/systemd/system/glowf1sh-cloud-client.service ]; then
    cp /etc/systemd/system/glowf1sh-cloud-client.service /etc/systemd/system/glowf1sh-cloud-client.service.backup-$(date +%Y%m%d-%H%M%S)
    echo -e "  ${GREEN}✓${NC} Service backed up"
else
    echo -e "  ${RED}❌${NC} Service file not found!"
    exit 1
fi

echo -e "${YELLOW}[2/5]${NC} Updating systemd service ReadWritePaths..."

# Update ReadWritePaths in service file
sed -i 's|^ReadWritePaths=.*|ReadWritePaths=/opt/glowf1sh-remote /var/log /usr/bin|' /etc/systemd/system/glowf1sh-cloud-client.service

# Verify change
if grep -q "ReadWritePaths=/opt/glowf1sh-remote /var/log /usr/bin" /etc/systemd/system/glowf1sh-cloud-client.service; then
    echo -e "  ${GREEN}✓${NC} ReadWritePaths updated"
else
    echo -e "  ${RED}❌${NC} Failed to update ReadWritePaths"
    exit 1
fi

echo -e "${YELLOW}[3/5]${NC} Creating update log file..."

# Create log file with correct permissions
mkdir -p /var/log 2>/dev/null || true
touch /var/log/glowf1sh-update.log 2>/dev/null || true
chmod 666 /var/log/glowf1sh-update.log 2>/dev/null || true

if [ -f /var/log/glowf1sh-update.log ]; then
    echo -e "  ${GREEN}✓${NC} Log file created"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Bootstrap patch applied" >> /var/log/glowf1sh-update.log
else
    echo -e "  ${YELLOW}⚠${NC}  Could not create log file (will use console logging)"
fi

echo -e "${YELLOW}[4/5]${NC} Reloading systemd daemon..."

systemctl daemon-reload
echo -e "  ${GREEN}✓${NC} Daemon reloaded"

echo -e "${YELLOW}[5/5]${NC} Restarting cloud client service..."

systemctl restart glowf1sh-cloud-client.service

# Wait for service to start
sleep 3

if systemctl is-active --quiet glowf1sh-cloud-client.service; then
    echo -e "  ${GREEN}✓${NC} Service restarted successfully"
else
    echo -e "  ${RED}❌${NC} Service failed to start!"
    echo -e "  Check logs: journalctl -u glowf1sh-cloud-client -n 50"
    exit 1
fi

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✅ Bootstrap patch applied successfully!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "The update system is now operational."
echo -e "Updates will be received automatically from cloud.gl0w.bot"
echo ""
echo -e "To verify: tail -f /var/log/glowf1sh-update.log"
echo ""
