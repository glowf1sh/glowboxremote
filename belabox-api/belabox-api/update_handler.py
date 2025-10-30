#!/usr/bin/env python3
"""
Glowf1sh Remote Update Handler
Empfängt System-Updates über WebSocket und führt sie aus

WICHTIG: NUR für Glowf1sh System Updates!
NICHT für belaUI.js oder Linux System Updates!
"""

import json
import base64
import os
import subprocess
import logging
import sys
from datetime import datetime
from typing import Dict, List, Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/var/log/glowf1sh-update.log')
    ]
)
logger = logging.getLogger('update_handler')


class UpdateHandler:
    """Handles Glowf1sh system updates"""

    def __init__(self):
        self.allowed_paths = ['/opt/belabox-api', '/opt/cloud', '/opt/rist']
        self.allowed_services = [
            'websocket-client',
            'glowf1sh-update-handler',
            'rist-relay'
        ]

    def validate_path(self, path: str) -> bool:
        """Validate that file path is in allowed directories"""
        abs_path = os.path.abspath(path)
        return any(abs_path.startswith(allowed) for allowed in self.allowed_paths)

    def validate_service(self, service: str) -> bool:
        """Validate that service is in whitelist"""
        return service in self.allowed_services

    async def handle_update_package(self, update_data: dict, send_status_callback) -> bool:
        """
        Process update package

        update_data = {
            version: "1.2.3",
            message: "Updating RIST components...",
            files: [{path, content_base64, mode}],
            commands: ["command1", "command2"],
            restart_services: ["service1", "service2"]
        }
        """
        try:
            version = update_data.get('version', 'unknown')
            message = update_data.get('message', 'Updating...')

            logger.info(f"Starting update to version {version}")
            await send_status_callback('in_progress', f"Glowf1sh Box Remote auto-updating... ({message})")

            # 1. Write files
            files = update_data.get('files', [])
            if files:
                logger.info(f"Writing {len(files)} files...")
                for file_info in files:
                    success = self.write_file(
                        file_info.get('path'),
                        file_info.get('content_base64'),
                        file_info.get('mode', '0644')
                    )
                    if not success:
                        raise Exception(f"Failed to write file: {file_info.get('path')}")

            # 2. Execute commands
            commands = update_data.get('commands', [])
            if commands:
                logger.info(f"Executing {len(commands)} commands...")
                for cmd in commands:
                    success = self.execute_command(cmd)
                    if not success:
                        raise Exception(f"Failed to execute command: {cmd}")

            # 3. Restart services
            services = update_data.get('restart_services', [])
            if services:
                logger.info(f"Restarting {len(services)} services...")
                for service in services:
                    success = self.restart_service(service)
                    if not success:
                        logger.warning(f"Failed to restart service: {service}")

            logger.info(f"Update to version {version} completed successfully")
            await send_status_callback('completed', f"Update erfolgreich abgeschlossen (v{version})")
            return True

        except Exception as e:
            logger.error(f"Update failed: {e}")
            await send_status_callback('failed', f"Update fehlgeschlagen: {str(e)}")
            return False

    def write_file(self, path: str, content_base64: str, mode: str) -> bool:
        """Write file from base64 content"""
        try:
            if not path or not content_base64:
                logger.error("Missing path or content")
                return False

            if not self.validate_path(path):
                logger.error(f"Path not allowed: {path}")
                return False

            # Decode base64
            content = base64.b64decode(content_base64)

            # Create directory if needed
            directory = os.path.dirname(path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, mode=0o755)

            # Write file
            with open(path, 'wb') as f:
                f.write(content)

            # Set permissions
            mode_int = int(mode, 8) if isinstance(mode, str) else mode
            os.chmod(path, mode_int)

            logger.info(f"Written file: {path} (mode: {mode})")
            return True

        except Exception as e:
            logger.error(f"Failed to write file {path}: {e}")
            return False

    def execute_command(self, command: str) -> bool:
        """Execute shell command"""
        try:
            logger.info(f"Executing: {command}")

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout
            )

            if result.stdout:
                logger.info(f"Command output: {result.stdout}")
            if result.stderr:
                logger.warning(f"Command stderr: {result.stderr}")

            if result.returncode != 0:
                logger.error(f"Command failed with exit code {result.returncode}")
                return False

            return True

        except subprocess.TimeoutExpired:
            logger.error(f"Command timeout: {command}")
            return False
        except Exception as e:
            logger.error(f"Failed to execute command {command}: {e}")
            return False

    def restart_service(self, service: str) -> bool:
        """Restart systemd service"""
        try:
            if not self.validate_service(service):
                logger.error(f"Service not in whitelist: {service}")
                return False

            logger.info(f"Restarting service: {service}")

            result = subprocess.run(
                ['systemctl', 'restart', service],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                logger.error(f"Failed to restart {service}: {result.stderr}")
                return False

            logger.info(f"Service {service} restarted successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to restart service {service}: {e}")
            return False


# Singleton instance
update_handler = UpdateHandler()


def get_update_handler():
    """Get the update handler instance"""
    return update_handler
