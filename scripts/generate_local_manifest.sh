#!/bin/bash
# Manifest Generator für bestehende BelaBox Installationen
# Generiert manifest.json basierend auf bereits installierten Dateien

set -e

BASE_DIR="/opt/glowf1sh-remote"
CONFIG_DIR="$BASE_DIR/config"
MANIFEST_FILE="$CONFIG_DIR/manifest.json"

# Farben für Output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Glowf1sh Manifest Generator${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Prüfen ob als root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Fehler: Dieses Script muss als root ausgeführt werden${NC}"
    exit 1
fi

# Prüfen ob Installationsverzeichnis existiert
if [ ! -d "$BASE_DIR" ]; then
    echo -e "${RED}Fehler: $BASE_DIR existiert nicht${NC}"
    exit 1
fi

# Config-Verzeichnis erstellen falls nicht vorhanden
mkdir -p "$CONFIG_DIR"

# Funktion: SHA256 berechnen
calculate_sha256() {
    sha256sum "$1" | awk '{print $1}'
}

# Funktion: Dateigröße ermitteln
get_file_size() {
    stat -c%s "$1"
}

# Funktion: Datei-Permissions ermitteln
get_file_mode() {
    stat -c%a "$1"
}

echo -e "${YELLOW}Scanne Dateien in $BASE_DIR...${NC}"
echo ""

# JSON Manifest erstellen
cat > "$MANIFEST_FILE" << 'EOF_MANIFEST'
{
  "manifest_version": "1.0.0",
  "last_updated": "TIMESTAMP_PLACEHOLDER",
  "installed_at": "TIMESTAMP_PLACEHOLDER",
  "system_requirements": {
    "python": ">=3.9",
    "systemd": true,
    "min_disk_space_mb": 500
  },
  "files": {}
}
EOF_MANIFEST

# Timestamp einfügen
TIMESTAMP=$(date -Iseconds)
sed -i "s/TIMESTAMP_PLACEHOLDER/$TIMESTAMP/g" "$MANIFEST_FILE"

# Dateien scannen und zum Manifest hinzufügen
FILE_COUNT=0

# Funktion: Datei zum Manifest hinzufügen
add_file_to_manifest() {
    local file_path="$1"
    local rel_path="$2"
    local description="$3"
    local version="${4:-1.0.0}"

    if [ ! -f "$file_path" ]; then
        echo -e "  ${YELLOW}⚠${NC}  $rel_path nicht gefunden, überspringe"
        return
    fi

    local sha256=$(calculate_sha256 "$file_path")
    local size=$(get_file_size "$file_path")
    local mode=$(get_file_mode "$file_path")

    # JSON Entry erstellen (manuell weil jq evtl. nicht installiert)
    python3 << EOF
import json
import sys

manifest_path = "$MANIFEST_FILE"
with open(manifest_path, 'r') as f:
    manifest = json.load(f)

manifest['files']['$rel_path'] = {
    'version': '$version',
    'sha256': '$sha256',
    'size': $size,
    'mode': '$mode',
    'description': '$description',
    'installed_at': '$TIMESTAMP'
}

with open(manifest_path, 'w') as f:
    json.dump(manifest, f, indent=2, sort_keys=True)
EOF

    echo -e "  ${GREEN}✓${NC} $rel_path"
    FILE_COUNT=$((FILE_COUNT + 1))
}

# CLI Binary
echo "CLI Tools:"
add_file_to_manifest "$BASE_DIR/cli/glowf1sh-license" "cli/glowf1sh-license" "License management CLI tool"

# BelaBox API Module
echo ""
echo "BelaBox API Module:"
for module in api_server.py belabox_client.py cloud_client.py license-validator.py manifest_handler.py update_handler.py __init__.py; do
    add_file_to_manifest "$BASE_DIR/belabox-api/$module" "belabox-api/$module" "BelaBox API module"
done

# BelaBox API Runtime
echo ""
echo "BelaBox API Runtime:"
add_file_to_manifest "$BASE_DIR/belabox-api/_core/pyarmor_runtime_011004/__init__.py" "belabox-api/_core/pyarmor_runtime_011004/__init__.py" "Runtime module"
add_file_to_manifest "$BASE_DIR/belabox-api/_core/pyarmor_runtime_011004/pyarmor_runtime.so" "belabox-api/_core/pyarmor_runtime_011004/pyarmor_runtime.so" "Runtime library"

# RIST Module
echo ""
echo "RIST Module:"
for module in rist_manager.py adaptive_controller.py license_client.py rist_profiles.py; do
    add_file_to_manifest "$BASE_DIR/rist/$module" "rist/$module" "RIST module"
done

# RIST Runtime
echo ""
echo "RIST Runtime:"
add_file_to_manifest "$BASE_DIR/rist/_core/pyarmor_runtime_011004/__init__.py" "rist/_core/pyarmor_runtime_011004/__init__.py" "Runtime module"
add_file_to_manifest "$BASE_DIR/rist/_core/pyarmor_runtime_011004/pyarmor_runtime.so" "rist/_core/pyarmor_runtime_011004/pyarmor_runtime.so" "Runtime library"

# Systemd Services
echo ""
echo "Systemd Services:"
add_file_to_manifest "/etc/systemd/system/glowf1sh-api-server.service" "systemd/glowf1sh-api-server.service" "API Server Service"
add_file_to_manifest "/etc/systemd/system/glowf1sh-cloud-client.service" "systemd/glowf1sh-cloud-client.service" "Cloud Client Service"
add_file_to_manifest "/etc/systemd/system/glowf1sh-license-validator.service" "systemd/glowf1sh-license-validator.service" "License Validator Service"
add_file_to_manifest "/etc/systemd/system/glowf1sh-license-validator.timer" "systemd/glowf1sh-license-validator.timer" "License Validator Timer"

# Installer Script
echo ""
echo "Installer:"
add_file_to_manifest "$BASE_DIR/install.sh" "install.sh" "Installation script"

# Scripts
echo ""
echo "Scripts:"
add_file_to_manifest "$BASE_DIR/scripts/generate_local_manifest.sh" "scripts/generate_local_manifest.sh" "Manifest generator script"

# Permissions setzen
chmod 644 "$MANIFEST_FILE"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ Manifest erfolgreich erstellt!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Pfad:          ${GREEN}$MANIFEST_FILE${NC}"
echo -e "Dateien:       ${GREEN}$FILE_COUNT${NC}"
echo -e "Version:       ${GREEN}1.0.0${NC}"
echo -e "Erstellt:      ${GREEN}$TIMESTAMP${NC}"
echo ""
echo -e "${YELLOW}Nächste Schritte:${NC}"
echo -e "1. Cloud Client neu starten: ${GREEN}systemctl restart glowf1sh-cloud-client${NC}"
echo -e "2. Manifest wird automatisch an Cloud gesendet"
echo -e "3. In Cloud Dashboard unter 'Details' prüfen"
echo ""
