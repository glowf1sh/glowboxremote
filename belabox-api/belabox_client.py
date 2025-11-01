#!/usr/bin/env python3
"""
BelaBox WebSocket Client
Connects to local BelaBox belaUI WebSocket and provides start/stop/config methods
Uses existing auth tokens from BelaBox instead of password
"""

import json
import websocket
import time
import threading
import requests
from typing import Dict, Optional, Any


class BelaBoxClient:
    def __init__(self, auth_token_file: str):
        self.auth_token_file = auth_token_file
        self.auth_token = None
        self.url = "ws://127.0.0.1:80"
        self.ws = None
        self.authenticated = False
        self.last_status = None
        self.last_config = None
        self.last_netif = None
        self.lock = threading.Lock()
        self.keepalive_thread = None
        self.stop_keepalive = threading.Event()
        self.last_status_update = 0  # Track when status was last updated
        self.last_notifications = []  # Store notifications from belaUI.js
        self.rist_errors = []  # Store RIST-specific errors

    def load_auth_token(self) -> bool:
        """Load auth token from BelaBox auth_tokens.json"""
        try:
            with open(self.auth_token_file, 'r') as f:
                tokens = json.load(f)
                # Get first available token
                if tokens:
                    self.auth_token = list(tokens.keys())[0]
                    return True
                else:
                    print("No auth tokens found in file")
                    return False
        except Exception as e:
            print(f"Error loading auth token: {e}")
            return False

    def connect(self) -> bool:
        """Connect to BelaBox WebSocket"""
        try:
            # Connect with initial timeout, then set shorter timeout for recv()
            self.ws = websocket.create_connection(self.url, timeout=10)
            self.ws.settimeout(0.5)  # 500ms timeout for recv() operations
            return True
        except Exception as e:
            print(f"Connection error: {e}")
            return False

    def disconnect(self):
        """Disconnect from WebSocket"""
        # Stop keepalive thread first
        if self.keepalive_thread and self.keepalive_thread.is_alive():
            self.stop_keepalive.set()
            self.keepalive_thread.join(timeout=2)
            self.keepalive_thread = None
            self.stop_keepalive.clear()

        if self.ws:
            try:
                self.ws.close()
            except:
                pass
            self.ws = None
        self.authenticated = False

    def _keepalive_loop(self):
        """Send periodic ping messages to keep connection active for broadcasts"""
        print("[KEEPALIVE] Thread started")
        while not self.stop_keepalive.wait(10):  # Wait 10 seconds between pings
            try:
                if self.ws and self.authenticated:
                    # Send a simple ping message to update lastActive on server
                    ping_msg = json.dumps({"ping": int(time.time() * 1000)})
                    self.ws.send(ping_msg)
                    print(f"[KEEPALIVE] Ping sent at {time.strftime('%H:%M:%S')}")
            except Exception as e:
                print(f"[KEEPALIVE] Error sending ping: {e}")
                # Don't break - keep trying
        print("[KEEPALIVE] Thread stopped")

    def _start_keepalive(self):
        """Start keepalive thread if not already running"""
        if not self.keepalive_thread or not self.keepalive_thread.is_alive():
            self.stop_keepalive.clear()
            self.keepalive_thread = threading.Thread(target=self._keepalive_loop, daemon=True)
            self.keepalive_thread.start()

    def authenticate(self) -> bool:
        """Authenticate with BelaBox using token"""
        if not self.auth_token:
            if not self.load_auth_token():
                return False

        if not self.ws:
            if not self.connect():
                return False

        try:
            # Send auth message with token
            auth_msg = json.dumps({"auth": {"token": self.auth_token}})
            self.ws.send(auth_msg)

            # Wait for auth response and collect initial data
            auth_received = False
            for _ in range(20):  # 20 attempts to get all initial data
                try:
                    response = self.ws.recv()
                    msg = json.loads(response)

                    if "auth" in msg:
                        if msg["auth"].get("success"):
                            self.authenticated = True
                            auth_received = True
                            # Continue reading to get config and status
                        else:
                            print("Authentication failed - token may be invalid")
                            return False

                    # Store status/config/netif updates
                    if "status" in msg:
                        status = msg["status"]
                        if self.last_status is None:
                            self.last_status = status
                        else:
                            self.last_status.update(status)
                    if "config" in msg:
                        self.last_config = msg["config"]
                    if "netif" in msg:
                        netif = msg["netif"]
                        print(f"[DEBUG] netif message received: {list(netif.keys())}")
                        if self.last_netif is None:
                            self.last_netif = netif
                        else:
                            self.last_netif = netif
                        print(f"[DEBUG] last_netif now has: {list(self.last_netif.keys())}")

                    # If we got auth and have both config and status, we're done
                    if auth_received and self.last_config and self.last_status:
                        self._start_keepalive()
                        return True

                except websocket.WebSocketTimeoutException:
                    # If we already authenticated, that's okay
                    if auth_received:
                        self._start_keepalive()
                        return True
                    continue
                except Exception as e:
                    print(f"Auth error: {e}")
                    return False

            # Return true if authenticated, even if we don't have all data yet
            if auth_received:
                self._start_keepalive()
            return auth_received
        except Exception as e:
            print(f"Authentication error: {e}")
            return False

    def send_and_wait_response(self, message: Dict, timeout: int = 10) -> Optional[Dict]:
        """Send message and wait for response"""
        with self.lock:
            try:
                if not self.authenticated:
                    if not self.authenticate():
                        return {"success": False, "error": "Authentication failed"}

                # Send message
                self.ws.send(json.dumps(message))

                # Wait for response and status update
                start_time = time.time()
                while time.time() - start_time < timeout:
                    try:
                        response = self.ws.recv()
                        msg = json.loads(response)

                        # Store updates
                        if "status" in msg:
                            status = msg["status"]
                            if self.last_status is None:
                                self.last_status = status
                            else:
                                self.last_status.update(status)
                        if "config" in msg:
                            self.last_config = msg["config"]
                        if "notification" in msg:
                            # Handle error notifications
                            notif = msg["notification"]
                            if notif.get("type") == "error":
                                return {"success": False, "error": notif.get("message", "Unknown error")}

                    except websocket.WebSocketTimeoutException:
                        time.sleep(0.1)
                        continue
                    except Exception as e:
                        return {"success": False, "error": str(e)}

                return {"success": True}

            except Exception as e:
                self.disconnect()
                return {"success": False, "error": str(e)}

    def start(self) -> Dict:
        """Start streaming"""
        if not self.last_config:
            # Get current config first
            self.get_config()

        if not self.last_config:
            return {"success": False, "error": "Could not retrieve config"}

        # Send start command with current config (no waiting needed - status updates come via cloud WebSocket)
        message = {"start": self.last_config}

        with self.lock:
            try:
                if not self.authenticated:
                    if not self.authenticate():
                        return {"success": False, "error": "Authentication failed"}

                self.ws.send(json.dumps(message))
                return {"success": True}

            except Exception as e:
                self.disconnect()
                return {"success": False, "error": str(e)}

    def stop(self) -> Dict:
        """Stop streaming"""
        message = {"stop": 0}

        with self.lock:
            try:
                if not self.authenticated:
                    if not self.authenticate():
                        return {"success": False, "error": "Authentication failed"}

                self.ws.send(json.dumps(message))
                return {"success": True}

            except Exception as e:
                self.disconnect()
                return {"success": False, "error": str(e)}

    def get_status(self) -> Dict:
        """Get current streaming status"""
        with self.lock:
            try:
                # Check if cached status is stale (>60s old) - force reconnect to get fresh data
                if self.last_status_update > 0 and (time.time() - self.last_status_update) > 60:
                    print(f"[CACHE] Status is stale ({int(time.time() - self.last_status_update)}s old), forcing reconnect...")
                    self.disconnect()
                    self.last_status_update = 0

                if not self.authenticated:
                    if not self.authenticate():
                        return {"success": False, "error": "Authentication failed"}

                # Try reading ALL available messages to refresh cache
                status_updated = False
                try:
                    self.ws.settimeout(0.1)  # Very short timeout
                    while True:  # Read all available messages
                        try:
                            response = self.ws.recv()
                            msg = json.loads(response)

                            # Update cached values
                            if "status" in msg:
                                status = msg["status"]
                                if self.last_status is None:
                                    self.last_status = status
                                else:
                                    self.last_status.update(status)  # MERGE partial updates
                                status_updated = True
                            if "config" in msg:
                                self.last_config = msg["config"]
                            if "netif" in msg:
                                self.last_netif = msg["netif"]  # REPLACE complete object
                                status_updated = True
                            if "notification" in msg:
                                notif = msg["notification"]
                                current_time = time.time()

                                # Handle show/remove notifications
                                if "show" in notif:
                                    # Replace entire list with current state from belaUI
                                    # Update timestamp EVERY time (like belaUI's pn.updated = getms())
                                    # This is critical for duration-based cleanup!
                                    self.last_notifications = [
                                        {**n, 'source': 'belaUI', 'received_at': current_time}
                                        for n in notif["show"]
                                    ]

                                if "remove" in notif:
                                    # Explicit remove
                                    for name in notif["remove"]:
                                        self.last_notifications = [x for x in self.last_notifications if x.get('name') != name]

                        except websocket.WebSocketTimeoutException:
                            break  # No more messages available
                        except json.JSONDecodeError:
                            continue  # Skip malformed messages, try next one

                except Exception as e:
                    # Other errors - continue with cached data
                    pass

                # Update timestamp if we got fresh data
                if status_updated:
                    self.last_status_update = time.time()

                # Check RIST errors if RIST mode is active
                self._update_rist_errors()

                # Duration-based cleanup: Remove expired notifications
                # This mirrors belaUI's _notificationIsLive() behavior
                # Timestamp is updated every time belaUI sends the notification (like pn.updated)
                current_time = time.time()
                cleaned_notifications = []
                for notif in self.last_notifications:
                    duration = notif.get('duration', 0)
                    received_at = notif.get('received_at', current_time)

                    # Keep if: duration=0 (permanent) OR not expired yet
                    if duration == 0 or (current_time - received_at) < duration:
                        cleaned_notifications.append(notif)

                self.last_notifications = cleaned_notifications

                # Merge all notifications (belaUI + RIST)
                all_notifications = self.last_notifications + self.rist_errors

                # Return cached status
                if self.last_status is not None:
                    return {
                        "success": True,
                        "is_streaming": self.last_status.get("is_streaming", False),
                        "status": self.last_status,
                        "netif": self.last_netif or {},
                        "notifications": all_notifications,
                        "streaming_mode": self._get_active_mode()
                    }

                return {"success": False, "error": "No status available"}

            except Exception as e:
                self.disconnect()
                return {"success": False, "error": str(e)}

    def get_config(self) -> Dict:
        """Get current configuration"""
        with self.lock:
            try:
                if not self.authenticated:
                    if not self.authenticate():
                        return {"success": False, "error": "Authentication failed"}

                # IMPORTANT: Actively refresh config from WebSocket
                # Read multiple messages to get latest config update
                try:
                    for _ in range(10):  # Try reading 10 messages to find updates
                        response = self.ws.recv()
                        msg = json.loads(response)

                        # Update cached status/config/netif if present
                        # Only update last_status if is_streaming field is present (full status)
                        if "status" in msg:
                            status = msg["status"]
                            if "is_streaming" in status:
                                self.last_status = status
                        if "config" in msg:
                            self.last_config = msg["config"]
                        if "netif" in msg:
                            netif = msg["netif"]
                            if self.last_netif is None:
                                self.last_netif = netif
                            else:
                                self.last_netif = netif

                except websocket.WebSocketTimeoutException:
                    # Timeout is okay - we use whatever we have cached
                    pass
                except Exception as e:
                    # Other errors - continue with cached data
                    print(f"Warning during config refresh: {e}")

                # Return cached config (now refreshed)
                if self.last_config is not None:
                    return {
                        "success": True,
                        "config": self.last_config
                    }

                return {"success": False, "error": "No config available"}

            except Exception as e:
                self.disconnect()
                return {"success": False, "error": str(e)}

    def update_config(self, config_updates: Dict) -> Dict:
        """Update configuration"""
        try:
            if not self.authenticated:
                if not self.authenticate():
                    return {"success": False, "error": "Authentication failed"}

            # Get current config and streaming status
            if not self.last_config:
                self.get_config()

            if not self.last_config:
                return {"success": False, "error": "Could not retrieve current config"}

            # Get current streaming status
            status = self.get_status()
            is_streaming = status.get('is_streaming', False) if status.get('success') else False

            # Merge updates with current config
            new_config = self.last_config.copy()
            new_config.update(config_updates)

            # IMPORTANT: Use different WebSocket message for bitrate updates
            # If only max_br is being updated, use special bitrate message
            # This triggers belaUI's setBitrate() which updates files and sends SIGHUP to belacoder
            if 'max_br' in config_updates and len(config_updates) == 1:
                # Use bitrate-specific message (works during stream AND when stopped)
                message = {"bitrate": {"max_br": config_updates['max_br']}}
                print(f"Sending bitrate update: {config_updates['max_br']} kbps")
            else:
                # Use normal config message for other settings
                message = {"config": new_config}

            result = self.send_and_wait_response(message)

            # IMPORTANT: ALWAYS save config to disk, even if WebSocket failed!
            # This ensures config changes are persistent even when WebSocket is down
            # (can happen after belaUI restart)
            try:
                self._save_config_to_disk(new_config)
                print(f"✅ Config saved to disk (WebSocket success: {result.get('success')})")
            except Exception as e:
                print(f"❌ Error saving config to disk: {e}")
                # If WebSocket failed AND disk save failed, return error
                if not result.get("success"):
                    return {"success": False, "error": f"WebSocket and disk save both failed: {e}"}

            # Update local config cache on success
            if result.get("success"):
                self.last_config = new_config
            else:
                # WebSocket failed but config is on disk - return partial success
                print(f"⚠️ WebSocket failed but config saved to disk (will be loaded after belaUI restart)")
                return {"success": True, "message": "Config saved to disk (belaUI restart scheduled)"}

            return result

        except Exception as e:
            self.disconnect()
            return {"success": False, "error": str(e)}

    def _save_config_to_disk(self, config: Dict):
        """Save configuration to /opt/belaUI/config.json and trigger reload"""
        config_file = '/opt/belaUI/config.json'
        backup_file = '/opt/belaUI/config.json.backup'
        bitrate_file = '/tmp/belacoder_br'

        try:
            # Read current file to preserve sensitive fields
            with open(config_file, 'r') as f:
                current_config = json.load(f)

            # Preserve sensitive fields
            sensitive_fields = ['password_hash', 'ssh_pass_hash', 'ssh_pass']
            for field in sensitive_fields:
                if field in current_config:
                    config[field] = current_config[field]

            # Create backup
            import shutil
            shutil.copy2(config_file, backup_file)

            # Write new config atomically (write to temp, then rename)
            temp_file = config_file + '.tmp'
            with open(temp_file, 'w') as f:
                json.dump(config, f)

            # Atomic rename
            import os
            os.rename(temp_file, config_file)

            print(f"Config saved to disk: {config_file}")

            # Update bitrate file for belacoder (if max_br changed)
            if 'max_br' in config:
                try:
                    min_bitrate = 300  # kbps
                    max_bitrate = config['max_br']  # kbps

                    # Write bitrate file (values in bps, not kbps)
                    with open(bitrate_file, 'w') as f:
                        f.write(f"{min_bitrate * 1000}\n")
                        f.write(f"{max_bitrate * 1000}\n")

                    print(f"Bitrate file updated: {bitrate_file} ({max_bitrate} kbps)")

                    # Send SIGHUP to belacoder to reload bitrate (if running)
                    import subprocess
                    result = subprocess.run(['pgrep', 'belacoder'],
                                          capture_output=True, text=True)
                    if result.returncode == 0:
                        subprocess.run(['killall', '-HUP', 'belacoder'])
                        print("Sent SIGHUP to belacoder (bitrate reload)")

                except Exception as e:
                    print(f"Warning: Could not update bitrate file: {e}")

            # Restart belaUI to load new config (only if stream is not active)
            try:
                import subprocess

                # Check if stream is active
                is_streaming = False
                if self.last_status is not None:
                    is_streaming = self.last_status.get('is_streaming', False)

                if not is_streaming:
                    # Stream is not active, safe to restart belaUI
                    import sys
                    sys.stderr.write("[belabox_client] Restarting belaUI to load new configuration...\n")
                    sys.stderr.flush()
                    result = subprocess.run(['systemctl', 'restart', 'belaUI'],
                                          capture_output=True, text=True, timeout=10)
                    if result.returncode == 0:
                        sys.stderr.write("[belabox_client] ✅ BelaUI restarted successfully\n")
                        sys.stderr.flush()

                        # IMPORTANT: WebSocket reconnect after belaUI restart!
                        # belaUI restart closes the WebSocket, we need to reconnect
                        sys.stderr.write("[belabox_client] Disconnecting old WebSocket...\n")
                        sys.stderr.flush()
                        self.disconnect()

                        # Wait for belaUI to be ready
                        import time
                        time.sleep(2)

                        # Reconnect
                        sys.stderr.write("[belabox_client] Reconnecting to belaUI...\n")
                        sys.stderr.flush()
                        if self.authenticate():
                            sys.stderr.write("[belabox_client] ✅ Reconnected successfully\n")
                            sys.stderr.flush()
                        else:
                            sys.stderr.write("[belabox_client] ⚠️ Reconnect failed (will retry on next request)\n")
                            sys.stderr.flush()
                    else:
                        sys.stderr.write(f"[belabox_client] ⚠️ BelaUI restart failed: {result.stderr}\n")
                        sys.stderr.flush()
                else:
                    print("⚠️ Stream is active, skipping belaUI restart (config on disk only)")

            except Exception as e:
                print(f"Warning: Could not restart belaUI: {e}")

        except Exception as e:
            print(f"Error saving config to disk: {e}")
            raise

    def save_rist_config(self, rist_config: Dict) -> Dict:
        """Save RIST configuration to /opt/glowf1sh_belabox_rist/config.json"""
        config_file = '/opt/glowf1sh_belabox_rist/config.json'
        backup_file = '/opt/glowf1sh_belabox_rist/config.json.backup'

        try:
            import os
            import shutil

            # Ensure directory exists
            os.makedirs(os.path.dirname(config_file), exist_ok=True)

            # Create backup if file exists
            if os.path.exists(config_file):
                shutil.copy2(config_file, backup_file)

            # Write new config atomically
            temp_file = config_file + '.tmp'
            with open(temp_file, 'w') as f:
                json.dump(rist_config, f, indent=2)

            os.rename(temp_file, config_file)

            print(f"✅ RIST config saved to: {config_file}")
            return {"success": True, "message": "RIST configuration saved"}

        except Exception as e:
            error_msg = f"Error saving RIST config: {e}"
            print(f"❌ {error_msg}")
            return {"success": False, "error": error_msg}

    def check_updates(self) -> Dict:
        """Check for available system updates"""
        try:
            import subprocess

            # Update package list first
            print("Updating package list...")
            subprocess.run(['apt-get', 'update'],
                         capture_output=True,
                         check=True,
                         timeout=120)

            # Check for upgradable packages
            result = subprocess.run(['apt', 'list', '--upgradable'],
                                  capture_output=True,
                                  text=True,
                                  timeout=30)

            if result.returncode == 0:
                # Parse output to count updates
                lines = result.stdout.strip().split('\n')
                # First line is header "Listing...", skip it
                updates = [line for line in lines[1:] if line.strip()]
                num_updates = len(updates)

                return {
                    "success": True,
                    "num_updates": num_updates,
                    "updates": updates[:20]  # Return first 20 for preview
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to check updates"
                }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Update check timed out"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Update check error: {str(e)}"
            }

    def apt_update(self) -> Dict:
        """Run apt-get update"""
        try:
            import subprocess

            print("Running apt-get update...")
            result = subprocess.run(['apt-get', 'update'],
                                  capture_output=True,
                                  text=True,
                                  timeout=180)

            if result.returncode == 0:
                return {
                    "success": True,
                    "message": "Package list updated successfully",
                    "output": result.stdout
                }
            else:
                return {
                    "success": False,
                    "error": "apt-get update failed",
                    "output": result.stderr
                }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "apt-get update timed out after 3 minutes"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"apt-get update error: {str(e)}"
            }

    def apt_upgrade(self, auto_yes: bool = True) -> Dict:
        """Run apt-get upgrade"""
        try:
            import subprocess

            print("Running apt-get upgrade...")
            cmd = ['apt-get', 'upgrade']
            if auto_yes:
                cmd.append('-y')

            # Set DEBIAN_FRONTEND=noninteractive to avoid prompts
            env = {'DEBIAN_FRONTEND': 'noninteractive'}

            result = subprocess.run(cmd,
                                  capture_output=True,
                                  text=True,
                                  env=env,
                                  timeout=600)  # 10 minutes timeout

            if result.returncode == 0:
                return {
                    "success": True,
                    "message": "System upgraded successfully",
                    "output": result.stdout
                }
            else:
                return {
                    "success": False,
                    "error": "apt-get upgrade failed",
                    "output": result.stderr
                }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "apt-get upgrade timed out after 10 minutes"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"apt-get upgrade error: {str(e)}"
            }

    def get_details(self) -> Dict:
        """Get detailed box information including network interfaces and modems"""
        with self.lock:
            try:
                if not self.authenticated:
                    if not self.authenticate():
                        return {"success": False, "error": "Authentication failed"}

                # Refresh status and config from WebSocket
                try:
                    for _ in range(10):
                        response = self.ws.recv()
                        msg = json.loads(response)

                        # Update cached status/config if present
                        if "status" in msg:
                            status = msg["status"]
                            if "is_streaming" in status:
                                self.last_status = status
                        if "config" in msg:
                            self.last_config = msg["config"]

                except websocket.WebSocketTimeoutException:
                    pass
                except Exception as e:
                    print(f"Warning during details refresh: {e}")

                # Build response with all available data
                result = {"success": True}

                if self.last_status:
                    result["status"] = self.last_status
                    # Extract netif and modems from status
                    if "modems" in self.last_status:
                        result["modems"] = self.last_status["modems"]

                if self.last_config:
                    result["config"] = self.last_config

                # Read bitrate file
                try:
                    with open('/tmp/belacoder_br', 'r') as f:
                        lines = f.readlines()
                        if len(lines) >= 2:
                            min_bitrate = int(lines[0].strip()) // 1000  # Convert to kbps
                            max_bitrate = int(lines[1].strip()) // 1000
                            result["bitrate"] = {
                                "min": min_bitrate,
                                "max": max_bitrate
                            }
                except Exception as e:
                    print(f"Warning: Could not read bitrate file: {e}")

                return result

            except Exception as e:
                self.disconnect()
                return {"success": False, "error": str(e)}

    # ========================================================================
    # RIST API Proxy Methods
    # Forward requests to local RIST API on port 3000
    # ========================================================================

    def get_rist_profiles_video(self) -> Dict:
        """Get RIST video profiles from local RIST API"""
        try:
            response = requests.get('http://127.0.0.1:3000/rist/profiles/video', timeout=5)
            return response.json()
        except requests.RequestException as e:
            return {
                "success": False,
                "error": f"RIST API unavailable: {str(e)}"
            }

    def get_rist_profiles_audio(self) -> Dict:
        """Get RIST audio profiles from local RIST API"""
        try:
            response = requests.get('http://127.0.0.1:3000/rist/profiles/audio', timeout=5)
            return response.json()
        except requests.RequestException as e:
            return {
                "success": False,
                "error": f"RIST API unavailable: {str(e)}"
            }

    def get_rist_profiles_overview(self) -> Dict:
        """Get RIST profiles overview"""
        try:
            response = requests.get('http://127.0.0.1:3000/rist/profiles', timeout=5)
            return response.json()
        except requests.RequestException as e:
            return {
                "success": False,
                "error": f"RIST API unavailable: {str(e)}"
            }

    def rist_profiles_sync(self) -> Dict:
        """Trigger manual RIST profile sync with license server"""
        try:
            response = requests.post('http://127.0.0.1:3000/rist/profiles/sync', timeout=30)
            return response.json()
        except requests.RequestException as e:
            return {
                "success": False,
                "error": f"RIST sync failed: {str(e)}"
            }

    def start_rist_stream(self, video_profile_id: str, audio_profile_id: str,
                          links: list, bonding_method: str = "broadcast",
                          params: dict = None) -> Dict:
        """Start RIST stream with specified profiles and configuration"""
        try:
            payload = {
                "video_profile_id": video_profile_id,
                "audio_profile_id": audio_profile_id,
                "links": links,
                "bonding_method": bonding_method
            }

            if params:
                payload["params"] = params

            response = requests.post('http://127.0.0.1:3000/rist/start',
                                   json=payload, timeout=10)
            return response.json()
        except requests.RequestException as e:
            return {
                "success": False,
                "error": f"RIST start failed: {str(e)}"
            }

    def stop_rist_stream(self) -> Dict:
        """Stop RIST stream"""
        try:
            response = requests.post('http://127.0.0.1:3000/rist/stop', timeout=5)
            return response.json()
        except requests.RequestException as e:
            return {
                "success": False,
                "error": f"RIST stop failed: {str(e)}"
            }

    def _update_rist_errors(self):
        """Check RIST manager for errors and update rist_errors list"""
        if not self.last_config or self.last_config.get('mode') != 'rist':
            self.rist_errors = []
            return
        
        try:
            response = requests.get('http://127.0.0.1:3000/rist/status', timeout=2)
            if response.status_code == 200:
                rist_status = response.json()
                if rist_status.get('error'):
                    # RIST has an error
                    error_notification = {
                        'name': 'rist_error',
                        'type': 'error',
                        'msg': rist_status['error'],
                        'source': 'RIST',
                        'isDismissable': False,
                        'isPersistent': True
                    }
                    self.rist_errors = [error_notification]
                else:
                    self.rist_errors = []
        except:
            pass

    def _get_active_mode(self) -> str:
        """Get the active streaming mode (srtla or rist)"""
        if not self.last_config:
            return 'srtla'  # Default
        return self.last_config.get('mode', 'srtla')
