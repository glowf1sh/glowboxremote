# glowf1sh-license Binary Analysis Report

**Date:** 2025-10-29
**Binary:** `/test/dev/glowf1sh-remote/cli/glowf1sh-license`
**Purpose:** Reverse-Engineering für 1:1 Go Neu-Implementierung

---

## Binary Info

**File type:** ELF 64-bit LSB executable, ARM aarch64, version 1 (SYSV), dynamically linked
**Architecture:** ARM aarch64 (ARM64)
**Size:** 6.3 MB (6503694 bytes)
**Build Info:** Go BuildID=5mIbzeJIUNKgefC3QklF/n_VM1ryH35Ng4ixTj8_A/QqWi-vRYn21nq3DaSW2J/_MTNHOrWabBpjeyyMfCl
**Stripped:** No (debug symbols included)
**Interpreter:** /lib/ld-linux-aarch64.so.1

**Dependencies:**
- linux-vdso.so.1 (virtual library)
- libc.so.6 (/lib/aarch64-linux-gnu/libc.so.6)
- /lib/ld-linux-aarch64.so.1 (dynamic linker)

---

## Commands

### command: status
```
Usage: glowf1sh-license status
Help text: Show box status, license tier, and feature flags
```

**Output format:**
```
╔════════════════════════════════════════╗
║      Glowf1sh Box Status Report        ║
╚════════════════════════════════════════╝

Box ID:        gfbox-rasalhague-887
Status:        ✓ active
License Tier:  ■ premium
Last Updated:  2025-10-29T13:14:56+01:00

Enabled Features:
  (none)
```

---

### command: activate <license-key>
```
Usage: glowf1sh-license activate <license-key>
Help text: Activate box with a license key
```

**Behavior:**
- Requires one argument: `<license-key>`
- Error without key: "Error: License key required"
- Error with invalid key: "Error: License server returned 403"

---

### command: features
```
Usage: glowf1sh-license features
Help text: List all available features
```

**Output format:**
```
Enabled Features:
  (none)
```

---

### command: help
```
Usage: glowf1sh-license help
Help text: Show this help message
```

---

## API Integration

### Base URL
```
https://license.gl0w.bot
```

### Endpoints

#### POST /api/box/activate
**Request body fields:**
- `box_id` (string): Unique box identifier (format: gfbox-{name}-{number})
- `hardware_id` (string): Hardware identifier hash
- `license_key` (string): License key provided by user

**Response body (success):**
```json
{
  "status": "active",
  "tier": "premium",
  "token": "<jwt_token>",
  "expires_in": 3600,
  "features": []
}
```

**Response body (error):**
```json
{
  "error": "Invalid or expired license"
}
```

---

### HTTP Headers

**Request headers:**
- `X-Client-Type`: "glowfish-license-client"
- `X-Client-Auth`: "glowfish-client-v1-production-key-2025"
- `X-Client-Version`: "1.0.0"
- `Content-Type`: "application/json"

---

## Configuration

### Config Files

#### /opt/glowf1sh-remote/config/config.json
```json
{
  "box_id": "gfbox-rasalhague-887",
  "hardware_id": "7d90f42cfedb6ee7638fb667f56452a7b823778a257aa46147edbb20aad0708e"
}
```

#### /opt/glowf1sh-remote/config/license.json
```json
{
  "status": "active",
  "jwt_token": "eyJhbGc...",
  "tier": "premium",
  "features": [],
  "last_validated": "2025-10-29T13:14:56+01:00",
  "config_checksum": "abc123...",
  "grace_period_hours": 24
}
```

---

## Box ID Generation

**Format:** `gfbox-{star_name}-{number}`
- Example: `gfbox-rasalhague-887`
- Star names: Astronomical names
- Number: 3-digit (001-999)

---

## Hardware ID Generation

**Source:** `/etc/machine-id`
**Algorithm:** SHA256 hash of machine-id
**Format:** 64-character hex string
**Example:** `7d90f42cfedb6ee7638fb667f56452a7b823778a257aa46147edbb20aad0708e`

---

## UI/UX

### Box-Drawing Characters
- Top: ╔ ═ ╗
- Sides: ║
- Bottom: ╚ ═ ╝

### Status Indicators
- Success: ✓ (green)
- Error: ✗ (red)
- Info: ■

### Colors
- Green: Success states
- Red: Error states
- Cyan: Info/Headers

---

## Error Messages

1. `Error: License key required`
2. `Error: License server returned %d`
3. `Error: Could not save config`
4. `Activating box with license key...`
5. `Run 'glowf1sh-license status' to view license details`

---

## Implementation Notes

### Required Go Packages
- `github.com/spf13/cobra` - CLI framework
- `github.com/fatih/color` - Colored output
- `github.com/golang-jwt/jwt/v5` - JWT handling
- `encoding/json` - JSON marshaling
- `net/http` - HTTP client
- `crypto/sha256` - Hardware ID hashing

### Directory Structure
```
src/
├── main.go
├── go.mod
├── cmd/
│   ├── root.go
│   ├── activate.go
│   ├── status.go
│   ├── features.go
│   └── rebind.go (NEU!)
└── pkg/
    ├── api/client.go
    ├── config/
    │   ├── config.go
    │   └── license.go
    ├── hardware/hardware.go
    └── ui/printer.go
```

---

## Next Steps

1. ✅ Binary analysiert und dokumentiert
2. ⏳ Go-Projekt Setup (Phase 2)
3. ⏳ Core-Module implementieren (Phase 3)
4. ⏳ Commands implementieren (Phase 4)
5. ⏳ rebind-hardware Command hinzufügen (NEU!)
6. ⏳ Server-API Auto-Rebind (Phase 5)
7. ⏳ Build & Test (Phase 6)
8. ⏳ install.sh Integration (Phase 7)
9. ⏳ /publish Command anpassen (Phase 8)
