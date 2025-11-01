#!/usr/bin/env python3
"""
Glowf1sh License Validator - Dead Man's Switch
Runs every 30 minutes via systemd timer
Validates license, renews JWT token, checks for tampering
"""

import json
import sys
import hashlib
import requests
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
CONFIG_DIR = Path("/opt/glowf1sh-remote/config")
CONFIG_FILE = CONFIG_DIR / "config.json"
LICENSE_FILE = CONFIG_DIR / "license.json"
LICENSE_API_URL = "https://license.gl0w.bot/api"

# Client Headers for API Authentication
CLIENT_HEADERS = {
    "X-Client-Type": "glowfish-license-client",
    "X-Client-Auth": "glowfish-client-v1-production-key-2025",
    "X-Client-Version": "1.0.0",
    "Content-Type": "application/json"
}


def calculate_sha256(file_path):
    """Calculate SHA256 checksum of a file"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def load_json_file(file_path):
    """Load and parse JSON file"""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {file_path}: {e}", file=sys.stderr)
        return None


def save_json_file(file_path, data):
    """Save data to JSON file"""
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving {file_path}: {e}", file=sys.stderr)
        return False


def report_tampering(box_id, hardware_id, reason):
    """Report tampering to license server"""
    try:
        response = requests.post(
            f"{LICENSE_API_URL}/box/report-tampering",
            json={
                "box_id": box_id,
                "hardware_id": hardware_id,
                "reason": reason,
                "timestamp": datetime.now().isoformat()
            },
            headers=CLIENT_HEADERS,
            timeout=10
        )

        if response.status_code == 200:
            print(f"Tampering reported successfully: {reason}")
        else:
            print(f"Failed to report tampering: {response.status_code}", file=sys.stderr)
    except Exception as e:
        print(f"Error reporting tampering: {e}", file=sys.stderr)


def renew_license(box_id, jwt_token):
    """Renew license via heartbeat to server"""
    try:
        response = requests.post(
            f"{LICENSE_API_URL}/box/renew",
            json={
                "box_id": box_id,
                "token": jwt_token
            },
            headers=CLIENT_HEADERS,
            timeout=10
        )

        if response.status_code == 200:
            return response.json()
        else:
            print(f"License renewal failed: {response.status_code}", file=sys.stderr)
            return None
    except Exception as e:
        print(f"Error renewing license: {e}", file=sys.stderr)
        return None


def validate():
    """Main validation logic"""

    # Load config.json
    config = load_json_file(CONFIG_FILE)
    if not config:
        print("Failed to load config.json", file=sys.stderr)
        sys.exit(1)

    box_id = config.get("box_id")
    hardware_id = config.get("hardware_id")

    if not box_id or not hardware_id:
        print("Invalid config.json - missing box_id or hardware_id", file=sys.stderr)
        sys.exit(1)

    # Validate hardware_id against actual machine-id (anti-tampering)
    try:
        with open('/etc/machine-id', 'r') as f:
            machine_id = f.read().strip()
        hardware_id_actual = hashlib.sha256(machine_id.encode()).hexdigest()

        if hardware_id != hardware_id_actual:
            print(f"TAMPERING DETECTED: Hardware ID mismatch!", file=sys.stderr)
            print(f"Config says: {hardware_id[:16]}...", file=sys.stderr)
            print(f"Actual:      {hardware_id_actual[:16]}...", file=sys.stderr)
            report_tampering(box_id, hardware_id,
                           "Hardware ID mismatch - config.json copied to different hardware")
            sys.exit(1)
    except Exception as e:
        print(f"Error validating hardware ID: {e}", file=sys.stderr)
        sys.exit(1)

    # Load license.json
    license_data = load_json_file(LICENSE_FILE)
    if not license_data:
        print("Failed to load license.json", file=sys.stderr)
        sys.exit(1)

    # Calculate current config.json checksum
    current_checksum = calculate_sha256(CONFIG_FILE)
    stored_checksum = license_data.get("config_checksum", "")

    # Check for tampering
    if stored_checksum and current_checksum != stored_checksum:
        print(f"TAMPERING DETECTED: config.json checksum mismatch!", file=sys.stderr)
        print(f"Expected: {stored_checksum}", file=sys.stderr)
        print(f"Current:  {current_checksum}", file=sys.stderr)

        # Report tampering
        report_tampering(box_id, hardware_id, f"config.json checksum mismatch: {current_checksum}")

        # Mark license as inactive
        license_data["status"] = "inactive"
        license_data["last_validated"] = datetime.now().isoformat()
        save_json_file(LICENSE_FILE, license_data)

        sys.exit(1)

    # Check grace period
    last_validated = license_data.get("last_validated")
    grace_period_hours = license_data.get("grace_period_hours", 24)

    if last_validated:
        try:
            last_validated_dt = datetime.fromisoformat(last_validated.replace('Z', '+00:00'))
            grace_period = timedelta(hours=grace_period_hours)

            if datetime.now() - last_validated_dt.replace(tzinfo=None) > grace_period:
                print(f"Grace period expired ({grace_period_hours}h)", file=sys.stderr)
                license_data["status"] = "inactive"
                save_json_file(LICENSE_FILE, license_data)
                sys.exit(1)
        except Exception as e:
            print(f"Error parsing last_validated: {e}", file=sys.stderr)

    # Renew license (heartbeat)
    jwt_token = license_data.get("jwt_token", "")
    if not jwt_token:
        print("No JWT token found in license.json", file=sys.stderr)
        sys.exit(1)

    renewal_response = renew_license(box_id, jwt_token)

    if renewal_response:
        # Update license.json with fresh data
        license_data["status"] = renewal_response.get("status", "active")
        license_data["jwt_token"] = renewal_response.get("token", jwt_token)
        license_data["tier"] = renewal_response.get("tier", license_data.get("tier", "free"))
        license_data["features"] = renewal_response.get("features", license_data.get("features", []))
        license_data["last_validated"] = datetime.now().isoformat()
        license_data["config_checksum"] = current_checksum

        if save_json_file(LICENSE_FILE, license_data):
            print(f"License renewed successfully - Status: {license_data['status']}, Tier: {license_data['tier']}")
        else:
            print("Failed to save updated license.json", file=sys.stderr)
            sys.exit(1)
    else:
        print("License renewal failed - keeping current state", file=sys.stderr)
        # Update last attempt timestamp but keep grace period active
        license_data["last_validated"] = datetime.now().isoformat()
        save_json_file(LICENSE_FILE, license_data)
        sys.exit(1)


if __name__ == "__main__":
    try:
        validate()
    except Exception as e:
        print(f"Validator crashed: {e}", file=sys.stderr)
        sys.exit(1)
