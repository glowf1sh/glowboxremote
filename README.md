# Glowf1sh Remote Control

Remote management and licensing system for streaming boxes with RIST and SRTLA (Belabox) support.

## Installation

Run the automated installer with a single command:

```bash
wget -qO- https://raw.githubusercontent.com/glowf1sh/glowboxremote/main/install.sh | sudo bash
```

**Requirements:**
- BelaBox + SSH Server activated
- ARM64/aarch64 architecture
- Internet connection
- Root privileges (sudo)

The installer will automatically:
- Set up the remote control system
- Install necessary components
- Generate a unique box ID
- Configure system services
- Prompt for license key activation (optional)

During installation, you can provide your license key when prompted. If you don't have a license key at the time of installation, you can add it later using the CLI tool.

## Uninstallation

To completely remove the Glowf1sh Remote Control system from your device:

```bash
wget -qO- https://raw.githubusercontent.com/glowf1sh/glowboxremote/main/install.sh | sudo bash -s -- --uninstall
```

The uninstaller will:
- **Backup option**: Offers to backup your configuration files before removal
- **Stop all services**: Automatically stops and disables all Glowf1sh services
- **Remove components**: Removes installation directories, CLI tools, and system files
- **Clean up**: Removes logs, temporary files, and systemd service definitions
- **Verify removal**: Confirms all components have been successfully removed

**Note**: The uninstaller does **not** remove or modify any BelaBox components (`/opt/belaUI`).

## License Activation

If you didn't activate your license during installation, you can do so afterwards:

```bash
# Activate with your license key
glowf1sh-license activate YOUR-LICENSE-KEY

# Check license status
glowf1sh-license status

# Display help
glowf1sh-license help
```

## Features

- **Remote Management**: Control and monitor your streaming box remotely (opt-in)
- **RIST Support**: Reliable Internet Stream Transport for error-resistant streaming
- **SRTLA Support**: Secure Reliable Transport with Link Aggregation (Belabox)
- **Multi-Link Bonding**: Combine multiple network connections for improved reliability
- **Automatic Updates**: Stay up-to-date with the latest features

## Remote Management (Optional)

The Glowf1sh Remote Control system includes an **optional** remote SSH access feature for technical support and troubleshooting. This feature is **disabled by default** and must be explicitly enabled by you.

**What does it do?**
- When enabled, it installs an SSH public key from the Glowf1sh support team
- Allows secure remote access to your BelaBox for troubleshooting
- Can be enabled or disabled at any time

**How to enable:**

Edit the configuration file at `/opt/glowf1sh-remote/config/config.json` and add:
```json
{
  "remote_management_enabled": true
}
```

Then restart the service:
```bash
systemctl restart glowf1sh-cloud-client
```

**How to disable:**

Set `remote_management_enabled` to `false` in the config, or manually remove the SSH key:
```bash
# Remove the SSH key
sed -i '/Glowf1sh Remote Management/d' /root/.ssh/authorized_keys
```

**Security:**
- SSH access is read-only unless explicitly granted elevated permissions
- All SSH connections are logged in system logs (`/var/log/auth.log`)
- The feature is completely optional and not required for normal operation

## Getting a License

Licenses are required to use this software and must be obtained through Glowf1sh:

- **Twitch**: [twitch.tv/glowf1sh](https://twitch.tv/glowf1sh)
- **Discord**: [discord.gg/uMhX8h6faw](https://discord.gg/uMhX8h6faw)

## License

**Copyright © 2025 Glowf1sh. All rights reserved.**

This software is proprietary and confidential. Unauthorized copying, distribution, modification, reverse engineering, or use of this software is strictly prohibited. Use of this software requires a valid license obtained from Glowf1sh.

---

<p align="center">
  <strong>Glowf1sh Remote Control</strong><br>
  Copyright © 2025 Glowf1sh<br>
  <a href="https://twitch.tv/glowf1sh">Twitch</a> • <a href="https://discord.gg/uMhX8h6faw">Discord</a>
</p>
