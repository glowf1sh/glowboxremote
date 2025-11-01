#!/usr/bin/env python3
"""
License Client - RIST Add-on License Validation
Validates RIST add-on license with online/offline support.

Features:
- Online license validation
- Offline grace period (7 days)
- License caching
- Periodic heartbeat validation
- Feature unlock mechanism
"""

import json
import logging
import requests
import threading
import time
import hashlib
import uuid
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime, timedelta
from enum import Enum


logger = logging.getLogger(__name__)


class LicenseStatus(Enum):
    """License validation status"""
    VALID = "valid"
    INVALID = "invalid"
    EXPIRED = "expired"
    GRACE_PERIOD = "grace_period"
    NOT_FOUND = "not_found"
    NETWORK_ERROR = "network_error"


class LicenseFeature(Enum):
    """Available licensed features"""
    RIST_BASIC = "rist_basic"
    RIST_BONDING = "rist_bonding"
    RIST_ADAPTIVE = "rist_adaptive"
    RIST_4K = "rist_4k"


@dataclass
class LicenseInfo:
    """License information"""
    license_key: str
    status: LicenseStatus
    features: List[str]
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    expires_at: Optional[str] = None  # ISO format
    last_validated: Optional[str] = None  # ISO format
    grace_period_until: Optional[str] = None  # ISO format
    device_id: Optional[str] = None


class LicenseClient:
    """
    License validation client for RIST add-on.

    Validates license with cloud server and manages offline grace period.
    """

    def __init__(
        self,
        license_server_url: str = "https://license.belabox.net/api/v1",
        cache_path: str = "/opt/belaUI/license_cache.json",
        grace_period_days: int = 7,
        heartbeat_interval: int = 3600,  # 1 hour
        timeout: int = 10  # seconds
    ):
        """
        Initialize license client.

        Args:
            license_server_url: License server base URL
            cache_path: Path to license cache file
            grace_period_days: Days of offline grace period
            heartbeat_interval: Interval between heartbeat validations (seconds)
            timeout: HTTP request timeout (seconds)
        """
        self.license_server_url = license_server_url.rstrip('/')
        self.cache_path = Path(cache_path)
        self.grace_period_days = grace_period_days
        self.heartbeat_interval = heartbeat_interval
        self.timeout = timeout

        # State
        self.license_info: Optional[LicenseInfo] = None
        self.device_id = self._get_or_create_device_id()
        self._lock = threading.RLock()

        # Heartbeat thread
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Load cached license
        self._load_cache()

    def _get_or_create_device_id(self) -> str:
        """Get or create unique device identifier"""
        device_id_file = Path("/opt/belaUI/device_id")

        if device_id_file.exists():
            try:
                with open(device_id_file, 'r') as f:
                    device_id = f.read().strip()
                    if device_id:
                        return device_id
            except:
                pass

        # Generate new device ID based on machine-id or UUID
        try:
            # Try to use machine-id (Linux)
            with open('/etc/machine-id', 'r') as f:
                machine_id = f.read().strip()
                device_id = hashlib.sha256(machine_id.encode()).hexdigest()[:32]
        except:
            # Fallback to random UUID
            device_id = str(uuid.uuid4()).replace('-', '')

        # Save device ID
        try:
            device_id_file.parent.mkdir(parents=True, exist_ok=True)
            with open(device_id_file, 'w') as f:
                f.write(device_id)
        except Exception as e:
            logger.warning(f"Failed to save device ID: {e}")

        return device_id

    def validate_license(self, license_key: str, force_online: bool = False) -> LicenseInfo:
        """
        Validate license key.

        Args:
            license_key: License key to validate
            force_online: Force online validation even if cache is valid

        Returns:
            LicenseInfo object with validation result
        """
        with self._lock:
            # Check cache first (if not forcing online)
            if not force_online and self.license_info and self.license_info.license_key == license_key:
                if self._is_cache_valid():
                    logger.info("Using cached license (valid)")
                    return self.license_info

            # Try online validation
            try:
                license_info = self._validate_online(license_key)

                # Cache successful validation
                self.license_info = license_info
                self._save_cache()

                logger.info(f"License validated online: {license_info.status.value}")
                return license_info

            except requests.exceptions.RequestException as e:
                logger.warning(f"Online validation failed: {e}")

                # Check if we can use grace period
                if self.license_info and self.license_info.license_key == license_key:
                    grace_info = self._check_grace_period()
                    if grace_info:
                        logger.warning(f"Using grace period (until {grace_info.grace_period_until})")
                        return grace_info

                # No cache and no connection
                return LicenseInfo(
                    license_key=license_key,
                    status=LicenseStatus.NETWORK_ERROR,
                    features=[],
                    device_id=self.device_id
                )

    def _validate_online(self, license_key: str) -> LicenseInfo:
        """
        Perform online license validation.

        Args:
            license_key: License key to validate

        Returns:
            LicenseInfo with validation result

        Raises:
            requests.exceptions.RequestException: On network error
        """
        endpoint = f"{self.license_server_url}/validate"

        payload = {
            "license_key": license_key,
            "device_id": self.device_id,
            "product": "belabox_rist_addon",
            "version": "1.0.0"
        }

        response = requests.post(
            endpoint,
            json=payload,
            timeout=self.timeout,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            data = response.json()

            if data.get("valid", False):
                return LicenseInfo(
                    license_key=license_key,
                    status=LicenseStatus.VALID,
                    features=data.get("features", []),
                    customer_id=data.get("customer_id"),
                    customer_name=data.get("customer_name"),
                    expires_at=data.get("expires_at"),
                    last_validated=datetime.utcnow().isoformat(),
                    device_id=self.device_id
                )
            else:
                reason = data.get("reason", "unknown")
                if "expired" in reason.lower():
                    status = LicenseStatus.EXPIRED
                else:
                    status = LicenseStatus.INVALID

                return LicenseInfo(
                    license_key=license_key,
                    status=status,
                    features=[],
                    device_id=self.device_id,
                    last_validated=datetime.utcnow().isoformat()
                )

        elif response.status_code == 404:
            return LicenseInfo(
                license_key=license_key,
                status=LicenseStatus.NOT_FOUND,
                features=[],
                device_id=self.device_id,
                last_validated=datetime.utcnow().isoformat()
            )

        else:
            # Server error
            response.raise_for_status()

    def _is_cache_valid(self) -> bool:
        """Check if cached license is still valid"""
        if not self.license_info:
            return False

        if self.license_info.status != LicenseStatus.VALID:
            return False

        # Check if last validation was recent (within heartbeat interval)
        if self.license_info.last_validated:
            try:
                last_validated = datetime.fromisoformat(self.license_info.last_validated)
                age = datetime.utcnow() - last_validated

                if age.total_seconds() < self.heartbeat_interval:
                    return True
            except:
                pass

        return False

    def _check_grace_period(self) -> Optional[LicenseInfo]:
        """
        Check if license is in grace period.

        Returns:
            LicenseInfo with grace period status or None
        """
        if not self.license_info:
            return None

        if not self.license_info.last_validated:
            return None

        try:
            last_validated = datetime.fromisoformat(self.license_info.last_validated)
            grace_period_until = last_validated + timedelta(days=self.grace_period_days)

            if datetime.utcnow() < grace_period_until:
                # Still in grace period
                grace_info = LicenseInfo(
                    license_key=self.license_info.license_key,
                    status=LicenseStatus.GRACE_PERIOD,
                    features=self.license_info.features,
                    customer_id=self.license_info.customer_id,
                    customer_name=self.license_info.customer_name,
                    expires_at=self.license_info.expires_at,
                    last_validated=self.license_info.last_validated,
                    grace_period_until=grace_period_until.isoformat(),
                    device_id=self.device_id
                )
                return grace_info

        except Exception as e:
            logger.error(f"Grace period check failed: {e}")

        return None

    def has_feature(self, feature: LicenseFeature) -> bool:
        """
        Check if a specific feature is licensed.

        Args:
            feature: Feature to check

        Returns:
            True if feature is available
        """
        with self._lock:
            if not self.license_info:
                return False

            if self.license_info.status not in [LicenseStatus.VALID, LicenseStatus.GRACE_PERIOD]:
                return False

            return feature.value in self.license_info.features

    def get_license_info(self) -> Optional[LicenseInfo]:
        """Get current license information"""
        with self._lock:
            return self.license_info

    def start_heartbeat(self) -> bool:
        """
        Start periodic license validation heartbeat.

        Returns:
            True if started successfully
        """
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            logger.warning("Heartbeat already running")
            return False

        if not self.license_info:
            logger.error("No license to validate")
            return False

        logger.info(f"Starting license heartbeat (interval: {self.heartbeat_interval}s)")
        self._stop_event.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="LicenseHeartbeat"
        )
        self._heartbeat_thread.start()

        return True

    def stop_heartbeat(self) -> None:
        """Stop heartbeat validation"""
        if not self._heartbeat_thread or not self._heartbeat_thread.is_alive():
            logger.warning("Heartbeat not running")
            return

        logger.info("Stopping license heartbeat...")
        self._stop_event.set()

        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=10.0)
            self._heartbeat_thread = None

        logger.info("License heartbeat stopped")

    def _heartbeat_loop(self) -> None:
        """Periodic license validation loop"""
        while not self._stop_event.is_set():
            try:
                if self.license_info:
                    # Re-validate license
                    updated_info = self.validate_license(
                        self.license_info.license_key,
                        force_online=True
                    )

                    if updated_info.status != self.license_info.status:
                        logger.warning(
                            f"License status changed: "
                            f"{self.license_info.status.value} -> {updated_info.status.value}"
                        )

            except Exception as e:
                logger.error(f"Heartbeat validation error: {e}", exc_info=True)

            # Wait for next interval
            self._stop_event.wait(self.heartbeat_interval)

    def _save_cache(self) -> None:
        """Save license to cache file"""
        if not self.license_info:
            return

        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)

            cache_data = asdict(self.license_info)
            cache_data['status'] = self.license_info.status.value

            with open(self.cache_path, 'w') as f:
                json.dump(cache_data, f, indent=2)

            logger.debug(f"License cached to {self.cache_path}")

        except Exception as e:
            logger.error(f"Failed to save license cache: {e}")

    def _load_cache(self) -> None:
        """Load license from cache file"""
        if not self.cache_path.exists():
            return

        try:
            with open(self.cache_path, 'r') as f:
                cache_data = json.load(f)

            cache_data['status'] = LicenseStatus(cache_data['status'])

            self.license_info = LicenseInfo(**cache_data)
            logger.info(f"License loaded from cache: {self.license_info.status.value}")

        except Exception as e:
            logger.warning(f"Failed to load license cache: {e}")


# Example usage
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create license client
    client = LicenseClient(
        license_server_url="https://license.belabox.net/api/v1",
        cache_path="/tmp/license_cache.json",
        grace_period_days=7,
        heartbeat_interval=10  # 10 seconds for testing
    )

    print(f"Device ID: {client.device_id}\n")

    # Test license key (example format)
    test_license_key = "RIST-XXXX-XXXX-XXXX-XXXX"

    print(f"Validating license: {test_license_key}")
    license_info = client.validate_license(test_license_key)

    print(f"\nLicense Status: {license_info.status.value}")
    print(f"Features: {license_info.features}")

    if license_info.customer_name:
        print(f"Customer: {license_info.customer_name}")

    if license_info.expires_at:
        print(f"Expires: {license_info.expires_at}")

    if license_info.grace_period_until:
        print(f"Grace Period Until: {license_info.grace_period_until}")

    # Check features
    print("\nFeature Checks:")
    for feature in LicenseFeature:
        has_it = client.has_feature(feature)
        status_symbol = "✓" if has_it else "✗"
        print(f"  {status_symbol} {feature.value}")

    # Start heartbeat
    if license_info.status in [LicenseStatus.VALID, LicenseStatus.GRACE_PERIOD]:
        print("\nStarting heartbeat validation...")
        client.start_heartbeat()

        try:
            print("Heartbeat running. Press Ctrl+C to stop.\n")
            while True:
                time.sleep(5)

                # Show current status
                info = client.get_license_info()
                if info:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                          f"License: {info.status.value}, "
                          f"Features: {len(info.features)}")

        except KeyboardInterrupt:
            print("\n\nStopping...")
            client.stop_heartbeat()
    else:
        print(f"\nCannot start heartbeat: license status is {license_info.status.value}")
