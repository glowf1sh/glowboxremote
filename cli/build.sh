#!/bin/bash
set -e

cd "$(dirname "$0")/src"

echo "===================================="
echo "Building glowf1sh-license CLI"
echo "===================================="
echo ""

# Build für ARM64 (OrangePi 5B+)
echo "→ Building for linux/arm64..."
GOOS=linux GOARCH=arm64 go build -ldflags="-s -w" -o ../glowf1sh-license

chmod +x ../glowf1sh-license

echo "✓ Built: ../glowf1sh-license"
echo ""

# Infos anzeigen
echo "===================================="
echo "Build Summary:"
echo "===================================="
ls -lh ../glowf1sh-license
file ../glowf1sh-license
echo ""
echo "SHA256 Checksum:"
sha256sum ../glowf1sh-license
echo "===================================="
