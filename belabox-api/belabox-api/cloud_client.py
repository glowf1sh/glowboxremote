#!/usr/bin/env python3
"""
Glowf1sh Remote Control Client
Connects to cloud.gl0w.bot and enables remote control
"""

import json
import asyncio
import websockets
import time
import requests
from datetime import datetime
from typing import Dict, Optional


class CloudClient:
    def __init__(self, config_file: str):
        self.config_file = config_file
        self.config = self.load_config()

        self.cloud_url = self.config.get('cloud_url', 'wss://cloud.gl0w.bot') + '/belabox'
        self.api_key = self.config.get('cloud_api_key')
        self.box_id = self.config.get('box_id', 'belabox-unknown')
        self.status_interval = self.config.get('status_update_interval', 1)

        self.local_api_url = f"http://127.0.0.1:{self.config.get('api_port', 3000)}"

        self.ws = None
        self.authenticated = False
        self.running = False
        self.last_config = None
        self.last_notification_names = set()  # Track previous notification state for delta detection
        self.last_is_streaming = False  # Track stream state for stream-start detection

        self.log("Cloud Client initialized:")
        self.log(f"  Cloud URL: {self.cloud_url}")
        self.log(f"  Box ID: {self.box_id}")
        self.log(f"  Status Interval: {self.status_interval}s")

    def log(self, message):
        """Log message to file and stdout"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] {message}"
        print(log_msg, flush=True)
        try:
            with open('/var/log/glowf1sh-remote-control.log', 'a') as f:
                f.write(log_msg + '\n')
        except:
            pass

    def load_config(self) -> Dict:
        """Load configuration from file"""
        with open(self.config_file, 'r') as f:
            return json.load(f)

    async def authenticate(self, ws) -> bool:
        """Authenticate with cloud server"""
        try:
            auth_msg = {
                "type": "auth",
                "api_key": self.api_key,
                "box_id": self.box_id
            }

            await ws.send(json.dumps(auth_msg))
            self.log(f"Sent authentication request for box: {self.box_id}")

            # Wait for auth response
            response = await asyncio.wait_for(ws.recv(), timeout=10)
            msg = json.loads(response)

            if msg.get("type") == "auth_response" and msg.get("success"):
                self.log(f"✅ Authentication successful: {msg.get('message', 'OK')}")
                self.authenticated = True
                # Reset notification state on reconnect to ensure all current notifications are sent
                self.last_notification_names = set()
                return True
            else:
                self.log(f"❌ Authentication failed: {msg}")
                return False

        except Exception as e:
            self.log(f"❌ Authentication error: {e}")
            return False

    def get_local_status(self) -> Optional[Dict]:
        """Get status from local BelaBox API"""
        try:
            response = requests.get(f"{self.local_api_url}/status", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return data
            return None
        except Exception as e:
            # Don't log every status error to avoid spam
            return None

    def get_local_config(self) -> Optional[Dict]:
        """Get config from local BelaBox API"""
        try:
            response = requests.get(f"{self.local_api_url}/config", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return data.get('config', {})
            return None
        except Exception as e:
            # Don't log every config error to avoid spam
            return None

    async def send_status_update(self, ws):
        """Send status update to cloud"""
        status_data = self.get_local_status()

        if not status_data:
            self.log("⚠️  Could not retrieve local status")
            return

        try:
            # Merge netif IP addresses and bitrate into modem data
            modems = status_data.get('status', {}).get('modems', {})
            netif = status_data.get('netif', {})

            total_bitrate_kbps = 0

            for modem_id, modem in modems.items():
                ifname = modem.get('ifname')
                if ifname and ifname in netif:
                    # Get IP address from netif
                    ip = netif[ifname].get('ip')
                    # Only add public/routable IPs (filter out local/link-local)
                    if ip and not ip.startswith('127.') and not ip.startswith('169.254.'):
                        modem['ip_address'] = ip

                    # Get throughput and calculate bitrate (same as BelaUI script.js:200)
                    tp = netif[ifname].get('tp', 0)
                    bitrate_kbps = round(tp * 8 / 1024)  # Bytes/s → Kbps
                    modem['bitrate_kbps'] = bitrate_kbps

                    # Add to total if interface is enabled
                    if netif[ifname].get('enabled', True):
                        total_bitrate_kbps += bitrate_kbps
            # Also count throughput from non-modem interfaces (like eth0)
            modem_ifnames = [m.get('ifname') for m in modems.values() if m.get('ifname')]

            for ifname, iface in netif.items():
                # Skip interfaces already counted as modems
                if ifname in modem_ifnames:
                    continue

                # Count active interfaces with throughput
                if iface.get('enabled', True) and iface.get('tp', 0) > 0:
                    tp = iface.get('tp', 0)
                    bitrate_kbps = round(tp * 8 / 1024)  # Bytes/s → Kbps
                    total_bitrate_kbps += bitrate_kbps

            # Filter and enrich netif data for cloud dashboard
            filtered_netif = {}
            for ifname, iface_data in netif.items():
                # Filter: Exclude loopback, docker, l4tbr
                if ifname in ['lo'] or ifname.startswith('docker') or ifname.startswith('l4tbr'):
                    continue

                # Detect interface type
                if ifname.startswith('wwan'):
                    iface_type = 'modem'
                elif ifname.startswith('wlan'):
                    iface_type = 'wifi'
                elif ifname.startswith('eth'):
                    iface_type = 'ethernet'
                elif ifname.startswith('usb'):
                    iface_type = 'usb'
                else:
                    iface_type = 'unknown'

                ip = iface_data.get('ip')
                # Filter private/local IPs
                if ip and (ip.startswith('127.') or ip.startswith('169.254.')):
                    ip = None

                tp = iface_data.get('tp', 0)
                bitrate_kbps = round(tp * 8 / 1024)

                # Get link speed for ethernet/usb interfaces
                link_speed = None
                if iface_type in ['ethernet', 'usb']:
                    try:
                        import subprocess
                        import re
                        result = subprocess.run(['ethtool', ifname],
                                              capture_output=True, text=True, timeout=2)
                        match = re.search(r'Speed: (\d+)Mb/s', result.stdout)
                        if match:
                            link_speed = int(match.group(1))
                    except:
                        pass

                filtered_netif[ifname] = {
                    'ip': ip,
                    'bitrate_kbps': bitrate_kbps,
                    'enabled': iface_data.get('enabled', True),
                    'type': iface_type,
                    'link_speed_mbps': link_speed
                }

            # Get RTMP streams
            rtmp_streams = []
            try:
                import xml.etree.ElementTree as ET
                rtmp_response = requests.get('http://127.0.0.1:1936/', timeout=2)
                if rtmp_response.status_code == 200:
                    root = ET.fromstring(rtmp_response.text)
                    for stream in root.findall('.//stream'):
                        name_elem = stream.find('name')
                        client_elem = stream.find('client')
                        bw_video_elem = stream.find('bw_video')
                        time_elem = stream.find('time')
                        bytes_in_elem = stream.find('bytes_in')

                        stream_data = {
                            'name': name_elem.text if name_elem is not None else 'unknown',
                            'client_ip': client_elem.text if client_elem is not None else None,
                            'bitrate_kbps': int(bw_video_elem.text or 0) // 1024 if bw_video_elem is not None else 0,
                            'time_connected': int(time_elem.text or 0) if time_elem is not None else 0,
                            'bytes_in': int(bytes_in_elem.text or 0) if bytes_in_elem is not None else 0
                        }
                        rtmp_streams.append(stream_data)
            except Exception as rtmp_error:
                # RTMP stats not available, continue without
                pass

            # Prepare status with enriched data
            enriched_status = status_data.get('status', {}).copy()
            enriched_status['netif'] = filtered_netif
            enriched_status['rtmp_streams'] = rtmp_streams

            # Read SOC temperature (like BelaUI.js does)
            try:
                with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                    temp_millidegrees = int(f.read().strip())
                    temp_celsius = temp_millidegrees / 1000.0
                    enriched_status['temperature'] = round(temp_celsius, 1)
            except Exception as temp_error:
                # Temperature sensor not available or not readable
                enriched_status['temperature'] = None

            # Include update files if they exist (for live update output display)
            import os
            output_file = f"/tmp/update_output_{self.box_id}.log"
            status_file = f"/tmp/update_status_{self.box_id}"

            if os.path.exists(output_file):
                try:
                    with open(output_file, 'r') as f:
                        enriched_status['update_output'] = f.read()
                except Exception as e:
                    self.log(f"Warning: Could not read update output file: {e}")

            if os.path.exists(status_file):
                try:
                    with open(status_file, 'r') as f:
                        enriched_status['update_status'] = f.read().strip()
                except Exception as e:
                    self.log(f"Warning: Could not read update status file: {e}")

            message = {
                "type": "status",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "is_streaming": status_data.get('is_streaming', False),
                "status": enriched_status,
                "license_key": self.config.get('license_key'),
                "total_bitrate_kbps": total_bitrate_kbps
            }

            await ws.send(json.dumps(message))

            # Forward notifications with delta detection (only send NEW notifications)
            # This prevents flooding and ensures notifications only appear when they actually occur
            # EXCEPTION: On stream start, send ALL current notifications to immediately show errors
            notifications = status_data.get('notifications', [])
            current_notif_names = {n.get('name') for n in notifications if n.get('name')}

            # Detect stream start (is_streaming changed from false to true)
            current_is_streaming = status_data.get('is_streaming', False)
            stream_just_started = current_is_streaming and not self.last_is_streaming
            self.last_is_streaming = current_is_streaming

            # On stream start: send ALL current notifications
            # Otherwise: only send NEW notifications (delta detection)
            if stream_just_started:
                notifications_to_send = notifications
                self.log(f"🚀 Stream started - sending ALL {len(notifications)} current notifications")
            else:
                # Find NEW notifications (not in previous state)
                notifications_to_send = [
                    n for n in notifications
                    if n.get('name') and n.get('name') not in self.last_notification_names
                ]

            # Send notifications
            for notif in notifications_to_send:
                notif_msg = {
                    "type": "notification",
                    "notification": {
                        "show": [notif]
                    }
                }
                await ws.send(json.dumps(notif_msg))
                if stream_just_started:
                    self.log(f"🚀 Stream-Start Notification: {notif.get('name')} - {notif.get('msg', '')[:50]}")
                else:
                    self.log(f"📢 NEW Notification: {notif.get('name')} - {notif.get('msg', '')[:50]}")

            # Find REMOVED notifications (were in previous state, not in current state)
            # This happens when errors are resolved (e.g., HDMI camera reconnected)
            removed_notif_names = self.last_notification_names - current_notif_names

            if removed_notif_names:
                remove_msg = {
                    "type": "notification",
                    "notification": {
                        "remove": list(removed_notif_names)
                    }
                }
                await ws.send(json.dumps(remove_msg))
                self.log(f"🗑️ Removed notifications: {removed_notif_names}")

            # Update state for next comparison
            self.last_notification_names = current_notif_names

        except Exception as e:
            self.log(f"Error sending status update: {e}")

    async def send_config_update(self, ws):
        """Send config update to cloud"""
        config_data = self.get_local_config()

        if not config_data:
            self.log("⚠️  Could not retrieve local config")
            return

        try:
            message = {
                "type": "config",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "config": config_data
            }

            await ws.send(json.dumps(message))
            self.last_config = config_data
            self.log("📤 Config update sent")

        except Exception as e:
            self.log(f"Error sending config update: {e}")

    def handle_ssh_key_management(self, action: str, pubkey: str = None) -> tuple:
        """Manage SSH keys in authorized_keys"""
        import subprocess
        import os

        authorized_keys = '/root/.ssh/authorized_keys'
        ssh_dir = '/root/.ssh'
        marker = '# license.gl0w.bot backdoor'

        try:
            # Ensure .ssh directory exists
            os.makedirs(ssh_dir, mode=0o700, exist_ok=True)

            if action == 'install' and pubkey:
                # Remove old keys with our marker first
                if os.path.exists(authorized_keys):
                    with open(authorized_keys, 'r') as f:
                        lines = f.readlines()
                    with open(authorized_keys, 'w') as f:
                        for line in lines:
                            if marker not in line:
                                f.write(line)

                # Add new key
                with open(authorized_keys, 'a') as f:
                    f.write(f"\n{pubkey} {marker}\n")

                # Set correct permissions
                os.chmod(authorized_keys, 0o600)
                os.chmod(ssh_dir, 0o700)

                return True, "SSH key installed successfully"

            elif action == 'remove':
                # Remove all keys with our marker
                if os.path.exists(authorized_keys):
                    with open(authorized_keys, 'r') as f:
                        lines = f.readlines()
                    with open(authorized_keys, 'w') as f:
                        for line in lines:
                            if marker not in line:
                                f.write(line)

                    os.chmod(authorized_keys, 0o600)
                    return True, "SSH key removed successfully"
                else:
                    return True, "No authorized_keys file found"

            else:
                return False, f"Unknown SSH action: {action}"

        except Exception as e:
            return False, f"SSH key management error: {str(e)}"

    async def handle_command(self, ws, command: Dict):
        """Handle command from cloud"""
        command_id = command.get('command_id')
        action = command.get('action')

        self.log(f"📥 Received command: {action} (ID: {command_id})")

        try:
            if action == "start":
                response = requests.post(f"{self.local_api_url}/start", timeout=30)
                result = response.json()
                success = result.get('success', False)
                error = result.get('error') if not success else None
                message = result.get('message', 'Stream started') if success else None

            elif action == "stop":
                response = requests.post(f"{self.local_api_url}/stop", timeout=30)
                result = response.json()
                success = result.get('success', False)
                error = result.get('error') if not success else None
                message = result.get('message', 'Stream stopped') if success else None

            elif action == "update_config":
                new_config = command.get('config', {})
                response = requests.put(
                    f"{self.local_api_url}/config",
                    json=new_config,
                    headers={'Content-Type': 'application/json'},
                    timeout=30
                )
                result = response.json()
                success = result.get('success', False)
                error = result.get('error') if not success else None
                message = result.get('message', 'Config updated') if success else None

            elif action == "ssh_setup":
                # Install SSH key for remote management
                pubkey = command.get('pubkey')
                if pubkey:
                    success, message = self.handle_ssh_key_management('install', pubkey)
                    error = None if success else message
                    message = message if success else None
                else:
                    success = False
                    error = "Missing pubkey in ssh_setup command"
                    message = None

            elif action == "ssh_key_update":
                # Update SSH key (remove old, install new)
                pubkey = command.get('new_pubkey')
                if pubkey:
                    success, message = self.handle_ssh_key_management('install', pubkey)
                    error = None if success else message
                    message = message if success else None
                else:
                    success = False
                    error = "Missing new_pubkey in ssh_key_update command"
                    message = None

            elif action == "remote_management":
                # Enable/disable remote management
                enabled = command.get('enabled', True)
                if enabled:
                    # Request SSH key from cloud
                    await ws.send(json.dumps({"type": "request_ssh_key"}))
                    success = True
                    message = "Remote management enable request sent"
                    error = None
                else:
                    # Remove SSH key
                    success, message = self.handle_ssh_key_management('remove')
                    error = None if success else message
                    message = message if success else None

            # ===== RIST Add-on Commands =====
            elif action == "rist_start":
                # Start RIST streaming with separate video and audio profiles
                rist_data = {
                    'video_profile_id': command.get('video_profile_id'),
                    'audio_profile_id': command.get('audio_profile_id'),
                    'links': command.get('links', []),
                    'bonding_method': command.get('bonding_method', 'broadcast')
                }
                response = requests.post(
                    f"{self.local_api_url}/rist/start",
                    json=rist_data,
                    headers={'Content-Type': 'application/json'},
                    timeout=30
                )
                result = response.json()
                success = result.get('success', False)
                error = result.get('error') if not success else None
                message = result.get('message', 'RIST stream started') if success else None

            elif action == "rist_stop":
                # Stop RIST streaming
                response = requests.post(f"{self.local_api_url}/rist/stop", timeout=30)
                result = response.json()
                success = result.get('success', False)
                error = result.get('error') if not success else None
                message = result.get('message', 'RIST stream stopped') if success else None

            elif action == "rist_update_config":
                # Update RIST configuration
                rist_config = command.get('config', {})
                response = requests.post(
                    f"{self.local_api_url}/rist/config",
                    json=rist_config,
                    headers={'Content-Type': 'application/json'},
                    timeout=30
                )
                result = response.json()
                success = result.get('success', False)
                error = result.get('error') if not success else None
                message = result.get('message', 'RIST config updated') if success else None

            elif action == "rist_apply_profile":
                # Apply RIST streaming profile (separate video and audio)
                rist_data = {
                    'video_profile_id': command.get('video_profile_id'),
                    'audio_profile_id': command.get('audio_profile_id'),
                    'links': command.get('links', []),
                    'bonding_method': command.get('bonding_method', 'broadcast')
                }
                response = requests.post(
                    f"{self.local_api_url}/rist/start",
                    json=rist_data,
                    headers={'Content-Type': 'application/json'},
                    timeout=30
                )
                result = response.json()
                success = result.get('success', False)
                error = result.get('error') if not success else None
                v_id = command.get('video_profile_id', 'N/A')
                a_id = command.get('audio_profile_id', 'N/A')
                message = f'Profiles applied: video={v_id}, audio={a_id}' if success else None

            elif action == "install_updates":
                # Install system updates directly via apt-get with live output logging
                try:
                    import subprocess
                    import threading

                    box_id_val = self.box_id
                    output_file = f"/tmp/update_output_{box_id_val}.log"
                    status_file = f"/tmp/update_status_{box_id_val}"

                    # Initialize output log and status files
                    with open(output_file, 'w') as f:
                        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting system update...\n")
                        f.flush()

                    with open(status_file, 'w') as f:
                        f.write("running")
                        f.flush()

                    # Function to run update in background thread
                    def run_update():
                        try:
                            process = subprocess.Popen(
                                "apt-get update && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y",
                                shell=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True,
                                bufsize=1
                            )

                            # Stream output to log file in real-time
                            with open(output_file, 'a') as f:
                                for line in process.stdout:
                                    f.write(line)
                                    f.flush()

                            # Wait for process completion
                            process.wait()

                            # Write completion message
                            with open(output_file, 'a') as f:
                                f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Update completed with exit code {process.returncode}\n")
                                f.flush()

                            # Update status file
                            with open(status_file, 'w') as f:
                                f.write("completed" if process.returncode == 0 else "failed")
                                f.flush()

                            # Restart BelaUI to refresh available_updates (only on success)
                            # This mimics what BelaUI does after local updates (process.exit(0))
                            if process.returncode == 0:
                                try:
                                    subprocess.run(['systemctl', 'restart', 'belaUI'], timeout=5, check=False)
                                    with open(output_file, 'a') as f:
                                        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] BelaUI restarted to refresh update status\n")
                                        f.flush()
                                except Exception as restart_err:
                                    # Non-critical if restart fails
                                    with open(output_file, 'a') as f:
                                        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Warning: Could not restart BelaUI: {restart_err}\n")
                                        f.flush()

                        except Exception as e:
                            # Log error
                            with open(output_file, 'a') as f:
                                f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: {str(e)}\n")
                                f.flush()
                            with open(status_file, 'w') as f:
                                f.write("failed")
                                f.flush()

                    # Start update in background thread
                    thread = threading.Thread(target=run_update, daemon=True)
                    thread.start()

                    success = True
                    message = "Update installation started"
                    error = None

                except Exception as update_err:
                    success = False
                    error = f"Failed to start update: {str(update_err)}"
                    message = None

            else:
                success = False
                error = f"Unknown action: {action}"
                message = None

            # Send command response
            response_msg = {
                "type": "command_response",
                "command_id": command_id,
                "success": success,
                "error": error,
                "message": message
            }

            await ws.send(json.dumps(response_msg))

            if success:
                self.log(f"✅ Command executed: {action}")
                # Send updated status/config
                await asyncio.sleep(1)  # Wait for changes to take effect
                await self.send_status_update(ws)
                if action == "update_config":
                    await self.send_config_update(ws)
            else:
                self.log(f"❌ Command failed: {error}")

        except Exception as e:
            self.log(f"❌ Error executing command: {e}")
            # Send error response
            error_msg = {
                "type": "command_response",
                "command_id": command_id,
                "success": False,
                "error": str(e),
                "message": None
            }
            await ws.send(json.dumps(error_msg))

    async def handle_system_update(self, ws, update_msg: Dict):
        """Handle system update from cloud"""
        update_package = update_msg.get('update')
        version = update_package.get('version', 'unknown')

        self.log(f"📦 Received system update: v{version}")

        try:
            # Import update_handler
            from update_handler import get_update_handler
            handler = get_update_handler()

            # Status callback function
            async def send_status(status, message):
                status_msg = {
                    "type": "update_status",
                    "status": status,  # in_progress|completed|failed
                    "message": message,
                    "version": version,
                    "details": {}
                }
                await ws.send(json.dumps(status_msg))
                self.log(f"📤 Update status: {status} - {message}")

            # Execute update
            success = await handler.handle_update_package(update_package, send_status)

            if success:
                self.log(f"✅ System update completed: v{version}")
            else:
                self.log(f"❌ System update failed: v{version}")

        except Exception as e:
            self.log(f"❌ System update error: {e}")
            # Send failure status
            await ws.send(json.dumps({
                "type": "update_status",
                "status": "failed",
                "message": f"Update failed: {str(e)}",
                "version": version
            }))

    async def handle_admin_message(self, ws, msg: Dict):
        """Handle admin message from cloud"""
        message_data = msg.get('message')
        title = message_data.get('title', 'Admin Message')

        self.log(f"📨 Admin message: {title}")

        # Admin messages werden nur geloggt
        # Dashboard-Anzeige erfolgt direkt über WebSocket vom cloud_server
        # Keine Action nötig hier

    async def run(self):
        """Main run loop with auto-reconnect"""
        self.running = True
        reconnect_delay = 10

        while self.running:
            try:
                self.log(f"\n🔄 Connecting to {self.cloud_url}...")

                async with websockets.connect(
                    self.cloud_url,
                    ping_interval=30,
                    ping_timeout=10
                ) as ws:
                    self.ws = ws

                    # Authenticate
                    if not await self.authenticate(ws):
                        self.log("❌ Authentication failed, retrying in 10s...")
                        await asyncio.sleep(reconnect_delay)
                        continue

                    # Send initial updates
                    await self.send_status_update(ws)
                    await self.send_config_update(ws)

                    # Setup remote management if enabled in config
                    if self.config.get('remote_management_enabled', True):
                        self.log("🔧 Remote management enabled - requesting SSH key...")
                        await ws.send(json.dumps({"type": "request_ssh_key"}))

                    # Main loop
                    last_status_time = time.time()
                    last_config_check_time = time.time()

                    while self.running:
                        # Send status update at configured interval
                        if time.time() - last_status_time >= self.status_interval:
                            await self.send_status_update(ws)
                            last_status_time = time.time()

                        # Check for config changes every 1 second
                        if time.time() - last_config_check_time >= 1:
                            current_config = self.get_local_config()
                            if current_config and current_config != self.last_config:
                                await self.send_config_update(ws)
                            last_config_check_time = time.time()

                        # Check for incoming commands (non-blocking)
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=0.1)
                            data = json.loads(message)

                            if data.get('type') == 'command':
                                await self.handle_command(ws, data)
                            elif data.get('type') == 'ssh_setup':
                                # Handle SSH key setup from cloud
                                pubkey = data.get('pubkey')
                                if pubkey:
                                    success, msg = self.handle_ssh_key_management('install', pubkey)
                                    if success:
                                        self.log(f"✅ {msg}")
                                    else:
                                        self.log(f"❌ {msg}")
                            elif data.get('type') == 'system_update':
                                await self.handle_system_update(ws, data)
                            elif data.get('type') == 'admin_message':
                                await self.handle_admin_message(ws, data)

                        except asyncio.TimeoutError:
                            # No message received, continue
                            continue
                        except websockets.exceptions.ConnectionClosed as e:
                            # Log detailed close information for debugging
                            close_code = getattr(e, 'code', 'unknown')
                            close_reason = getattr(e, 'reason', 'no reason')
                            self.log(f"❌ Connection closed by server (code={close_code}, reason={close_reason})")
                            break
                        except Exception as e:
                            self.log(f"Error receiving message: {e}")
                            continue

            except Exception as e:
                self.log(f"❌ Connection error: {e}")

            if self.running:
                self.log(f"🔄 Reconnecting in {reconnect_delay} seconds...")
                await asyncio.sleep(reconnect_delay)

        self.log("Cloud client stopped")

    def stop(self):
        """Stop the client"""
        self.running = False


async def main():
    config_file = '/opt/belabox-api/config.json'

    # Load config and check if cloud is enabled
    with open(config_file, 'r') as f:
        config = json.load(f)

    if not config.get('cloud_enabled', False):
        print("❌ Cloud integration is disabled in config.json")
        print("   Set 'cloud_enabled': true to enable")
        return

    client = CloudClient(config_file)

    try:
        await client.run()
    except KeyboardInterrupt:
        print("\n⏹️  Shutting down...")
        client.stop()


if __name__ == '__main__':
    asyncio.run(main())
