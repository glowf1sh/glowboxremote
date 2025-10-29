#!/bin/bash
#
# Glowf1sh License System - Installer
# Installation script for BelaBox devices
#
# Usage:
#   Install:   curl -fsSL https://raw.githubusercontent.com/glowf1sh/glowboxremote/main/install.sh | sudo bash
#   Uninstall: curl -fsSL https://raw.githubusercontent.com/glowf1sh/glowboxremote/main/install.sh -o /tmp/install.sh && sudo bash /tmp/install.sh --uninstall
#   Or:        UNINSTALL=1 curl -fsSL https://raw.githubusercontent.com/glowf1sh/glowboxremote/main/install.sh | sudo -E bash
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
CONFIG_DIR="$INSTALL_DIR/config"
BELABOX_API_DIR="$INSTALL_DIR/belabox-api"
RIST_DIR="$INSTALL_DIR/rist"
GSTREAMER_DIR="$INSTALL_DIR/gstreamer"
SCRIPTS_DIR="$INSTALL_DIR/scripts"
CLI_DIR="$INSTALL_DIR/cli"
CLI_BINARY="$CLI_DIR/glowf1sh-license"
CLI_SYMLINK="/usr/bin/glowf1sh-license"
BOX_ID_CACHE="/etc/.glowf1sh-box-id"

# Uninstall function
uninstall_glowf1sh() {
    echo ""
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║  ${RED}Glowf1sh License System - UNINSTALLER${BLUE}                ║${NC}"
    echo -e "${BLUE}║  ${YELLOW}Removing all components${BLUE}                              ║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════════════════╝${NC}"
    echo ""

    # Check if anything is actually installed
    FOUND_COMPONENTS=0
    [ -d "$INSTALL_DIR" ] && FOUND_COMPONENTS=$((FOUND_COMPONENTS + 1))
    [ -f "$CLI_BINARY" ] && FOUND_COMPONENTS=$((FOUND_COMPONENTS + 1))
    [ -n "$(ls /etc/systemd/system/glowf1sh-*.service /etc/systemd/system/glowf1sh-*.timer 2>/dev/null)" ] && FOUND_COMPONENTS=$((FOUND_COMPONENTS + 1))

    if [ $FOUND_COMPONENTS -eq 0 ]; then
        echo -e "${YELLOW}⚠  Nothing to uninstall - no Glowf1sh components found${NC}"
        echo ""
        exit 0
    fi

    echo -e "Found ${GREEN}$FOUND_COMPONENTS${NC} component(s) to remove"
    echo ""

    # Confirm uninstallation
    echo -e "${YELLOW}WARNING: This will remove all Glowf1sh components!${NC}"
    echo ""

    # Only prompt if interactive terminal
    if [ -t 0 ]; then
        read -p "Backup config files before uninstall? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            if [ -d "$CONFIG_DIR" ]; then
                BACKUP_DIR="/tmp/glowf1sh-backup-$(date +%Y%m%d-%H%M%S)"
                mkdir -p "$BACKUP_DIR"
                cp -r "$CONFIG_DIR" "$BACKUP_DIR/"
                echo -e "  ${GREEN}✓${NC} Config backed up to: $BACKUP_DIR"
            fi
        fi

        echo ""
        read -p "Continue with uninstallation? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Uninstallation cancelled."
            exit 0
        fi
    else
        # Non-interactive, proceed without backup
        echo -e "  ${BLUE}→${NC} Non-interactive mode: proceeding with uninstallation (no backup)"
    fi

    echo ""
    echo -e "${YELLOW}[1/7]${NC} Stopping and disabling services..."

    # Stop and disable all glowf1sh services (find them dynamically)
    FOUND_SERVICES=$(systemctl list-units --all --type=service --no-pager --no-legend 2>/dev/null | grep glowf1sh | awk '{print $1}' | sed 's/\.service//')
    SERVICE_COUNT=0
    if [ -n "$FOUND_SERVICES" ]; then
        for service in $FOUND_SERVICES; do
            # Skip if service name contains unicode or special chars
            if [[ ! "$service" =~ ^[a-zA-Z0-9_-]+$ ]]; then
                continue
            fi
            if systemctl is-active --quiet "$service" 2>/dev/null; then
                systemctl stop "$service" 2>/dev/null && echo "  - Stopped: $service" && SERVICE_COUNT=$((SERVICE_COUNT + 1))
            fi
            if systemctl is-enabled --quiet "$service" 2>/dev/null; then
                systemctl disable "$service" 2>/dev/null && echo "  - Disabled: $service"
            fi
        done
    fi

    # Stop and disable all glowf1sh timers
    FOUND_TIMERS=$(systemctl list-units --all --type=timer --no-pager --no-legend 2>/dev/null | grep glowf1sh | awk '{print $1}' | sed 's/\.timer//')
    if [ -n "$FOUND_TIMERS" ]; then
        for timer in $FOUND_TIMERS; do
            # Skip if timer name contains unicode or special chars
            if [[ ! "$timer" =~ ^[a-zA-Z0-9_-]+$ ]]; then
                continue
            fi
            if systemctl is-active --quiet "${timer}.timer" 2>/dev/null; then
                systemctl stop "${timer}.timer" 2>/dev/null && echo "  - Stopped: ${timer}.timer" && SERVICE_COUNT=$((SERVICE_COUNT + 1))
            fi
            if systemctl is-enabled --quiet "${timer}.timer" 2>/dev/null; then
                systemctl disable "${timer}.timer" 2>/dev/null && echo "  - Disabled: ${timer}.timer"
            fi
        done
    fi

    if [ $SERVICE_COUNT -gt 0 ]; then
        echo -e "  ${GREEN}✓${NC} Stopped and disabled $SERVICE_COUNT service(s)"
    else
        echo -e "  ${GREEN}✓${NC} No running services found"
    fi

    echo -e "${YELLOW}[2/7]${NC} Removing systemd service files..."
    rm -f /etc/systemd/system/glowf1sh-*.service
    rm -f /etc/systemd/system/glowf1sh-*.timer
    systemctl daemon-reload
    echo -e "  ${GREEN}✓${NC} Service files removed"

    echo -e "${YELLOW}[3/7]${NC} Removing file immutability flags..."
    if [ -f "$CONFIG_DIR/config.json" ]; then
        chattr -i "$CONFIG_DIR/config.json" 2>/dev/null || true
    fi
    if [ -f "$CONFIG_DIR/license.json" ]; then
        chattr -i "$CONFIG_DIR/license.json" 2>/dev/null || true
    fi
    echo -e "  ${GREEN}✓${NC} Immutability flags removed"

    echo -e "${YELLOW}[4/7]${NC} Removing installation directory..."
    if [ -d "$INSTALL_DIR" ]; then
        # List what will be removed (excluding belaUI which we don't touch)
        echo "  Removing: $INSTALL_DIR"
        rm -rf "$INSTALL_DIR"
        echo -e "  ${GREEN}✓${NC} $INSTALL_DIR removed"
    else
        echo -e "  ${YELLOW}⚠${NC}  Directory not found"
    fi

    echo -e "${YELLOW}[5/7]${NC} Removing CLI tool and symlinks..."
    # Remove symlink
    if [ -L "$CLI_SYMLINK" ] || [ -f "$CLI_SYMLINK" ]; then
        rm -f "$CLI_SYMLINK"
        echo -e "  ${GREEN}✓${NC} Symlink removed: $CLI_SYMLINK"
    fi
    # Remove binary (will be removed with INSTALL_DIR anyway, but explicit is better)
    if [ -f "$CLI_BINARY" ]; then
        rm -f "$CLI_BINARY"
        echo -e "  ${GREEN}✓${NC} Binary removed: $CLI_BINARY"
    fi
    # Remove any old/legacy symlinks from previous installations
    rm -f /usr/local/bin/glowf1sh-license 2>/dev/null || true
    rm -f /usr/local/sbin/glowf1sh-license 2>/dev/null || true

    echo -e "${YELLOW}[6/7]${NC} Cleaning up logs and temporary files..."
    # Remove logs
    rm -rf /var/log/glowf1sh* 2>/dev/null || true
    # Remove any leftover files in tmp
    rm -rf /tmp/glowf1sh-* 2>/dev/null || true
    rm -rf /tmp/gstreamer-arm64.tar.xz 2>/dev/null || true
    rm -rf /tmp/requirements.txt 2>/dev/null || true
    echo -e "  ${GREEN}✓${NC} Logs and temp files cleaned"

    echo -e "${YELLOW}[7/7]${NC} Final cleanup and verification..."
    # Verify everything is removed
    if [ ! -d "$INSTALL_DIR" ] && [ ! -f "$CLI_BINARY" ]; then
        echo -e "  ${GREEN}✓${NC} All components removed successfully"
    else
        echo -e "  ${YELLOW}⚠${NC}  Some components may still exist"
    fi
    echo -e "  ${GREEN}✓${NC} Cleanup complete"

    echo ""
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  Uninstallation completed successfully!               ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════╝${NC}"
    echo ""

    exit 0
}

# Check for uninstall argument
if [ "$1" = "--uninstall" ] || [ "$1" = "-u" ] || [ "$UNINSTALL" = "1" ]; then
    uninstall_glowf1sh
fi

# Header
echo ""
echo -e "${BLUE}╔═══════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  ${GREEN}Glowf1sh License System - Installer${BLUE}                  ║${NC}"
echo -e "${BLUE}║  ${YELLOW}BelaBox Remote Management & Licensing${BLUE}                ║${NC}"
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
echo -e "${YELLOW}[1/13]${NC} Creating installation directories..."
mkdir -p "$CONFIG_DIR"
mkdir -p "$BELABOX_API_DIR"
mkdir -p "$RIST_DIR"
mkdir -p "$GSTREAMER_DIR"
mkdir -p "$SCRIPTS_DIR"
mkdir -p "$CLI_DIR"
mkdir -p "$INSTALL_DIR/logs"
echo -e "  ${GREEN}✓${NC} Directories created"

# Step 2: Install CLI binary from repository (MOVED UP - needed for hardware ID)
echo -e "${YELLOW}[2/13]${NC} Installing CLI tool..."

# Expected CLI binary checksum (SHA256)
CLI_EXPECTED_SHA256="4da45c1824807bab6c7793ffff13022f6c78bd453bad0f5310b99a9c3c346232"

# Check if CLI binary exists in current directory (Git repo)
if [ -f "./cli/glowf1sh-license" ]; then
    # Copy from local repo
    mkdir -p "$CLI_DIR"
    cp "./cli/glowf1sh-license" "$CLI_BINARY"
    chmod 755 "$CLI_BINARY"
    echo -e "  ${GREEN}✓${NC} CLI binary installed to $CLI_BINARY"

    # Verify checksum
    if command -v sha256sum >/dev/null 2>&1; then
        CLI_ACTUAL_SHA256=$(sha256sum "$CLI_BINARY" | awk '{print $1}')
        if [ "$CLI_EXPECTED_SHA256" != "$CLI_ACTUAL_SHA256" ]; then
            echo -e "  ${RED}✗${NC} CLI binary checksum mismatch!"
            echo -e "  Expected: $CLI_EXPECTED_SHA256"
            echo -e "  Got:      $CLI_ACTUAL_SHA256"
            echo -e "  ${RED}Installation aborted - binary may be tampered!${NC}"
            rm -f "$CLI_BINARY"
            exit 1
        fi
        echo -e "  ${GREEN}✓${NC} CLI binary integrity verified (SHA256)"
    else
        echo -e "  ${YELLOW}⚠${NC}  sha256sum not found - skipping checksum verification"
    fi

    # Create system-wide symlink
    ln -sf "$CLI_BINARY" "$CLI_SYMLINK"
    echo -e "  ${GREEN}✓${NC} Symlink created: $CLI_SYMLINK → $CLI_BINARY"
else
    # Fallback: Try to download from GitHub
    echo -e "  ${YELLOW}⚠${NC}  CLI binary not found locally, trying GitHub download..."
    CLI_URL="$BASE_URL/cli/glowf1sh-license"

    if curl -fsSL "$CLI_URL" -o "$CLI_BINARY" 2>/dev/null; then
        chmod 755 "$CLI_BINARY"
        echo -e "  ${GREEN}✓${NC} CLI binary downloaded to $CLI_BINARY"

        # Verify checksum
        if command -v sha256sum >/dev/null 2>&1; then
            CLI_ACTUAL_SHA256=$(sha256sum "$CLI_BINARY" | awk '{print $1}')
            if [ "$CLI_EXPECTED_SHA256" != "$CLI_ACTUAL_SHA256" ]; then
                echo -e "  ${RED}✗${NC} Downloaded binary checksum mismatch!"
                echo -e "  Expected: $CLI_EXPECTED_SHA256"
                echo -e "  Got:      $CLI_ACTUAL_SHA256"
                echo -e "  ${RED}Installation aborted - binary may be tampered!${NC}"
                rm -f "$CLI_BINARY"
                exit 1
            fi
            echo -e "  ${GREEN}✓${NC} Downloaded binary integrity verified (SHA256)"
        else
            echo -e "  ${YELLOW}⚠${NC}  sha256sum not found - skipping checksum verification"
        fi

        # Create system-wide symlink
        ln -sf "$CLI_BINARY" "$CLI_SYMLINK"
        echo -e "  ${GREEN}✓${NC} Symlink created: $CLI_SYMLINK → $CLI_BINARY"
    else
        echo -e "  ${RED}✗${NC} Failed to install CLI tool"
        echo -e "  ${RED}Installation aborted - CLI tool is required for hardware ID generation${NC}"
        exit 1
    fi
fi

# Step 3: Generate Hardware ID using CLI tool
echo -e "${YELLOW}[3/13]${NC} Generating Hardware ID..."

# Use CLI to get hardware ID (CPU serial + ETH MACs)
HARDWARE_ID=$("$CLI_BINARY" hardware-id)

if [ -z "$HARDWARE_ID" ]; then
    echo -e "  ${RED}✗${NC} Failed to generate hardware ID"
    exit 1
fi

echo -e "  ${GREEN}✓${NC} Hardware ID: [Generated and secured]"

# Step 4: Generate Box ID (with recovery from local cache, then license server)
echo -e "${YELLOW}[4/13]${NC} Generating Box ID..."

BOX_ID=""

# Priority 1: Check local cache file (survives uninstall/reinstall)
if [ -f "$BOX_ID_CACHE" ]; then
    CACHED_BOX_ID=$(cat "$BOX_ID_CACHE" 2>/dev/null | tr -d '\n\r ')
    if [ ! -z "$CACHED_BOX_ID" ] && [[ "$CACHED_BOX_ID" =~ ^gfbox-[a-z]+-[0-9]+$ ]]; then
        BOX_ID="$CACHED_BOX_ID"
        echo -e "  ${BLUE}→${NC} Box ID restored from local cache (persistent)"
    fi
fi

# Priority 2: Check if this hardware already has a registered box_id on server (Box ID Recovery)
if [ -z "$BOX_ID" ]; then
    if command -v jq &> /dev/null && command -v curl &> /dev/null; then
        EXISTING_BOX_ID=$(curl -s --max-time 10 -X POST https://license.gl0w.bot/api/box/lookup-by-hardware \
          -H "Content-Type: application/json" \
          -H "X-Client-Type: glowfish-license-client" \
          -H "X-Client-Auth: glowfish-client-v1-production-key-2025" \
          -H "X-Client-Version: 2.0.0" \
          -d "{\"hardware_id\":\"$HARDWARE_ID\"}" 2>/dev/null | jq -r '.box_id // empty' 2>/dev/null)

        if [ ! -z "$EXISTING_BOX_ID" ] && [ "$EXISTING_BOX_ID" != "null" ]; then
            BOX_ID="$EXISTING_BOX_ID"
            echo -e "  ${BLUE}→${NC} Box ID recovered from license server"
        fi
    fi
fi

# Priority 3: Generate new box_id
if [ -z "$BOX_ID" ]; then
    # Generate new box ID (format: gfbox-<word>-<number>)
    # Words: gods, planets, stars, elements, creatures, demons, angels, animals, military, space missions, pokemon (max 12 chars)
    WORDS=(
        "zeus" "apollo" "athena" "poseidon" "hades" "ares" "hermes" "thor" "odin" "loki" "freya" "balder"
        "mercury" "venus" "earth" "mars" "jupiter" "saturn" "uranus" "neptune" "pluto"
        "sirius" "vega" "altair" "rigel" "deneb" "antares" "polaris" "canopus" "procyon" "capella" "arcturus" "aldebaran"
        "helium" "neon" "argon" "krypton" "xenon" "radon" "lithium" "carbon" "oxygen" "nitrogen" "hydrogen" "iron" "gold" "silver" "copper" "zinc"
        "phoenix" "dragon" "unicorn" "griffin" "basilisk" "hydra" "kraken" "cerberus" "pegasus" "sphinx" "chimera" "manticore"
        "asmodeus" "baal" "belial" "mammon" "lucifer" "moloch" "azazel" "beelzebub" "abaddon" "belphegor"
        "gabriel" "michael" "raphael" "uriel" "azrael" "jophiel" "chamuel" "zadkiel" "haniel" "metatron"
        "tiger" "lion" "falcon" "eagle" "wolf" "bear" "lynx" "fox" "raven" "owl" "shark" "orca" "cheetah" "panther" "puma" "leopard" "jaguar" "cougar"
        "blackbird" "raptor" "stealth" "phantom" "viper" "cobra" "javelin" "patriot" "tomahawk" "harrier" "hornet" "warthog" "apache" "chinook"
        "voyager" "pioneer" "galileo" "cassini" "juno" "hubble" "kepler" "curiosity" "spirit" "mariner" "viking"
        "pikachu" "charizard" "mewtwo" "blastoise" "gengar" "dragonite" "lucario" "greninja" "rayquaza" "garchomp" "tyranitar" "salamence" "metagross" "alakazam" "machamp" "gyarados" "snorlax" "lapras" "eevee" "umbreon" "espeon" "jolteon" "flareon" "vaporeon"
    )
    RANDOM_WORD=${WORDS[$RANDOM % ${#WORDS[@]}]}
    RANDOM_NUM=$((RANDOM % 1000))
    BOX_ID=$(printf "gfbox-%s-%03d" "$RANDOM_WORD" "$RANDOM_NUM")
    echo -e "  ${BLUE}→${NC} New Box ID generated"
fi

# Save Box ID to persistent cache (survives uninstall)
echo "$BOX_ID" > "$BOX_ID_CACHE"
chmod 600 "$BOX_ID_CACHE"

echo -e "  ${GREEN}✓${NC} Box ID: $BOX_ID"

# Step 5: Create config.json
echo -e "${YELLOW}[5/13]${NC} Creating config.json..."
cat > "$CONFIG_DIR/config.json" <<EOF
{
  "box_id": "$BOX_ID",
  "hardware_id": "$HARDWARE_ID",
  "license_url": "https://license.gl0w.bot/api",
  "license_key": "",
  "first_seen": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "installer_version": "2.0.0"
}
EOF
chmod 400 "$CONFIG_DIR/config.json"
chattr +i "$CONFIG_DIR/config.json"
echo -e "  ${GREEN}✓${NC} config.json created (secured with immutable flag)"

# Step 6: Create initial license.json
echo -e "${YELLOW}[6/13]${NC} Creating initial license.json..."
cat > "$CONFIG_DIR/license.json" <<EOF
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
chmod 600 "$CONFIG_DIR/license.json"
echo -e "  ${GREEN}✓${NC} license.json created"

# Step 7: Install Python dependencies
echo -e "${YELLOW}[7/13]${NC} Installing Python dependencies..."
if command -v pip3 &> /dev/null; then
    # Try to download requirements.txt from GitHub
    if curl -fsSL "$BASE_URL/requirements.txt" -o /tmp/requirements.txt 2>/dev/null; then
        echo "  Installing packages from requirements.txt..."
        if timeout 300 pip3 install -q -r /tmp/requirements.txt 2>/dev/null; then
            echo -e "  ${GREEN}✓${NC} Python dependencies installed from requirements.txt"
        else
            echo -e "  ${YELLOW}⚠${NC}  requirements.txt installation failed, trying fallback..."
            pip3 install -q pyarmor==7.7.4 websocket-client websockets requests flask psutil 2>/dev/null || true
            echo -e "  ${GREEN}✓${NC} Python dependencies installed (fallback)"
        fi
        rm -f /tmp/requirements.txt
    else
        echo "  requirements.txt not found, installing core packages directly..."
        pip3 install -q pyarmor==7.7.4 websocket-client websockets requests flask psutil 2>/dev/null || true
        echo -e "  ${GREEN}✓${NC} Core Python packages installed"
    fi
else
    echo -e "  ${YELLOW}⚠${NC}  pip3 not found, skipping Python dependencies"
fi

# Step 8: Download and install Python modules
echo -e "${YELLOW}[8/13]${NC} Installing Python modules..."

MODULES=(
    "api_server.py"
    "belabox_client.py"
    "cloud_client.py"
    "update_handler.py"
    "license-validator.py"
)

INSTALLED_COUNT=0
for module in "${MODULES[@]}"; do
    echo "  Downloading $module..."
    # Try obfuscated version first (from GitHub workflow) - DISABLED
    # if curl -fsSL "$BASE_URL/obfuscated/$module" -o "$BELABOX_API_DIR/$module" 2>/dev/null; then
    #     chmod 500 "$BELABOX_API_DIR/$module"
    #     INSTALLED_COUNT=$((INSTALLED_COUNT + 1))
    # Fallback to non-obfuscated (for development)
    if curl -fsSL --max-time 30 "$BASE_URL/belabox-api/$module" -o "$BELABOX_API_DIR/$module" 2>/dev/null; then
        chmod 500 "$BELABOX_API_DIR/$module"
        INSTALLED_COUNT=$((INSTALLED_COUNT + 1))
        echo "    ✓ $module"
    else
        echo "    ✗ Failed to download $module (will retry...)"
        # Retry once
        if curl -fsSL --max-time 30 "$BASE_URL/belabox-api/$module" -o "$BELABOX_API_DIR/$module" 2>/dev/null; then
            chmod 500 "$BELABOX_API_DIR/$module"
            INSTALLED_COUNT=$((INSTALLED_COUNT + 1))
            echo "    ✓ $module (retry successful)"
        fi
    fi
done

if [ $INSTALLED_COUNT -gt 0 ]; then
    echo -e "  ${GREEN}✓${NC} Installed $INSTALLED_COUNT/${#MODULES[@]} Python modules"
else
    echo -e "  ${YELLOW}⚠${NC}  No modules found (may need manual deployment)"
fi

# Step 6.5: Download _core runtime for belabox-api (PyArmor)
echo "  Installing PyArmor runtime (_core)..."
mkdir -p "$BELABOX_API_DIR/_core"
if curl -fsSL --max-time 30 "$BASE_URL/belabox-api/_core/__init__.py" -o "$BELABOX_API_DIR/_core/__init__.py" 2>/dev/null && \
   curl -fsSL --max-time 60 "$BASE_URL/belabox-api/_core/_pytransform.so" -o "$BELABOX_API_DIR/_core/_pytransform.so" 2>/dev/null; then
    chmod 500 "$BELABOX_API_DIR/_core/__init__.py"
    chmod 500 "$BELABOX_API_DIR/_core/_pytransform.so"
    echo -e "  ${GREEN}✓${NC} PyArmor runtime installed for belabox-api"
else
    echo -e "  ${YELLOW}⚠${NC}  PyArmor runtime not found (scripts may not work if obfuscated)"
fi

# Step 9: Download RIST modules
echo -e "${YELLOW}[9/13]${NC} Installing RIST modules..."

RIST_MODULES=(
    "rist_manager.py"
    "adaptive_controller.py"
    "license_client.py"
    "rist_profiles.py"
)

RIST_COUNT=0
for module in "${RIST_MODULES[@]}"; do
    echo "  Downloading $module..."
    if curl -fsSL --max-time 30 "$BASE_URL/rist/$module" -o "$RIST_DIR/$module" 2>/dev/null; then
        chmod 500 "$RIST_DIR/$module"
        RIST_COUNT=$((RIST_COUNT + 1))
        echo "    ✓ $module"
    else
        echo "    ⚠ Failed to download $module (optional, skipping)"
    fi
done

if [ $RIST_COUNT -gt 0 ]; then
    echo -e "  ${GREEN}✓${NC} Installed $RIST_COUNT RIST modules"
else
    echo -e "  ${YELLOW}⚠${NC}  RIST modules not found (optional)"
fi

# Step 8.5: Download _core runtime for rist (PyArmor)
echo "  Installing PyArmor runtime for RIST (_core)..."
mkdir -p "$RIST_DIR/_core"
if curl -fsSL --max-time 30 "$BASE_URL/rist/_core/__init__.py" -o "$RIST_DIR/_core/__init__.py" 2>/dev/null && \
   curl -fsSL --max-time 60 "$BASE_URL/rist/_core/_pytransform.so" -o "$RIST_DIR/_core/_pytransform.so" 2>/dev/null; then
    chmod 500 "$RIST_DIR/_core/__init__.py"
    chmod 500 "$RIST_DIR/_core/_pytransform.so"
    echo -e "  ${GREEN}✓${NC} PyArmor runtime installed for RIST"
else
    echo -e "  ${YELLOW}⚠${NC}  RIST PyArmor runtime not found (optional)"
fi

# Step 10: Download and verify GStreamer package
echo -e "${YELLOW}[10/13]${NC} Installing GStreamer package..."
echo "  Downloading GStreamer (this may take a moment)..."

if curl -fsSL "$BASE_URL/gstreamer-arm64.tar.xz" -o /tmp/gstreamer-arm64.tar.xz 2>/dev/null && \
   curl -fsSL "$BASE_URL/gstreamer-arm64.tar.xz.sha256" -o /tmp/gstreamer-arm64.tar.xz.sha256 2>/dev/null; then

    echo "  Verifying integrity..."
    cd /tmp
    if sha256sum -c gstreamer-arm64.tar.xz.sha256 >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} Verification successful"
        echo "  Extracting GStreamer..."
        tar -xJf gstreamer-arm64.tar.xz -C "$GSTREAMER_DIR" --strip-components=1 2>/dev/null || echo -e "  ${YELLOW}⚠${NC}  Extraction warning"
        rm -f gstreamer-arm64.tar.xz gstreamer-arm64.tar.xz.sha256
        echo -e "  ${GREEN}✓${NC} GStreamer installed to $GSTREAMER_DIR"
    else
        echo -e "  ${RED}✗${NC} Verification failed, skipping GStreamer installation"
        rm -f gstreamer-arm64.tar.xz gstreamer-arm64.tar.xz.sha256
    fi
else
    echo -e "  ${YELLOW}⚠${NC}  GStreamer package not found (optional)"
fi

# Step 11: Register box with license server
echo -e "${YELLOW}[11/13]${NC} Registering box with license server..."
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
fi

# Step 12: License activation (interactive)
echo -e "${YELLOW}[12/13]${NC} License activation..."

# Only prompt if running in interactive terminal
# Use /dev/tty to handle piped execution (curl | bash)
if [ -t 1 ] && [ -e /dev/tty ]; then
    echo ""
    read -p "Do you have a license key to activate now? [y/N]: " -n 1 -r < /dev/tty
    echo
else
    # Non-interactive, skip license activation
    REPLY="n"
fi

if [[ $REPLY =~ ^[Yy]$ ]]; then
    MAX_ATTEMPTS=3
    ATTEMPT=1
    LICENSE_ACTIVATED=false

    while [ $ATTEMPT -le $MAX_ATTEMPTS ] && [ "$LICENSE_ACTIVATED" = "false" ]; do
        if [ $ATTEMPT -eq 1 ]; then
            read -p "Enter your license key: " LICENSE_KEY < /dev/tty
        else
            echo ""
            read -p "Enter your license key (attempt $ATTEMPT/$MAX_ATTEMPTS): " LICENSE_KEY < /dev/tty
        fi

        if [ -z "$LICENSE_KEY" ]; then
            echo -e "  ${YELLOW}⚠${NC}  No license key entered"
            read -p "Skip license activation? [Y/n]: " -n 1 -r < /dev/tty
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                echo -e "  ${BLUE}→${NC} You can activate later with: ${GREEN}glowf1sh-license activate YOUR-KEY${NC}"
                break
            fi
        else
            echo "  Activating license..."
            # Use the CLI binary for license activation
            if [ -f "$CLI_BINARY" ]; then
                set +e  # Temporarily disable exit on error
                ACTIVATE_OUTPUT=$("$CLI_BINARY" activate "$LICENSE_KEY" 2>&1)
                EXIT_CODE=$?
                set -e  # Re-enable exit on error
                if [ $EXIT_CODE -eq 0 ]; then
                    echo -e "  ${GREEN}✓${NC} License activated successfully"
                    LICENSE_ACTIVATED=true
                else
                    echo -e "  ${RED}✗${NC} License activation failed:"
                    echo "$ACTIVATE_OUTPUT" | sed 's/^/    /'

                    if [ $ATTEMPT -lt $MAX_ATTEMPTS ]; then
                        echo -e "  ${YELLOW}→${NC} Please try again"
                    else
                        echo -e "  ${YELLOW}→${NC} Maximum attempts reached"
                        echo -e "  ${YELLOW}→${NC} You can try again later with: glowf1sh-license activate YOUR-KEY"
                    fi
                fi
            else
                echo -e "  ${RED}✗${NC} CLI tool not available"
                echo -e "  ${YELLOW}→${NC} You can activate later with: glowf1sh-license activate YOUR-KEY"
                break
            fi
        fi

        ((ATTEMPT++))
    done
else
    echo -e "  ${BLUE}→${NC} You can activate your license later with: ${GREEN}glowf1sh-license activate YOUR-KEY${NC}"
fi

# Step 13: Install systemd service, timer, and scripts
echo -e "${YELLOW}[13/13]${NC} Installing system services..."

# Download and install service file
if curl -fsSL "$BASE_URL/systemd/glowf1sh-license-validator.service" -o /etc/systemd/system/glowf1sh-license-validator.service 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Service file installed"
else
    echo -e "  ${YELLOW}⚠${NC}  Service file not found"
fi

# Download and install timer file
if curl -fsSL "$BASE_URL/systemd/glowf1sh-license-validator.timer" -o /etc/systemd/system/glowf1sh-license-validator.timer 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Timer file installed"
else
    echo -e "  ${YELLOW}⚠${NC}  Timer file not found"
fi

# Download and install system scripts
if curl -fsSL "$BASE_URL/scripts/harden-files.sh" -o "$SCRIPTS_DIR/harden-files.sh" 2>/dev/null; then
    chmod 755 "$SCRIPTS_DIR/harden-files.sh"
    echo -e "  ${GREEN}✓${NC} System scripts installed"
else
    echo -e "  ${YELLOW}⚠${NC}  System scripts not found"
fi

# Reload systemd and enable timer
systemctl daemon-reload 2>/dev/null || echo -e "  ${YELLOW}⚠${NC}  systemd not available"

# Enable and start the license validator timer
if systemctl enable glowf1sh-license-validator.timer 2>/dev/null; then
    systemctl start glowf1sh-license-validator.timer 2>/dev/null
    echo -e "  ${GREEN}✓${NC} License validator timer enabled and started"
else
    echo -e "  ${YELLOW}⚠${NC}  Could not enable timer (systemd not available?)"
fi

# Set initial permissions
# Temporarily remove immutable flag before chown
chattr -i "$CONFIG_DIR/config.json" 2>/dev/null || true
chown -R root:root "$INSTALL_DIR"
chmod 400 "$CONFIG_DIR/config.json" 2>/dev/null || true
chmod 600 "$CONFIG_DIR/license.json" 2>/dev/null || true
chmod 700 "$CONFIG_DIR" 2>/dev/null || true
# Restore immutable flag for config.json
chattr +i "$CONFIG_DIR/config.json" 2>/dev/null || true

# Installation complete
echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ✓ Installation Complete!                             ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BLUE}Box Information:${NC}"
echo -e "  Box ID:       ${GREEN}$BOX_ID${NC}"
echo -e "  Install Path: ${GREEN}$INSTALL_DIR${NC}"
echo ""

echo -e "${BLUE}Next Steps:${NC}"
echo ""
echo -e "${YELLOW}1.${NC} Activate your license (if you haven't already):"
echo -e "   ${GREEN}glowf1sh-license activate YOUR-LICENSE-KEY${NC}"
echo ""
echo -e "${YELLOW}2.${NC} Check license validator status:"
echo -e "   ${GREEN}systemctl status glowf1sh-license-validator.timer${NC}"
echo ""
echo -e "${YELLOW}3.${NC} Check license status:"
echo -e "   ${GREEN}glowf1sh-license status${NC}"
echo ""
echo -e "${YELLOW}4.${NC} View service status:"
echo -e "   ${GREEN}sudo systemctl status glowf1sh-license-validator.timer${NC}"
echo ""

echo -e "${GREEN}For more information, visit: https://github.com/${GITHUB_REPO}${NC}"
echo -e "${GREEN}Support: https://twitch.tv/glowf1sh${NC}"
echo ""
