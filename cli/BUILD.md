# Build Instructions - glowf1sh-license CLI

## Build

```bash
cd /test/dev/glowf1sh-remote/cli/
bash build.sh
```

## Binary Info

**Target:** ARM64 (OrangePi 5B+)
**Output:** `glowf1sh-license` (4.8MB)
**SHA256:** `8d32552c20d32449b01defbbfe3c85f5eb1ff530a3a5021c5d83f199d1975ce8`

## Commands

- `glowf1sh-license activate <key>` - Aktivierung
- `glowf1sh-license status` - Status anzeigen
- `glowf1sh-license features` - Features auflisten
- `glowf1sh-license rebind-hardware` - Hardware rebinden (30-Tage-Limit)
- `glowf1sh-license help` - Hilfe

## Integration in install.sh

Die Binary wird als Base64 in install.sh embedded mit SHA256-Checksum-Validierung.

## Testing

Alle Commands getestet ✓
- help: ✓
- status: ✓
- features: ✓
- rebind-hardware: ✓

## Dependencies

- Go 1.18+
- github.com/spf13/cobra
- github.com/golang-jwt/jwt/v4
- github.com/fatih/color
