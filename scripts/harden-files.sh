#!/bin/bash
#
# Glowf1sh File Protection Script
# Hardens config and license files with proper permissions and immutability
#
# Usage: sudo ./harden-files.sh [--revert]
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# File paths
CONFIG_FILE="/opt/glowf1sh-remote/api/config.json"
LICENSE_FILE="/opt/glowf1sh-remote/api/license.json"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}ERROR: This script must be run as root${NC}"
    exit 1
fi

# Function to harden files
harden_files() {
    echo -e "${GREEN}Hardening Glowf1sh License System Files...${NC}"
    echo ""

    # 1. Harden config.json (immutable!)
    if [ -f "$CONFIG_FILE" ]; then
        echo -e "${YELLOW}[1/4]${NC} Hardening config.json..."

        # Remove immutable flag first (in case it's already set)
        chattr -i "$CONFIG_FILE" 2>/dev/null || true

        # Set ownership
        chown root:root "$CONFIG_FILE"

        # Set permissions (read-only for root)
        chmod 400 "$CONFIG_FILE"

        # Make immutable (cannot be modified even by root)
        chattr +i "$CONFIG_FILE"

        echo -e "  ${GREEN}✓${NC} config.json: chmod 400, chattr +i"
    else
        echo -e "  ${RED}✗${NC} config.json not found at $CONFIG_FILE"
    fi

    # 2. Harden license.json (read/write for root, but no immutable)
    if [ -f "$LICENSE_FILE" ]; then
        echo -e "${YELLOW}[2/4]${NC} Hardening license.json..."

        # Remove immutable flag (should not be immutable as validator updates it)
        chattr -i "$LICENSE_FILE" 2>/dev/null || true

        # Set ownership
        chown root:root "$LICENSE_FILE"

        # Set permissions (read/write for root only)
        chmod 600 "$LICENSE_FILE"

        echo -e "  ${GREEN}✓${NC} license.json: chmod 600"
    else
        echo -e "  ${RED}✗${NC} license.json not found at $LICENSE_FILE"
    fi

    # 3. Harden Python modules (read/execute for root)
    echo -e "${YELLOW}[3/4]${NC} Hardening Python modules..."

    MODULES_DIR="/opt/glowf1sh-remote"
    if [ -d "$MODULES_DIR" ]; then
        # Python scripts
        find "$MODULES_DIR" -maxdepth 1 -name "*.py" -type f -exec chown root:root {} \;
        find "$MODULES_DIR" -maxdepth 1 -name "*.py" -type f -exec chmod 500 {} \;

        MODULE_COUNT=$(find "$MODULES_DIR" -maxdepth 1 -name "*.py" -type f | wc -l)
        echo -e "  ${GREEN}✓${NC} Hardened $MODULE_COUNT Python modules (chmod 500)"
    else
        echo -e "  ${RED}✗${NC} Modules directory not found at $MODULES_DIR"
    fi

    # 4. Harden CLI tool
    echo -e "${YELLOW}[4/4]${NC} Hardening CLI tool..."

    CLI_TOOL="/usr/local/bin/glowf1sh-license"
    if [ -f "$CLI_TOOL" ]; then
        chown root:root "$CLI_TOOL"
        chmod 755 "$CLI_TOOL"
        echo -e "  ${GREEN}✓${NC} CLI tool hardened (chmod 755)"
    else
        echo -e "  ${YELLOW}⚠${NC}  CLI tool not found at $CLI_TOOL (may not be installed yet)"
    fi

    echo ""
    echo -e "${GREEN}File hardening complete!${NC}"
    echo ""
    echo -e "${YELLOW}NOTE:${NC} config.json is now immutable. To modify it, you must first run:"
    echo -e "  sudo chattr -i $CONFIG_FILE"
    echo ""
}

# Function to revert hardening
revert_hardening() {
    echo -e "${YELLOW}Reverting file hardening...${NC}"
    echo ""

    # Revert config.json
    if [ -f "$CONFIG_FILE" ]; then
        chattr -i "$CONFIG_FILE" 2>/dev/null || true
        chmod 644 "$CONFIG_FILE"
        echo -e "  ${GREEN}✓${NC} config.json: removed immutable flag, chmod 644"
    fi

    # Revert license.json
    if [ -f "$LICENSE_FILE" ]; then
        chattr -i "$LICENSE_FILE" 2>/dev/null || true
        chmod 644 "$LICENSE_FILE"
        echo -e "  ${GREEN}✓${NC} license.json: chmod 644"
    fi

    # Revert Python modules
    MODULES_DIR="/opt/glowf1sh-remote"
    if [ -d "$MODULES_DIR" ]; then
        find "$MODULES_DIR" -maxdepth 1 -name "*.py" -type f -exec chmod 755 {} \;
        echo -e "  ${GREEN}✓${NC} Python modules: chmod 755"
    fi

    echo ""
    echo -e "${GREEN}File hardening reverted${NC}"
    echo ""
}

# Function to show current status
show_status() {
    echo -e "${GREEN}Current File Status:${NC}"
    echo ""

    if [ -f "$CONFIG_FILE" ]; then
        echo -e "${YELLOW}config.json:${NC}"
        ls -lah "$CONFIG_FILE"
        echo -n "  Immutable: "
        if lsattr "$CONFIG_FILE" 2>/dev/null | grep -q "i"; then
            echo -e "${GREEN}YES${NC}"
        else
            echo -e "${RED}NO${NC}"
        fi
        echo ""
    fi

    if [ -f "$LICENSE_FILE" ]; then
        echo -e "${YELLOW}license.json:${NC}"
        ls -lah "$LICENSE_FILE"
        echo -n "  Immutable: "
        if lsattr "$LICENSE_FILE" 2>/dev/null | grep -q "i"; then
            echo -e "${GREEN}YES${NC}"
        else
            echo -e "${RED}NO${NC}"
        fi
        echo ""
    fi
}

# Main script logic
case "${1:-}" in
    --revert|-r)
        revert_hardening
        ;;
    --status|-s)
        show_status
        ;;
    --help|-h)
        echo "Usage: $0 [OPTIONS]"
        echo ""
        echo "Options:"
        echo "  (none)         Harden files with proper permissions"
        echo "  --revert, -r   Revert hardening (make files editable)"
        echo "  --status, -s   Show current file status"
        echo "  --help, -h     Show this help message"
        echo ""
        ;;
    "")
        harden_files
        ;;
    *)
        echo -e "${RED}ERROR: Unknown option: $1${NC}"
        echo "Run '$0 --help' for usage information"
        exit 1
        ;;
esac

exit 0
