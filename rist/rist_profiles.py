#!/usr/bin/env python3
"""
RIST Streaming Profiles - Platform-Optimized (Twitch, YouTube)

Separate Video and Audio profiles for maximum flexibility.
Users can combine any video profile with any audio profile.

Video Profiles: 20 (Twitch + YouTube, H.264/H.265, 30/60fps)
Audio Profiles: 6 (AAC + Opus, various bitrates)
Total Combinations: 120 possible configurations
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
from rist_manager import (
    AudioCodec, VideoCodec, AudioConfig, VideoConfig,
    RISTConfig, RISTLink, BondingMethod
)


class Platform(Enum):
    """Streaming platform"""
    TWITCH = "twitch"
    YOUTUBE = "youtube"
    GENERIC = "generic"


class ProfileCategory(Enum):
    """Profile category"""
    TWITCH_1080P = "twitch_1080p"
    TWITCH_1440P_BETA = "twitch_1440p_beta"
    YOUTUBE_1080P = "youtube_1080p"
    YOUTUBE_1440P = "youtube_1440p"
    YOUTUBE_4K = "youtube_4k"
    AUDIO = "audio"


@dataclass
class VideoProfile:
    """Video encoding profile"""
    id: str
    name: str
    description: str
    platform: Platform
    category: ProfileCategory
    codec: VideoCodec
    width: int
    height: int
    framerate: int
    bitrate: int  # bits per second
    keyframe_interval: int = 60  # GOP size (2 seconds for 30fps, 120 frames for 60fps)


@dataclass
class AudioProfile:
    """Audio encoding profile"""
    id: str
    name: str
    description: str
    codec: AudioCodec
    bitrate: int  # bits per second
    sample_rate: int = 48000
    channels: int = 2


# =============================================================================
# VIDEO PROFILES - TWITCH
# =============================================================================

# Twitch 1080p (Standard)
TWITCH_1080P_30_H264 = VideoProfile(
    id="twitch_1080p30_h264",
    name="Twitch 1080p30 (H.264)",
    description="Twitch 1080p 30fps with H.264 (6 Mbps recommended)",
    platform=Platform.TWITCH,
    category=ProfileCategory.TWITCH_1080P,
    codec=VideoCodec.H264,
    width=1920,
    height=1080,
    framerate=30,
    bitrate=6_000_000,  # 6 Mbps
    keyframe_interval=60
)

TWITCH_1080P_30_H265 = VideoProfile(
    id="twitch_1080p30_h265",
    name="Twitch 1080p30 (H.265)",
    description="Twitch 1080p 30fps with H.265 (6 Mbps)",
    platform=Platform.TWITCH,
    category=ProfileCategory.TWITCH_1080P,
    codec=VideoCodec.H265,
    width=1920,
    height=1080,
    framerate=30,
    bitrate=6_000_000,
    keyframe_interval=60
)

TWITCH_1080P_60_H264 = VideoProfile(
    id="twitch_1080p60_h264",
    name="Twitch 1080p60 (H.264)",
    description="Twitch 1080p 60fps with H.264 (6 Mbps recommended)",
    platform=Platform.TWITCH,
    category=ProfileCategory.TWITCH_1080P,
    codec=VideoCodec.H264,
    width=1920,
    height=1080,
    framerate=60,
    bitrate=6_000_000,
    keyframe_interval=120
)

TWITCH_1080P_60_H265 = VideoProfile(
    id="twitch_1080p60_h265",
    name="Twitch 1080p60 (H.265)",
    description="Twitch 1080p 60fps with H.265 (6 Mbps)",
    platform=Platform.TWITCH,
    category=ProfileCategory.TWITCH_1080P,
    codec=VideoCodec.H265,
    width=1920,
    height=1080,
    framerate=60,
    bitrate=6_000_000,
    keyframe_interval=120
)

# Twitch 1440p (Beta - Enhanced Broadcasting)
TWITCH_1440P_30_H264 = VideoProfile(
    id="twitch_1440p30_h264",
    name="Twitch 1440p30 (H.264) Beta",
    description="Twitch 2K 30fps with H.264 - Beta (7.5 Mbps)",
    platform=Platform.TWITCH,
    category=ProfileCategory.TWITCH_1440P_BETA,
    codec=VideoCodec.H264,
    width=2560,
    height=1440,
    framerate=30,
    bitrate=7_500_000,  # 7.5 Mbps
    keyframe_interval=60
)

TWITCH_1440P_30_H265 = VideoProfile(
    id="twitch_1440p30_h265",
    name="Twitch 1440p30 (H.265) Beta",
    description="Twitch 2K 30fps with H.265 HEVC - Beta (9 Mbps)",
    platform=Platform.TWITCH,
    category=ProfileCategory.TWITCH_1440P_BETA,
    codec=VideoCodec.H265,
    width=2560,
    height=1440,
    framerate=30,
    bitrate=9_000_000,  # 9 Mbps
    keyframe_interval=60
)

TWITCH_1440P_60_H264 = VideoProfile(
    id="twitch_1440p60_h264",
    name="Twitch 1440p60 (H.264) Beta",
    description="Twitch 2K 60fps with H.264 - Beta (7.5 Mbps)",
    platform=Platform.TWITCH,
    category=ProfileCategory.TWITCH_1440P_BETA,
    codec=VideoCodec.H264,
    width=2560,
    height=1440,
    framerate=60,
    bitrate=7_500_000,
    keyframe_interval=120
)

TWITCH_1440P_60_H265 = VideoProfile(
    id="twitch_1440p60_h265",
    name="Twitch 1440p60 (H.265) Beta",
    description="Twitch 2K 60fps with H.265 HEVC - Beta (9 Mbps)",
    platform=Platform.TWITCH,
    category=ProfileCategory.TWITCH_1440P_BETA,
    codec=VideoCodec.H265,
    width=2560,
    height=1440,
    framerate=60,
    bitrate=9_000_000,
    keyframe_interval=120
)

# =============================================================================
# VIDEO PROFILES - YOUTUBE
# =============================================================================

# YouTube 1080p
YOUTUBE_1080P_30_H264 = VideoProfile(
    id="youtube_1080p30_h264",
    name="YouTube 1080p30 (H.264)",
    description="YouTube 1080p 30fps with H.264 (5 Mbps)",
    platform=Platform.YOUTUBE,
    category=ProfileCategory.YOUTUBE_1080P,
    codec=VideoCodec.H264,
    width=1920,
    height=1080,
    framerate=30,
    bitrate=5_000_000,  # 5 Mbps (mid-range)
    keyframe_interval=60
)

YOUTUBE_1080P_30_H265 = VideoProfile(
    id="youtube_1080p30_h265",
    name="YouTube 1080p30 (H.265)",
    description="YouTube 1080p 30fps with H.265 (5 Mbps)",
    platform=Platform.YOUTUBE,
    category=ProfileCategory.YOUTUBE_1080P,
    codec=VideoCodec.H265,
    width=1920,
    height=1080,
    framerate=30,
    bitrate=5_000_000,
    keyframe_interval=60
)

YOUTUBE_1080P_60_H264 = VideoProfile(
    id="youtube_1080p60_h264",
    name="YouTube 1080p60 (H.264)",
    description="YouTube 1080p 60fps with H.264 (7 Mbps)",
    platform=Platform.YOUTUBE,
    category=ProfileCategory.YOUTUBE_1080P,
    codec=VideoCodec.H264,
    width=1920,
    height=1080,
    framerate=60,
    bitrate=7_000_000,  # 7 Mbps
    keyframe_interval=120
)

YOUTUBE_1080P_60_H265 = VideoProfile(
    id="youtube_1080p60_h265",
    name="YouTube 1080p60 (H.265)",
    description="YouTube 1080p 60fps with H.265 (7 Mbps)",
    platform=Platform.YOUTUBE,
    category=ProfileCategory.YOUTUBE_1080P,
    codec=VideoCodec.H265,
    width=1920,
    height=1080,
    framerate=60,
    bitrate=7_000_000,
    keyframe_interval=120
)

# YouTube 1440p (2K)
YOUTUBE_1440P_30_H264 = VideoProfile(
    id="youtube_1440p30_h264",
    name="YouTube 1440p30 (H.264)",
    description="YouTube 2K 30fps with H.264 (10 Mbps)",
    platform=Platform.YOUTUBE,
    category=ProfileCategory.YOUTUBE_1440P,
    codec=VideoCodec.H264,
    width=2560,
    height=1440,
    framerate=30,
    bitrate=10_000_000,  # 10 Mbps
    keyframe_interval=60
)

YOUTUBE_1440P_30_H265 = VideoProfile(
    id="youtube_1440p30_h265",
    name="YouTube 1440p30 (H.265)",
    description="YouTube 2K 30fps with H.265 (10 Mbps)",
    platform=Platform.YOUTUBE,
    category=ProfileCategory.YOUTUBE_1440P,
    codec=VideoCodec.H265,
    width=2560,
    height=1440,
    framerate=30,
    bitrate=10_000_000,
    keyframe_interval=60
)

YOUTUBE_1440P_60_H264 = VideoProfile(
    id="youtube_1440p60_h264",
    name="YouTube 1440p60 (H.264)",
    description="YouTube 2K 60fps with H.264 (15 Mbps)",
    platform=Platform.YOUTUBE,
    category=ProfileCategory.YOUTUBE_1440P,
    codec=VideoCodec.H264,
    width=2560,
    height=1440,
    framerate=60,
    bitrate=15_000_000,  # 15 Mbps
    keyframe_interval=120
)

YOUTUBE_1440P_60_H265 = VideoProfile(
    id="youtube_1440p60_h265",
    name="YouTube 1440p60 (H.265)",
    description="YouTube 2K 60fps with H.265 (15 Mbps)",
    platform=Platform.YOUTUBE,
    category=ProfileCategory.YOUTUBE_1440P,
    codec=VideoCodec.H265,
    width=2560,
    height=1440,
    framerate=60,
    bitrate=15_000_000,
    keyframe_interval=120
)

# YouTube 4K (2160p)
YOUTUBE_4K_30_H264 = VideoProfile(
    id="youtube_4k30_h264",
    name="YouTube 4K30 (H.264)",
    description="YouTube 4K 30fps with H.264 (20 Mbps)",
    platform=Platform.YOUTUBE,
    category=ProfileCategory.YOUTUBE_4K,
    codec=VideoCodec.H264,
    width=3840,
    height=2160,
    framerate=30,
    bitrate=20_000_000,  # 20 Mbps
    keyframe_interval=60
)

YOUTUBE_4K_30_H265 = VideoProfile(
    id="youtube_4k30_h265",
    name="YouTube 4K30 (H.265)",
    description="YouTube 4K 30fps with H.265 (20 Mbps)",
    platform=Platform.YOUTUBE,
    category=ProfileCategory.YOUTUBE_4K,
    codec=VideoCodec.H265,
    width=3840,
    height=2160,
    framerate=30,
    bitrate=20_000_000,
    keyframe_interval=60
)

YOUTUBE_4K_60_H264 = VideoProfile(
    id="youtube_4k60_h264",
    name="YouTube 4K60 (H.264)",
    description="YouTube 4K 60fps with H.264 (35 Mbps)",
    platform=Platform.YOUTUBE,
    category=ProfileCategory.YOUTUBE_4K,
    codec=VideoCodec.H264,
    width=3840,
    height=2160,
    framerate=60,
    bitrate=35_000_000,  # 35 Mbps
    keyframe_interval=120
)

YOUTUBE_4K_60_H265 = VideoProfile(
    id="youtube_4k60_h265",
    name="YouTube 4K60 (H.265)",
    description="YouTube 4K 60fps with H.265 (35 Mbps)",
    platform=Platform.YOUTUBE,
    category=ProfileCategory.YOUTUBE_4K,
    codec=VideoCodec.H265,
    width=3840,
    height=2160,
    framerate=60,
    bitrate=35_000_000,
    keyframe_interval=120
)

# =============================================================================
# AUDIO PROFILES
# =============================================================================

AUDIO_AAC_128 = AudioProfile(
    id="aac_128k",
    name="AAC 128 kbps",
    description="AAC audio at 128 kbps (good quality)",
    codec=AudioCodec.AAC,
    bitrate=128_000,
    sample_rate=48000,
    channels=2
)

AUDIO_AAC_192 = AudioProfile(
    id="aac_192k",
    name="AAC 192 kbps",
    description="AAC audio at 192 kbps (high quality)",
    codec=AudioCodec.AAC,
    bitrate=192_000,
    sample_rate=48000,
    channels=2
)

AUDIO_AAC_256 = AudioProfile(
    id="aac_256k",
    name="AAC 256 kbps",
    description="AAC audio at 256 kbps (broadcast quality)",
    codec=AudioCodec.AAC,
    bitrate=256_000,
    sample_rate=48000,
    channels=2
)

AUDIO_OPUS_96 = AudioProfile(
    id="opus_96k",
    name="Opus 96 kbps",
    description="Opus audio at 96 kbps (good quality, low latency)",
    codec=AudioCodec.OPUS,
    bitrate=96_000,
    sample_rate=48000,
    channels=2
)

AUDIO_OPUS_128 = AudioProfile(
    id="opus_128k",
    name="Opus 128 kbps",
    description="Opus audio at 128 kbps (high quality, low latency)",
    codec=AudioCodec.OPUS,
    bitrate=128_000,
    sample_rate=48000,
    channels=2
)

AUDIO_OPUS_192 = AudioProfile(
    id="opus_192k",
    name="Opus 192 kbps",
    description="Opus audio at 192 kbps (broadcast quality, low latency)",
    codec=AudioCodec.OPUS,
    bitrate=192_000,
    sample_rate=48000,
    channels=2
)

# =============================================================================
# PROFILE COLLECTIONS
# =============================================================================

ALL_VIDEO_PROFILES = [
    # Twitch 1080p
    TWITCH_1080P_30_H264,
    TWITCH_1080P_30_H265,
    TWITCH_1080P_60_H264,
    TWITCH_1080P_60_H265,
    # Twitch 1440p Beta
    TWITCH_1440P_30_H264,
    TWITCH_1440P_30_H265,
    TWITCH_1440P_60_H264,
    TWITCH_1440P_60_H265,
    # YouTube 1080p
    YOUTUBE_1080P_30_H264,
    YOUTUBE_1080P_30_H265,
    YOUTUBE_1080P_60_H264,
    YOUTUBE_1080P_60_H265,
    # YouTube 1440p
    YOUTUBE_1440P_30_H264,
    YOUTUBE_1440P_30_H265,
    YOUTUBE_1440P_60_H264,
    YOUTUBE_1440P_60_H265,
    # YouTube 4K
    YOUTUBE_4K_30_H264,
    YOUTUBE_4K_30_H265,
    YOUTUBE_4K_60_H264,
    YOUTUBE_4K_60_H265,
]

ALL_AUDIO_PROFILES = [
    AUDIO_AAC_128,
    AUDIO_AAC_192,
    AUDIO_AAC_256,
    AUDIO_OPUS_96,
    AUDIO_OPUS_128,
    AUDIO_OPUS_192,
]

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_video_profile(profile_id: str) -> Optional[VideoProfile]:
    """Get video profile by ID"""
    for profile in ALL_VIDEO_PROFILES:
        if profile.id == profile_id:
            return profile
    return None


def get_audio_profile(profile_id: str) -> Optional[AudioProfile]:
    """Get audio profile by ID"""
    for profile in ALL_AUDIO_PROFILES:
        if profile.id == profile_id:
            return profile
    return None


def get_all_video_profiles() -> List[VideoProfile]:
    """Get all video profiles"""
    return ALL_VIDEO_PROFILES


def get_all_audio_profiles() -> List[AudioProfile]:
    """Get all audio profiles"""
    return ALL_AUDIO_PROFILES


def get_video_profiles_by_platform(platform: Platform) -> List[VideoProfile]:
    """Get video profiles filtered by platform"""
    return [p for p in ALL_VIDEO_PROFILES if p.platform == platform]


def get_video_profiles_by_category(category: ProfileCategory) -> List[VideoProfile]:
    """Get video profiles filtered by category"""
    return [p for p in ALL_VIDEO_PROFILES if p.category == category]


def create_stream_config(
    video_profile_id: str,
    audio_profile_id: str,
    links: List[RISTLink],
    bonding_method: BondingMethod = BondingMethod.BROADCAST
) -> tuple[Optional[RISTConfig], Optional[VideoConfig], Optional[AudioConfig]]:
    """
    Create RIST configuration from video and audio profile IDs.

    Args:
        video_profile_id: Video profile ID
        audio_profile_id: Audio profile ID
        links: RIST links
        bonding_method: Bonding method

    Returns:
        Tuple of (rist_config, video_config, audio_config) or (None, None, None) if invalid
    """
    video_profile = get_video_profile(video_profile_id)
    audio_profile = get_audio_profile(audio_profile_id)

    if not video_profile or not audio_profile:
        return None, None, None

    # Create RIST config
    rist_config = RISTConfig(
        links=links,
        bonding_method=bonding_method
    )

    # Create video config
    video_config = VideoConfig(
        codec=video_profile.codec,
        width=video_profile.width,
        height=video_profile.height,
        framerate=video_profile.framerate,
        bitrate=video_profile.bitrate,
        keyframe_interval=video_profile.keyframe_interval
    )

    # Create audio config
    audio_config = AudioConfig(
        codec=audio_profile.codec,
        bitrate=audio_profile.bitrate,
        sample_rate=audio_profile.sample_rate,
        channels=audio_profile.channels
    )

    return rist_config, video_config, audio_config


# Example usage
if __name__ == "__main__":
    print("=== RIST Streaming Profiles ===\n")

    print(f"Video Profiles: {len(ALL_VIDEO_PROFILES)}")
    print(f"Audio Profiles: {len(ALL_AUDIO_PROFILES)}")
    print(f"Total Combinations: {len(ALL_VIDEO_PROFILES) * len(ALL_AUDIO_PROFILES)}\n")

    print("--- Twitch Profiles ---")
    twitch_profiles = get_video_profiles_by_platform(Platform.TWITCH)
    for p in twitch_profiles:
        print(f"  {p.id}: {p.name} ({p.bitrate/1_000_000:.1f} Mbps)")

    print("\n--- YouTube Profiles ---")
    youtube_profiles = get_video_profiles_by_platform(Platform.YOUTUBE)
    for p in youtube_profiles:
        print(f"  {p.id}: {p.name} ({p.bitrate/1_000_000:.1f} Mbps)")

    print("\n--- Audio Profiles ---")
    for p in ALL_AUDIO_PROFILES:
        print(f"  {p.id}: {p.name}")

    print("\n--- Example Configuration ---")
    rist_config, video_config, audio_config = create_stream_config(
        "youtube_1080p60_h265",
        "opus_128k",
        [RISTLink(address="192.168.1.100", port=5004)]
    )
    print(f"Video: {video_config.width}x{video_config.height}@{video_config.framerate}fps")
    print(f"       {video_config.codec.value} {video_config.bitrate/1_000_000:.1f} Mbps")
    print(f"Audio: {audio_config.codec.value} {audio_config.bitrate/1000} kbps")
