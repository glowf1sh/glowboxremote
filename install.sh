#!/bin/bash
#
# Glowf1sh License System - Installer
# Installation script for BelaBox devices
#
# Usage: curl -fsSL https://raw.githubusercontent.com/glowf1sh/glowboxremote/main/install.sh | sudo bash
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
GITHUB_REPO="glowf1sh/glowboxremote"
GITHUB_BRANCH="main"
BASE_URL="https://raw.githubusercontent.com/${GITHUB_REPO}/${GITHUB_BRANCH}"
GITHUB_API="https://api.github.com/repos/${GITHUB_REPO}/releases/latest"
INSTALL_DIR="/opt/glowf1sh-remote"
RIST_DIR="/opt/glowf1sh-remote-rist"
GSTREAMER_DIR="/opt/gstreamer-1.24"
CLI_PATH="/usr/local/bin/glowf1sh-license"

# Header
echo ""
echo -e "${BLUE}╔═══════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  ${GREEN}Glowf1sh License System - Installer${BLUE}              ║${NC}"
echo -e "${BLUE}║  ${YELLOW}BelaBox Remote Management & Licensing${BLUE}            ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}ERROR: This script must be run as root (use sudo)${NC}"
    exit 1
fi

# Check system architecture
ARCH=$(uname -m)
if [ "$ARCH" != "aarch64" ] && [ "$ARCH" != "arm64" ]; then
    echo -e "${YELLOW}WARNING: This system is designed for ARM64 architecture${NC}"
    echo "Detected: $ARCH"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check internet connection
if ! ping -c 1 github.com &> /dev/null; then
    echo -e "${RED}ERROR: No internet connection. Please check your network.${NC}"
    exit 1
fi

echo -e "${GREEN}Starting installation...${NC}"
echo ""

# Step 1: Create directories
echo -e "${YELLOW}[1/11]${NC} Creating installation directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$RIST_DIR"
mkdir -p "$GSTREAMER_DIR"
mkdir -p "$INSTALL_DIR/api"
mkdir -p "$INSTALL_DIR/logs"
echo -e "  ${GREEN}✓${NC} Directories created"

# Step 2: Generate Box ID and hardware ID
echo -e "${YELLOW}[2/11]${NC} Generating Box ID and Hardware ID..."

# Generate box ID (format: gfbox-<word>-<number>)
WORDS=("tiger" "löwe" "falke" "adler" "wolf" "bär" "luchs" "fuchs" "rabe" "eule" "hai" "orca" "gepard" "panther" "puma" "stern" "mond" "komet" "meteor" "nova" "orion" "sirius" "rasalhague" "vega" "antares" "rigel" "deneb" "altair")
RANDOM_WORD=${WORDS[$RANDOM % ${#WORDS[@]}]}
RANDOM_NUM=$((RANDOM % 1000))
BOX_ID=$(printf "gfbox-%s-%03d" "$RANDOM_WORD" "$RANDOM_NUM")

# Generate hardware ID (SHA256 of machine-id)
if [ -f /etc/machine-id ]; then
    HARDWARE_ID=$(sha256sum /etc/machine-id | awk '{print $1}')
else
    # Fallback: use CPU serial or generate random ID
    HARDWARE_ID=$(cat /proc/cpuinfo 2>/dev/null | grep Serial | cut -d' ' -f2 | sha256sum | cut -d' ' -f1 2>/dev/null || cat /dev/urandom | tr -dc 'a-f0-9' | fold -w 64 | head -n 1)
fi

echo -e "  ${GREEN}✓${NC} Box ID: $BOX_ID"
echo -e "  ${GREEN}✓${NC} Hardware ID: ${HARDWARE_ID:0:16}..."

# Step 3: Create config.json
echo -e "${YELLOW}[3/11]${NC} Creating config.json..."
cat > "$INSTALL_DIR/api/config.json" <<EOF
{
  "box_id": "$BOX_ID",
  "hardware_id": "$HARDWARE_ID",
  "license_url": "https://license.gl0w.bot/api",
  "license_key": "",
  "first_seen": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "installer_version": "2.0.0"
}
EOF
chmod 644 "$INSTALL_DIR/api/config.json"
echo -e "  ${GREEN}✓${NC} config.json created"

# Step 4: Create initial license.json (with Dead Man's Switch fields)
echo -e "${YELLOW}[4/11]${NC} Creating initial license.json..."
cat > "$INSTALL_DIR/api/license.json" <<EOF
{
  "status": "inactive",
  "tier": "free",
  "jwt_token": "",
  "expires_at": "",
  "features": [],
  "last_validated": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "grace_period_hours": 24,
  "config_checksum": "",
  "license_checksum": ""
}
EOF
chmod 600 "$INSTALL_DIR/api/license.json"
echo -e "  ${GREEN}✓${NC} license.json created with Dead Man's Switch support"

# Step 5: Download and install CLI binary
echo -e "${YELLOW}[5/11]${NC} Installing CLI tool..."

# Try to get latest release URL
RELEASE_DATA=$(curl -s "$GITHUB_API" 2>/dev/null || echo "")
CLI_URL=$(echo "$RELEASE_DATA" | grep -o "https://github.com.*glowf1sh-license.*" | head -1 | tr -d '"')

if [ -z "$CLI_URL" ]; then
    echo -e "  ${YELLOW}⚠${NC}  CLI binary not found in latest release, trying direct download..."
    CLI_URL="$BASE_URL/cli/glowf1sh-license"
fi

if curl -fsSL "$CLI_URL" -o "$CLI_PATH" 2>/dev/null; then
    chmod 755 "$CLI_PATH"
    echo -e "  ${GREEN}✓${NC} CLI tool installed to $CLI_PATH"
else
    echo -e "  ${RED}✗${NC} Failed to download CLI tool (non-critical, continuing...)"
fi

# Step 6: Download and install Python modules (obfuscated from GitHub releases)
echo -e "${YELLOW}[6/11]${NC} Installing Python modules..."

MODULES=(
    "api-server.py"
    "auth-handler.py"
    "belabox-client.py"
    "cloud-client.py"
    "feature-enforcer.py"
    "license-validator.py"
    "update-handler.py"
)

INSTALLED_COUNT=0
for module in "${MODULES[@]}"; do
    # Try obfuscated version first (from GitHub workflow) - DISABLED
    # if curl -fsSL "$BASE_URL/obfuscated/$module" -o "$INSTALL_DIR/$module" 2>/dev/null; then
    #     chmod 500 "$INSTALL_DIR/$module"
    #     ((INSTALLED_COUNT++))
    # Fallback to non-obfuscated (for development)
    if curl -fsSL "$BASE_URL/belabox-api/$module" -o "$INSTALL_DIR/$module" 2>/dev/null; then
        chmod 500 "$INSTALL_DIR/$module"
        ((INSTALLED_COUNT++))
    fi
done

if [ $INSTALLED_COUNT -gt 0 ]; then
    echo -e "  ${GREEN}✓${NC} Installed $INSTALLED_COUNT/${#MODULES[@]} Python modules"
else
    echo -e "  ${YELLOW}⚠${NC}  No modules found (may need manual deployment)"
fi

# Step 7: Install PyArmor Runtime
echo -e "${YELLOW}[7/11]${NC} Installing PyArmor Runtime..."
if command -v pip3 &> /dev/null; then
    pip3 install -q pyarmor==7.7.4 2>/dev/null || echo -e "  ${YELLOW}⚠${NC}  PyArmor installation failed (non-critical)"
    echo -e "  ${GREEN}✓${NC} PyArmor Runtime installed"
else
    echo -e "  ${YELLOW}⚠${NC}  pip3 not found, skipping PyArmor installation"
fi

# Step 8: Download RIST modules
echo -e "${YELLOW}[8/11]${NC} Installing RIST modules..."

RIST_MODULES=(
    "rist-manager.py"
    "adaptive-controller.py"
    "license-client.py"
    "rist-profiles.py"
)

RIST_COUNT=0
for module in "${RIST_MODULES[@]}"; do
    if curl -fsSL "$BASE_URL/rist/$module" -o "$RIST_DIR/$module" 2>/dev/null; then
        chmod 500 "$RIST_DIR/$module"
        ((RIST_COUNT++))
    fi
done

if [ $RIST_COUNT -gt 0 ]; then
    echo -e "  ${GREEN}✓${NC} Installed $RIST_COUNT RIST modules"
else
    echo -e "  ${YELLOW}⚠${NC}  RIST modules not found (optional)"
fi

# Step 9: Download and verify GStreamer package
echo -e "${YELLOW}[9/11]${NC} Installing GStreamer package..."
echo "  Downloading GStreamer (this may take a moment)..."

if curl -fsSL "$BASE_URL/gstreamer-arm64.tar.xz" -o /tmp/gstreamer-arm64.tar.xz 2>/dev/null && \
   curl -fsSL "$BASE_URL/gstreamer-arm64.tar.xz.sha256" -o /tmp/gstreamer-arm64.tar.xz.sha256 2>/dev/null; then

    echo "  Verifying integrity..."
    cd /tmp
    if sha256sum -c gstreamer-arm64.tar.xz.sha256 >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} Verification successful"
        echo "  Extracting GStreamer..."
        tar -xJf gstreamer-arm64.tar.xz -C /opt/ 2>/dev/null || echo -e "  ${YELLOW}⚠${NC}  Extraction warning"
        rm -f gstreamer-arm64.tar.xz gstreamer-arm64.tar.xz.sha256
        echo -e "  ${GREEN}✓${NC} GStreamer installed to $GSTREAMER_DIR"
    else
        echo -e "  ${RED}✗${NC} Verification failed, skipping GStreamer installation"
        rm -f gstreamer-arm64.tar.xz gstreamer-arm64.tar.xz.sha256
    fi
else
    echo -e "  ${YELLOW}⚠${NC}  GStreamer package not found (optional)"
fi

# Step 10: Register box with license server
echo -e "${YELLOW}[10/11]${NC} Registering box with license server..."
REGISTER_RESPONSE=$(curl -s -X POST https://license.gl0w.bot/api/box/register \
  -H "Content-Type: application/json" \
  -H "X-Client-Type: glowfish-license-client" \
  -H "X-Client-Auth: glowfish-client-v1-production-key-2025" \
  -H "X-Client-Version: 2.0.0" \
  -d "{\"box_id\":\"$BOX_ID\",\"hardware_id\":\"$HARDWARE_ID\"}" 2>&1)

if echo "$REGISTER_RESPONSE" | grep -q "success"; then
    echo -e "  ${GREEN}✓${NC} Box registered successfully"
else
    echo -e "  ${YELLOW}⚠${NC}  Warning: Could not register with license server (offline installation?)"
    echo "  You can activate your license later with: glowf1sh-license activate"
fi

# Step 11: Install systemd service, timer, and hardening script
echo -e "${YELLOW}[11/11]${NC} Installing systemd services and hardening script..."

# Download and install service file
if curl -fsSL "$BASE_URL/systemd/glowf1sh-license-validator.service" -o /etc/systemd/system/glowf1sh-license-validator.service 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Service file installed"
else
    echo -e "  ${YELLOW}⚠${NC}  Service file not found"
fi

# Download and install timer file (Dead Man's Switch)
if curl -fsSL "$BASE_URL/systemd/glowf1sh-license-validator.timer" -o /etc/systemd/system/glowf1sh-license-validator.timer 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Timer file installed (Dead Man's Switch)"
else
    echo -e "  ${YELLOW}⚠${NC}  Timer file not found"
fi

# Download and install file hardening script
if curl -fsSL "$BASE_URL/scripts/harden-files.sh" -o "$INSTALL_DIR/harden-files.sh" 2>/dev/null; then
    chmod 755 "$INSTALL_DIR/harden-files.sh"
    echo -e "  ${GREEN}✓${NC} Hardening script installed"
else
    echo -e "  ${YELLOW}⚠${NC}  Hardening script not found"
fi

# Reload systemd and enable timer
systemctl daemon-reload 2>/dev/null || echo -e "  ${YELLOW}⚠${NC}  systemd not available"

# Set initial permissions (not fully hardened yet - user should run harden script after activation)
chown -R root:root "$INSTALL_DIR"
chmod 400 "$INSTALL_DIR/api/config.json" 2>/dev/null || true
chmod 600 "$INSTALL_DIR/api/license.json" 2>/dev/null || true
chmod 700 "$INSTALL_DIR/api" 2>/dev/null || true

# Installation complete
echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ✓ Installation Complete!${NC}                            ║"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BLUE}Box Information:${NC}"
echo -e "  Box ID:       ${GREEN}$BOX_ID${NC}"
echo -e "  Hardware ID:  ${GREEN}${HARDWARE_ID:0:32}...${NC}"
echo -e "  Install Path: ${GREEN}$INSTALL_DIR${NC}"
echo ""

echo -e "${BLUE}Next Steps:${NC}"
echo ""
echo -e "${YELLOW}1.${NC} Activate your license:"
echo -e "   ${GREEN}glowf1sh-license activate YOUR-LICENSE-KEY${NC}"
echo ""
echo -e "${YELLOW}2.${NC} Enable automatic license validation (Dead Man's Switch):"
echo -e "   ${GREEN}sudo systemctl enable --now glowf1sh-license-validator.timer${NC}"
echo ""
echo -e "${YELLOW}3.${NC} Harden file permissions (recommended after activation):"
echo -e "   ${GREEN}sudo $INSTALL_DIR/harden-files.sh${NC}"
echo ""
echo -e "${YELLOW}4.${NC} Check license status:"
echo -e "   ${GREEN}glowf1sh-license status${NC}"
echo ""
echo -e "${YELLOW}5.${NC} View service status:"
echo -e "   ${GREEN}sudo systemctl status glowf1sh-license-validator.timer${NC}"
echo ""

echo -e "${YELLOW}Note:${NC} The license validator timer will run every 30 minutes to"
echo -e "      maintain your license and detect tampering. A 24-hour grace"
echo -e "      period is provided for offline operation."
echo ""

echo -e "${GREEN}For more information, visit: https://github.com/${GITHUB_REPO}${NC}"
echo -e "${GREEN}Support: https://twitch.tv/glowf1sh${NC}"
echo ""
