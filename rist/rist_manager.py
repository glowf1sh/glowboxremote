#!/usr/bin/env python3
"""
RIST Manager - GStreamer RIST Pipeline Controller (subprocess-based)
Manages RIST streaming using gst-launch-1.0 subprocess calls.

Features:
- Dynamic pipeline configuration
- Multi-link bonding support
- FEC/ARQ configuration
- Stats monitoring via parsing
- Simple start/stop control

NO PyGObject dependencies - uses subprocess only!
"""

import subprocess
import json
import logging
import os
import signal
import time
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import threading


logger = logging.getLogger(__name__)


class BondingMethod(Enum):
    """RIST bonding methods"""
    BROADCAST = "broadcast"  # Send to all links
    ROUND_ROBIN = "round-robin"  # Alternate between links


class AudioCodec(Enum):
    """Supported audio codecs"""
    AAC = "aac"
    OPUS = "opus"


class VideoCodec(Enum):
    """Supported video codecs"""
    H264 = "h264"
    H265 = "h265"


@dataclass
class AudioConfig:
    """Audio encoding configuration"""
    codec: AudioCodec
    bitrate: int  # bits per second
    sample_rate: int = 48000
    channels: int = 2


@dataclass
class VideoConfig:
    """Video encoding configuration"""
    codec: VideoCodec
    width: int
    height: int
    framerate: int
    bitrate: int  # bits per second
    keyframe_interval: int = 60  # GOP size


@dataclass
class RISTLink:
    """RIST link configuration"""
    address: str
    port: int
    enabled: bool = True
    weight: int = 100  # For weighted bonding (0-100)


@dataclass
class RISTConfig:
    """RIST protocol configuration"""
    links: List[RISTLink]
    bonding_method: BondingMethod = BondingMethod.BROADCAST

    # RIST parameters
    sender_buffer: int = 1200  # ms
    receiver_buffer: int = 1200  # ms
    reorder_buffer: int = 25  # ms
    rtt_min: int = 50  # ms
    rtt_max: int = 500  # ms

    # FEC configuration
    fec_rows: int = 4
    fec_columns: int = 5

    # ARQ
    max_retries: int = 10


class RISTManager:
    """
    RIST streaming manager using subprocess calls to gst-launch-1.0.

    Simpler than PyGObject but no runtime pipeline modification.
    """

    def __init__(self, gstreamer_path: str = "/opt/gstreamer-1.24"):
        """
        Initialize RIST manager.

        Args:
            gstreamer_path: Path to GStreamer installation
        """
        self.gstreamer_path = gstreamer_path
        self.gst_launch = os.path.join(gstreamer_path, "bin", "gst-launch-1.0")

        # Configuration
        self.rist_config: Optional[RISTConfig] = None
        self.video_config: Optional[VideoConfig] = None
        self.audio_config: Optional[AudioConfig] = None

        # Process management
        self.process: Optional[subprocess.Popen] = None
        self.is_streaming = False

        # Error monitoring
        self.last_error: Optional[str] = None
        self.error_callback: Optional[Callable[[str], None]] = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.stop_monitoring = threading.Event()

        # Environment setup
        self._setup_environment()

        logger.info(f"RIST Manager initialized (gst-launch: {self.gst_launch})")

    def _setup_environment(self):
        """Setup GStreamer environment variables"""
        lib_path = os.path.join(self.gstreamer_path, "lib")
        lib_arch_path = os.path.join(self.gstreamer_path, "lib", "aarch64-linux-gnu")
        plugin_path = os.path.join(lib_arch_path, "gstreamer-1.0")

        # Update environment
        os.environ['PATH'] = f"{os.path.join(self.gstreamer_path, 'bin')}:{os.environ.get('PATH', '')}"
        os.environ['LD_LIBRARY_PATH'] = f"{lib_arch_path}:{lib_path}:{os.environ.get('LD_LIBRARY_PATH', '')}"
        os.environ['GST_PLUGIN_PATH'] = plugin_path

        logger.debug(f"GStreamer environment configured: {plugin_path}")

    def _parse_gst_error(self, line: str) -> Optional[str]:
        """
        Parse GStreamer error/warning messages into user-friendly errors.

        Args:
            line: Error line from stderr

        Returns:
            User-friendly error message or None if not critical
        """
        line_lower = line.lower()

        # Critical errors
        if "no space left on device" in line_lower:
            return "Speicherplatz voll - Stream kann nicht aufgezeichnet werden"
        elif "could not open resource" in line_lower or "connection refused" in line_lower:
            return "RIST-Verbindung fehlgeschlagen - Server nicht erreichbar"
        elif "internal data flow error" in line_lower:
            return "Pipeline-Fehler - Video/Audio-Quelle prüfen"
        elif "streaming stopped" in line_lower or "eos" in line_lower:
            return "RIST Stream unerwartet beendet"
        elif "not negotiated" in line_lower:
            return "Video/Audio-Format nicht unterstützt"
        elif "no such element" in line_lower or "failed to create element" in line_lower:
            return "GStreamer-Plugin fehlt - Installation prüfen"

        # Return full line for unknown errors if ERROR level
        if "error" in line_lower:
            return f"RIST Error: {line[:100]}"

        return None

    def _monitor_stderr(self):
        """
        Monitor GStreamer process stderr for errors.
        Runs in separate thread.
        """
        if not self.process:
            return

        logger.info("Starting RIST error monitor thread")

        while not self.stop_monitoring.is_set():
            if not self.process or self.process.poll() is not None:
                break

            try:
                line = self.process.stderr.readline()
                if not line:
                    break

                line_str = line.decode('utf-8', errors='ignore').strip()
                if not line_str:
                    continue

                # Log all output for debugging
                if "ERROR" in line_str or "WARN" in line_str:
                    logger.warning(f"GStreamer: {line_str}")

                # Parse errors
                error_msg = self._parse_gst_error(line_str)
                if error_msg:
                    self.last_error = error_msg
                    logger.error(f"RIST Error detected: {error_msg}")

                    if self.error_callback:
                        try:
                            self.error_callback(error_msg)
                        except Exception as e:
                            logger.error(f"Error in error_callback: {e}")

            except Exception as e:
                logger.error(f"Error in monitor thread: {e}")
                break

        logger.info("RIST error monitor thread stopped")

    def configure(
        self,
        rist_config: RISTConfig,
        video_config: Optional[VideoConfig] = None,
        audio_config: Optional[AudioConfig] = None
    ):
        """
        Configure RIST streaming.

        Args:
            rist_config: RIST protocol configuration
            video_config: Video encoding configuration (optional)
            audio_config: Audio encoding configuration (optional)
        """
        if self.is_streaming:
            raise RuntimeError("Cannot configure while streaming. Stop first.")

        self.rist_config = rist_config
        self.video_config = video_config
        self.audio_config = audio_config

        logger.info(f"RIST configured: {len(rist_config.links)} links, bonding={rist_config.bonding_method.value}")

    def _build_pipeline_command(self) -> List[str]:
        """
        Build gst-launch-1.0 command for RIST streaming.

        Returns:
            List of command arguments
        """
        if not self.rist_config:
            raise RuntimeError("RIST not configured")

        cmd = [self.gst_launch]

        # Video branch
        if self.video_config:
            video_pipeline = self._build_video_pipeline()
            cmd.extend(video_pipeline)

        # Audio branch
        if self.audio_config:
            audio_pipeline = self._build_audio_pipeline()
            if self.video_config:
                cmd.append("!")
            cmd.extend(audio_pipeline)

        # RIST sink(s)
        rist_pipeline = self._build_rist_pipeline()
        cmd.append("!")
        cmd.extend(rist_pipeline)

        logger.debug(f"Pipeline command: {' '.join(cmd)}")
        return cmd

    def _build_video_pipeline(self) -> List[str]:
        """Build video encoding pipeline elements"""
        vc = self.video_config

        elements = [
            # Video source (from v4l2 or test)
            "videotestsrc",  # TODO: Replace with actual source
            "is-live=true",
            "!",
            "video/x-raw,format=I420",
            f"width={vc.width},height={vc.height},framerate={vc.framerate}/1",
            "!",
            "videoconvert",
            "!",
        ]

        # Encoder
        if vc.codec == VideoCodec.H264:
            elements.extend([
                "x264enc" if self._has_plugin("x264enc") else "avenc_h264",
                f"bitrate={vc.bitrate // 1000}",  # x264enc wants kbps
                "tune=zerolatency",
                f"key-int-max={vc.keyframe_interval}",
                "!",
                "h264parse",
                "!",
                "rtph264pay",
            ])
        elif vc.codec == VideoCodec.H265:
            elements.extend([
                "x265enc" if self._has_plugin("x265enc") else "avenc_h265",
                f"bitrate={vc.bitrate // 1000}",
                "tune=zerolatency",
                f"key-int-max={vc.keyframe_interval}",
                "!",
                "h265parse",
                "!",
                "rtph265pay",
            ])

        return elements

    def _build_audio_pipeline(self) -> List[str]:
        """Build audio encoding pipeline elements"""
        ac = self.audio_config

        elements = [
            # Audio source (from alsa or test)
            "audiotestsrc",  # TODO: Replace with actual source
            "is-live=true",
            "!",
            "audioconvert",
            "!",
            f"audio/x-raw,rate={ac.sample_rate},channels={ac.channels}",
            "!",
        ]

        # Encoder
        if ac.codec == AudioCodec.AAC:
            elements.extend([
                "avenc_aac",
                f"bitrate={ac.bitrate}",
                "!",
                "aacparse",
                "!",
                "rtpmp4apay",
            ])
        elif ac.codec == AudioCodec.OPUS:
            elements.extend([
                "opusenc",
                f"bitrate={ac.bitrate}",
                "!",
                "opusparse",
                "!",
                "rtpopuspay",
            ])

        return elements

    def _build_rist_pipeline(self) -> List[str]:
        """Build RIST sink pipeline elements"""
        rc = self.rist_config

        # For now, simple single-link or broadcast
        if len(rc.links) == 1:
            # Single link
            link = rc.links[0]
            return [
                "ristsink",
                f"address={link.address}",
                f"port={link.port}",
                f"sender-buffer={rc.sender_buffer}",
                f"stats-update-interval=1000",
            ]
        else:
            # Multi-link bonding
            # GStreamer ristsink supports bonding via bonding-method property
            links_str = ",".join([f"{link.address}:{link.port}" for link in rc.links if link.enabled])

            return [
                "ristsink",
                f"address={links_str}",
                f"bonding-method={rc.bonding_method.value}",
                f"sender-buffer={rc.sender_buffer}",
                f"stats-update-interval=1000",
            ]

    def _has_plugin(self, plugin_name: str) -> bool:
        """Check if a GStreamer plugin is available"""
        try:
            result = subprocess.run(
                [os.path.join(self.gstreamer_path, "bin", "gst-inspect-1.0"), plugin_name],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False

    def start(self) -> bool:
        """
        Start RIST streaming.

        Returns:
            True if started successfully
        """
        if self.is_streaming:
            logger.warning("Already streaming")
            return False

        if not self.rist_config:
            raise RuntimeError("RIST not configured. Call configure() first.")

        try:
            # Build pipeline command
            cmd = self._build_pipeline_command()

            # Start process
            logger.info(f"Starting RIST stream: {' '.join(cmd[:5])}...")

            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=os.environ.copy(),
                preexec_fn=os.setsid  # Create new process group for clean kill
            )

            # Wait a bit to check if it crashes immediately
            time.sleep(1)

            if self.process.poll() is not None:
                # Process died
                stdout, stderr = self.process.communicate()
                logger.error(f"Pipeline failed to start: {stderr.decode()[:500]}")
                self.last_error = "Pipeline konnte nicht gestartet werden"
                return False

            self.is_streaming = True

            # Start error monitoring thread
            self.stop_monitoring.clear()
            self.monitor_thread = threading.Thread(target=self._monitor_stderr, daemon=True)
            self.monitor_thread.start()

            logger.info("RIST stream started")
            return True

        except Exception as e:
            logger.error(f"Failed to start RIST stream: {e}")
            self.last_error = str(e)
            return False

    def stop(self) -> bool:
        """
        Stop RIST streaming.

        Returns:
            True if stopped successfully
        """
        if not self.is_streaming or not self.process:
            logger.warning("Not streaming")
            return False

        try:
            logger.info("Stopping RIST stream...")

            # Send EOS signal (Ctrl+C equivalent)
            os.killpg(os.getpgid(self.process.pid), signal.SIGINT)

            # Stop monitor thread
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.stop_monitoring.set()
                self.monitor_thread.join(timeout=2)

            # Wait for graceful shutdown (max 5 seconds)
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill
                logger.warning("Graceful shutdown timeout, forcing kill")
                os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                self.process.wait()

            self.is_streaming = False
            self.process = None
            logger.info("RIST stream stopped")
            return True

        except Exception as e:
            logger.error(f"Failed to stop RIST stream: {e}")
            return False

    def get_status(self) -> Dict:
        """
        Get current streaming status.

        Returns:
            Status dictionary
        """
        status = {
            "is_streaming": self.is_streaming,
            "configured": self.rist_config is not None,
        }

        if self.rist_config:
            status["links"] = len(self.rist_config.links)
            status["bonding_method"] = self.rist_config.bonding_method.value

        if self.video_config:
            status["video"] = {
                "codec": self.video_config.codec.value,
                "resolution": f"{self.video_config.width}x{self.video_config.height}",
                "framerate": self.video_config.framerate,
                "bitrate": self.video_config.bitrate
            }

        if self.audio_config:
            status["audio"] = {
                "codec": self.audio_config.codec.value,
                "sample_rate": self.audio_config.sample_rate,
                "bitrate": self.audio_config.bitrate
            }

        if self.process:
            status["pid"] = self.process.pid
            status["running"] = self.process.poll() is None

        # Include last error if present
        status["error"] = self.last_error

        return status

    def update_bitrate(self, new_bitrate: int) -> bool:
        """
        Update video bitrate (requires restart with subprocess approach).

        Args:
            new_bitrate: New bitrate in bps

        Returns:
            True if updated successfully
        """
        if not self.video_config:
            return False

        logger.info(f"Updating video bitrate: {self.video_config.bitrate} -> {new_bitrate}")

        self.video_config.bitrate = new_bitrate

        # With subprocess, we need to restart
        if self.is_streaming:
            logger.warning("Bitrate update requires restart")
            self.stop()
            time.sleep(0.5)
            return self.start()

        return True


# Example usage
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create manager
    manager = RISTManager()

    # Configure
    rist_config = RISTConfig(
        links=[
            RISTLink(address="192.168.1.100", port=5004),
            RISTLink(address="192.168.2.100", port=5004),
        ],
        bonding_method=BondingMethod.BROADCAST
    )

    video_config = VideoConfig(
        codec=VideoCodec.H264,
        width=1280,
        height=720,
        framerate=30,
        bitrate=2_500_000
    )

    audio_config = AudioConfig(
        codec=AudioCodec.OPUS,
        bitrate=128_000
    )

    manager.configure(rist_config, video_config, audio_config)

    # Start
    print("\nStarting RIST stream...")
    if manager.start():
        print("✅ Stream started")
        print(json.dumps(manager.get_status(), indent=2))

        # Run for a bit
        try:
            input("\nPress Enter to stop...\n")
        except KeyboardInterrupt:
            pass

        # Stop
        print("\nStopping stream...")
        manager.stop()
    else:
        print("❌ Failed to start stream")
