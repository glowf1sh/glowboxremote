#!/usr/bin/env python3
"""
Adaptive Controller - Dynamic Bitrate and Link Management
Monitors network conditions and modem signals to optimize RIST streaming.

Features:
- Adaptive bitrate based on RIST stats (packet loss, RTT)
- Bonding link management based on modem signal quality
- Dual-update: API (hot-reload) + config.json (persistence)
- Configurable thresholds and behavior
"""

import json
import logging
import threading
import time
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
from pathlib import Path

from rist_manager import RISTManager, VideoConfig, AudioConfig, RISTConfig, RISTLink
from modem_monitor import ModemMonitor, ModemStatus, SignalQuality


logger = logging.getLogger(__name__)


@dataclass
class AdaptiveConfig:
    """Configuration for adaptive controller behavior"""

    # Enable/disable adaptive features
    enabled: bool = True
    adaptive_bitrate_enabled: bool = True
    adaptive_links_enabled: bool = True

    # Bitrate adaptation thresholds
    packet_loss_threshold_high: float = 5.0  # % - reduce bitrate
    packet_loss_threshold_low: float = 1.0   # % - can increase bitrate
    rtt_threshold_high: int = 200  # ms - reduce bitrate

    # Bitrate adjustment parameters
    bitrate_step_down: float = 0.15  # Reduce by 15%
    bitrate_step_up: float = 0.10    # Increase by 10%
    min_video_bitrate: int = 500000  # 500 kbps minimum
    max_video_bitrate: int = 10000000  # 10 Mbps maximum

    # Link management thresholds
    link_disable_signal_threshold: int = 20  # % - disable link below this
    link_enable_signal_threshold: int = 40   # % - re-enable link above this

    # Timing
    stats_check_interval: int = 2  # seconds
    config_save_interval: int = 10  # seconds

    # Stability requirements
    stable_periods_before_increase: int = 5  # Good stats for N periods before increase
    immediate_decrease: bool = True  # Decrease immediately on bad stats


@dataclass
class AdaptiveState:
    """Current state of adaptive controller"""

    # Current network metrics
    current_packet_loss: float = 0.0  # %
    current_rtt: int = 0  # ms
    current_retransmissions: int = 0

    # Current bitrates
    current_video_bitrate: int = 0
    current_audio_bitrate: int = 0

    # Link states
    active_links: List[str] = None
    disabled_links: List[str] = None

    # Stability tracking
    stable_periods: int = 0
    last_adjustment_time: float = 0

    # Action history
    total_bitrate_increases: int = 0
    total_bitrate_decreases: int = 0
    total_link_disables: int = 0
    total_link_enables: int = 0

    def __post_init__(self):
        if self.active_links is None:
            self.active_links = []
        if self.disabled_links is None:
            self.disabled_links = []


class AdaptiveController:
    """
    Adaptive controller for RIST streaming.

    Monitors network conditions and modem signals to:
    - Adjust video/audio bitrate dynamically
    - Enable/disable bonding links based on signal quality
    - Persist changes to config.json
    """

    def __init__(
        self,
        rist_manager: RISTManager,
        modem_monitor: Optional[ModemMonitor] = None,
        config_path: str = "/opt/belaUI/config.json",
        adaptive_config: Optional[AdaptiveConfig] = None,
        state_callback: Optional[Callable[[AdaptiveState], None]] = None
    ):
        """
        Initialize adaptive controller.

        Args:
            rist_manager: RISTManager instance to control
            modem_monitor: Optional ModemMonitor for signal-based decisions
            config_path: Path to config.json for persistence
            adaptive_config: Configuration for adaptive behavior
            state_callback: Optional callback for state updates
        """
        self.rist_manager = rist_manager
        self.modem_monitor = modem_monitor
        self.config_path = Path(config_path)
        self.config = adaptive_config or AdaptiveConfig()
        self.state_callback = state_callback

        # State
        self.state = AdaptiveState()
        self._lock = threading.RLock()

        # Control thread
        self._control_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Config save tracking
        self._config_dirty = False
        self._last_config_save = 0

    def start(self) -> bool:
        """
        Start adaptive controller.

        Returns:
            True if started successfully
        """
        if self._control_thread and self._control_thread.is_alive():
            logger.warning("Adaptive controller already running")
            return False

        if not self.config.enabled:
            logger.info("Adaptive controller disabled in config")
            return False

        logger.info("Starting adaptive controller...")
        self._stop_event.clear()
        self._control_thread = threading.Thread(
            target=self._control_loop,
            daemon=True,
            name="AdaptiveController"
        )
        self._control_thread.start()

        logger.info("Adaptive controller started")
        return True

    def stop(self) -> None:
        """Stop adaptive controller"""
        if not self._control_thread or not self._control_thread.is_alive():
            logger.warning("Adaptive controller not running")
            return

        logger.info("Stopping adaptive controller...")
        self._stop_event.set()

        if self._control_thread:
            self._control_thread.join(timeout=10.0)
            self._control_thread = None

        # Save config one last time if dirty
        if self._config_dirty:
            self._save_config()

        logger.info("Adaptive controller stopped")

    def _control_loop(self) -> None:
        """Main control loop"""
        logger.info(f"Adaptive control loop started (interval: {self.config.stats_check_interval}s)")

        while not self._stop_event.is_set():
            try:
                # Update state from RIST stats
                self._update_rist_stats()

                # Update state from modem monitor
                if self.modem_monitor:
                    self._update_modem_stats()

                # Make adaptive decisions
                if self.config.adaptive_bitrate_enabled:
                    self._adaptive_bitrate_control()

                if self.config.adaptive_links_enabled and self.modem_monitor:
                    self._adaptive_link_control()

                # Save config periodically if dirty
                if self._config_dirty:
                    current_time = time.time()
                    if current_time - self._last_config_save >= self.config.config_save_interval:
                        self._save_config()

                # Notify state callback
                if self.state_callback:
                    with self._lock:
                        self.state_callback(self.state)

            except Exception as e:
                logger.error(f"Adaptive control loop error: {e}", exc_info=True)

            # Wait for next interval
            self._stop_event.wait(self.config.stats_check_interval)

    def _update_rist_stats(self) -> None:
        """Update state from RIST manager statistics"""
        stats = self.rist_manager.get_stats()
        if not stats:
            return

        with self._lock:
            # Extract metrics
            sent_original = stats.get("sent_original_packets", 0)
            sent_retransmitted = stats.get("sent_retransmitted_packets", 0)

            # Calculate packet loss percentage
            if sent_original > 0:
                self.state.current_packet_loss = (sent_retransmitted / sent_original) * 100
            else:
                self.state.current_packet_loss = 0.0

            self.state.current_retransmissions = sent_retransmitted

            # TODO: Extract RTT from session stats if available
            # For now, RTT would need to be added to rist_manager stats extraction

            # Update current bitrates from rist_manager config
            if self.rist_manager.video_config:
                self.state.current_video_bitrate = self.rist_manager.video_config.bitrate
            if self.rist_manager.audio_config:
                self.state.current_audio_bitrate = self.rist_manager.audio_config.bitrate

    def _update_modem_stats(self) -> None:
        """Update state from modem monitor"""
        if not self.modem_monitor:
            return

        modem_status = self.modem_monitor.get_all_modem_status()

        with self._lock:
            # Track which links should be active based on modem signal
            active = []
            disabled = []

            for modem_id, status in modem_status.items():
                if status.connected and status.signal_strength >= self.config.link_enable_signal_threshold:
                    active.append(modem_id)
                elif status.signal_strength < self.config.link_disable_signal_threshold:
                    disabled.append(modem_id)

            # Only update if changed to avoid unnecessary reconfigurations
            if set(active) != set(self.state.active_links):
                logger.info(f"Active links changed: {self.state.active_links} -> {active}")
                self.state.active_links = active

            if set(disabled) != set(self.state.disabled_links):
                logger.info(f"Disabled links changed: {self.state.disabled_links} -> {disabled}")
                self.state.disabled_links = disabled

    def _adaptive_bitrate_control(self) -> None:
        """Adaptive bitrate adjustment based on network conditions"""
        with self._lock:
            packet_loss = self.state.current_packet_loss
            current_bitrate = self.state.current_video_bitrate

            if current_bitrate == 0:
                return  # No bitrate set yet

            # Check if we should decrease bitrate (immediate action)
            should_decrease = (
                packet_loss > self.config.packet_loss_threshold_high or
                (self.state.current_rtt > self.config.rtt_threshold_high and self.state.current_rtt > 0)
            )

            if should_decrease and self.config.immediate_decrease:
                # Decrease bitrate
                new_bitrate = int(current_bitrate * (1 - self.config.bitrate_step_down))
                new_bitrate = max(new_bitrate, self.config.min_video_bitrate)

                if new_bitrate < current_bitrate:
                    logger.warning(
                        f"Network degradation detected (loss: {packet_loss:.2f}%, "
                        f"RTT: {self.state.current_rtt}ms) - "
                        f"Reducing bitrate: {current_bitrate//1000} -> {new_bitrate//1000} kbps"
                    )
                    self._apply_video_bitrate(new_bitrate)
                    self.state.stable_periods = 0
                    self.state.total_bitrate_decreases += 1
                    self.state.last_adjustment_time = time.time()
                return

            # Check if we can increase bitrate (requires stability)
            can_increase = (
                packet_loss < self.config.packet_loss_threshold_low and
                current_bitrate < self.config.max_video_bitrate
            )

            if can_increase:
                self.state.stable_periods += 1

                if self.state.stable_periods >= self.config.stable_periods_before_increase:
                    # Increase bitrate
                    new_bitrate = int(current_bitrate * (1 + self.config.bitrate_step_up))
                    new_bitrate = min(new_bitrate, self.config.max_video_bitrate)

                    if new_bitrate > current_bitrate:
                        logger.info(
                            f"Network stable for {self.state.stable_periods} periods - "
                            f"Increasing bitrate: {current_bitrate//1000} -> {new_bitrate//1000} kbps"
                        )
                        self._apply_video_bitrate(new_bitrate)
                        self.state.stable_periods = 0
                        self.state.total_bitrate_increases += 1
                        self.state.last_adjustment_time = time.time()
            else:
                # Reset stability counter if conditions not met
                if packet_loss >= self.config.packet_loss_threshold_low:
                    self.state.stable_periods = 0

    def _adaptive_link_control(self) -> None:
        """Enable/disable bonding links based on modem signal quality"""
        if not self.rist_manager.rist_config:
            return

        with self._lock:
            current_links = self.rist_manager.rist_config.links

            # Check if link configuration needs update
            needs_update = False
            new_links = []

            for link in current_links:
                # Assume link.address maps to modem (would need proper mapping in real implementation)
                # For now, we'll use a simple heuristic based on active_links

                # Check if this link should be enabled or disabled
                should_be_enabled = True  # Default

                # If we have modem monitoring, check signal
                if self.modem_monitor:
                    modem_status = self.modem_monitor.get_all_modem_status()

                    # Find corresponding modem (this is simplified - needs proper mapping)
                    for modem_id, status in modem_status.items():
                        # Check if link matches modem (by interface or other mapping)
                        if status.signal_strength < self.config.link_disable_signal_threshold:
                            should_be_enabled = False
                            if link.enabled:
                                logger.warning(
                                    f"Disabling link {link.address}:{link.port} - "
                                    f"modem {modem_id} signal too low ({status.signal_strength}%)"
                                )
                                self.state.total_link_disables += 1
                                needs_update = True
                        elif status.signal_strength >= self.config.link_enable_signal_threshold:
                            should_be_enabled = True
                            if not link.enabled:
                                logger.info(
                                    f"Re-enabling link {link.address}:{link.port} - "
                                    f"modem {modem_id} signal recovered ({status.signal_strength}%)"
                                )
                                self.state.total_link_enables += 1
                                needs_update = True

                # Create updated link
                new_link = RISTLink(
                    address=link.address,
                    port=link.port,
                    enabled=should_be_enabled
                )
                new_links.append(new_link)

            # Apply link configuration if changed
            if needs_update:
                self._apply_link_config(new_links)

    def _apply_video_bitrate(self, new_bitrate: int) -> None:
        """
        Apply new video bitrate via hot-reload and mark config dirty.

        Args:
            new_bitrate: New video bitrate in bps
        """
        try:
            # Update via hot-reload (API)
            new_video_config = VideoConfig(
                codec=self.rist_manager.video_config.codec,
                bitrate=new_bitrate,
                width=self.rist_manager.video_config.width,
                height=self.rist_manager.video_config.height,
                framerate=self.rist_manager.video_config.framerate,
                profile=self.rist_manager.video_config.profile
            )

            success = self.rist_manager.hot_reload(video_config=new_video_config)

            if success:
                self.state.current_video_bitrate = new_bitrate
                self._config_dirty = True
                logger.debug(f"Video bitrate updated to {new_bitrate} bps")
            else:
                logger.error("Failed to apply video bitrate via hot-reload")

        except Exception as e:
            logger.error(f"Failed to apply video bitrate: {e}", exc_info=True)

    def _apply_link_config(self, new_links: List[RISTLink]) -> None:
        """
        Apply new link configuration via hot-reload and mark config dirty.

        Args:
            new_links: New list of RIST links
        """
        try:
            # Update via hot-reload (API)
            new_rist_config = RISTConfig(
                links=new_links,
                bonding_method=self.rist_manager.rist_config.bonding_method,
                sender_buffer=self.rist_manager.rist_config.sender_buffer,
                receiver_buffer=self.rist_manager.rist_config.receiver_buffer,
                reorder_section=self.rist_manager.rist_config.reorder_section,
                min_rtcp_interval=self.rist_manager.rist_config.min_rtcp_interval,
                max_rtcp_bandwidth=self.rist_manager.rist_config.max_rtcp_bandwidth,
                max_rtx_retries=self.rist_manager.rist_config.max_rtx_retries,
                stats_update_interval=self.rist_manager.rist_config.stats_update_interval
            )

            success = self.rist_manager.hot_reload(rist_config=new_rist_config)

            if success:
                self._config_dirty = True
                logger.debug(f"Link configuration updated: {len([l for l in new_links if l.enabled])} active")
            else:
                logger.error("Failed to apply link config via hot-reload")

        except Exception as e:
            logger.error(f"Failed to apply link config: {e}", exc_info=True)

    def _save_config(self) -> None:
        """Save current configuration to config.json"""
        try:
            # Read current config
            if not self.config_path.exists():
                logger.warning(f"Config file not found: {self.config_path}")
                return

            with open(self.config_path, 'r') as f:
                config = json.load(f)

            # Update RIST-related fields
            if 'rist' not in config:
                config['rist'] = {}

            # Save video bitrate
            if self.rist_manager.video_config:
                config['rist']['video_bitrate'] = self.rist_manager.video_config.bitrate

            # Save audio bitrate
            if self.rist_manager.audio_config:
                config['rist']['audio_bitrate'] = self.rist_manager.audio_config.bitrate

            # Save link configuration
            if self.rist_manager.rist_config:
                config['rist']['links'] = [
                    {
                        'address': link.address,
                        'port': link.port,
                        'enabled': link.enabled
                    }
                    for link in self.rist_manager.rist_config.links
                ]

            # Write config back
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)

            self._config_dirty = False
            self._last_config_save = time.time()
            logger.debug(f"Configuration saved to {self.config_path}")

        except Exception as e:
            logger.error(f"Failed to save config: {e}", exc_info=True)

    def get_state(self) -> AdaptiveState:
        """Get current adaptive controller state"""
        with self._lock:
            return self.state

    def update_config(self, new_config: AdaptiveConfig) -> None:
        """
        Update adaptive controller configuration.

        Args:
            new_config: New configuration
        """
        with self._lock:
            self.config = new_config
            logger.info("Adaptive controller configuration updated")


# Example usage
if __name__ == "__main__":
    import sys
    from rist_profiles import get_profile, create_rist_config_for_profile

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create RIST manager
    rist_manager = RISTManager(
        video_source="videotestsrc",
        audio_source="audiotestsrc"
    )

    # Use a profile
    profile = get_profile("high_1080p30_opus")
    rist_config = create_rist_config_for_profile(
        profile,
        links=[
            RISTLink(address="127.0.0.1", port=5004),
            RISTLink(address="127.0.0.1", port=5006),
        ]
    )

    # Configure RIST manager
    rist_manager.configure(rist_config, profile.video_config, profile.audio_config)

    # Create modem monitor (optional)
    modem_monitor = ModemMonitor()
    modem_monitor.start_monitoring(interval=5)

    # Create adaptive controller
    def on_state_update(state: AdaptiveState):
        print(f"\nAdaptive State Update:")
        print(f"  Packet Loss: {state.current_packet_loss:.2f}%")
        print(f"  Video Bitrate: {state.current_video_bitrate // 1000} kbps")
        print(f"  Active Links: {len(state.active_links)}")
        print(f"  Stats: ↑{state.total_bitrate_increases} ↓{state.total_bitrate_decreases}")

    adaptive_config = AdaptiveConfig(
        enabled=True,
        adaptive_bitrate_enabled=True,
        adaptive_links_enabled=True,
        stats_check_interval=2
    )

    controller = AdaptiveController(
        rist_manager=rist_manager,
        modem_monitor=modem_monitor,
        config_path="/tmp/test_config.json",  # Test config
        adaptive_config=adaptive_config,
        state_callback=on_state_update
    )

    # Start streaming
    if rist_manager.start():
        print("RIST streaming started")

        # Start adaptive controller
        if controller.start():
            print("Adaptive controller started")
            print("\nMonitoring adaptive behavior. Press Ctrl+C to stop.\n")

            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n\nStopping...")
                controller.stop()
                rist_manager.stop()
                modem_monitor.stop_monitoring()
        else:
            print("Failed to start adaptive controller")
            rist_manager.stop()
    else:
        print("Failed to start RIST streaming")
