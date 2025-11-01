#!/usr/bin/env python3
"""
BelaBox REST API Server
Provides HTTP REST API endpoints for BelaBox control and RIST Add-on
"""

import json
import os
import sys
import logging
import io

from flask import Flask, request, jsonify
from belabox_client import BelaBoxClient

# Add RIST modules to path
sys.path.insert(0, '/opt/glowf1sh_belabox_rist')

# Import RIST modules
try:
    from rist_manager import RISTManager, RISTConfig, RISTLink, AudioConfig, VideoConfig, AudioCodec, VideoCodec, BondingMethod
    from rist_profiles import get_all_video_profiles, get_all_audio_profiles, get_video_profile, get_audio_profile, create_stream_config
    from adaptive_controller import AdaptiveController, AdaptiveConfig
    RIST_AVAILABLE = True
except ImportError as e:
    logging.warning(f"RIST modules not available: {e}")
    RIST_AVAILABLE = False

# Load config
CONFIG_FILE = '/opt/glowf1sh-remote/config/config.json'

def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def save_config(cfg):
    """Save config to file"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)

def generate_box_id():
    """Generate unique box ID: gfbox-{word}-{3-digit-number}"""
    import random

    # Word dictionary (German animals, colors, objects)
    words = [
        'tiger', 'löwe', 'falke', 'adler', 'wolf', 'bär', 'luchs', 'fuchs',
        'rabe', 'eule', 'hai', 'orca', 'delphin', 'gepard', 'panther', 'puma',
        'rot', 'blau', 'grün', 'gold', 'silber', 'bronze', 'violett', 'orange',
        'stern', 'mond', 'sonne', 'komet', 'meteor', 'nova', 'orion', 'sirius',
        'berg', 'fluss', 'see', 'wald', 'sturm', 'blitz', 'donner', 'nebel',
        'eisen', 'stahl', 'titan', 'kobalt', 'chrom', 'magnet', 'quarz', 'jade'
    ]

    word = random.choice(words)
    number = random.randint(0, 999)

    return f"gfbox-{word}-{number:03d}"

config = load_config()

# Generate box_id if not set
if not config.get('box_id'):
    config['box_id'] = generate_box_id()
    save_config(config)
    logging.info(f"Generated new box_id: {config['box_id']}")

# Initialize Flask app
app = Flask(__name__)

# Initialize BelaBox client with auth token file
auth_token_file = config.get('belabox_auth_token_file', '/opt/belaUI/auth_tokens.json')
client = BelaBoxClient(auth_token_file)

# Initialize RIST components (if available)
rist_manager = None
adaptive_controller = None

if RIST_AVAILABLE:
    try:
        rist_manager = RISTManager(gstreamer_path="/opt/gstreamer-1.24")
        # adaptive_controller = AdaptiveController(rist_manager)  # Can be enabled later if needed
        logging.info("RIST components initialized")
    except Exception as e:
        logging.error(f"Failed to initialize RIST components: {e}")
        RIST_AVAILABLE = False


@app.route('/start', methods=['POST'])
def start_stream():
    """Start streaming"""
    try:
        result = client.start()
        if result.get('success'):
            return jsonify({
                'success': True,
                'message': 'Stream started successfully'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Unknown error')
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/stop', methods=['POST'])
def stop_stream():
    """Stop streaming"""
    try:
        result = client.stop()
        if result.get('success'):
            return jsonify({
                'success': True,
                'message': 'Stream stopped successfully'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Unknown error')
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/status', methods=['GET'])
def get_status():
    """Get streaming status"""
    try:
        result = client.get_status()
        if result.get('success'):
            return jsonify({
                'success': True,
                'is_streaming': result.get('is_streaming', False),
                'status': result.get('status', {}),
                'netif': result.get('netif', {}),
                'notifications': result.get('notifications', []),
                'streaming_mode': result.get('streaming_mode', 'srtla')
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Unknown error')
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/config', methods=['GET'])
def get_config():
    """Get current configuration"""
    try:
        result = client.get_config()
        if result.get('success'):
            return jsonify({
                'success': True,
                'config': result.get('config', {})
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Unknown error')
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/config', methods=['PUT'])
def update_config():
    """Update configuration"""
    try:
        if not request.is_json:
            return jsonify({
                'success': False,
                'error': 'Content-Type must be application/json'
            }), 400

        config_updates = request.get_json()

        if not config_updates:
            return jsonify({
                'success': False,
                'error': 'No configuration data provided'
            }), 400

        result = client.update_config(config_updates)
        if result.get('success'):
            return jsonify({
                'success': True,
                'message': 'Configuration updated successfully'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Unknown error')
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'success': True,
        'service': 'belabox-api',
        'status': 'running',
        'cloud_api_key': config.get('cloud_api_key', 'not-set')
    }), 200


# ============================================================================
# RIST Add-on Endpoints (Direct Implementation)
# ============================================================================

@app.route('/rist/start', methods=['POST'])
def rist_start():
    """Start RIST streaming with separate video and audio profile selection"""
    if not RIST_AVAILABLE or not rist_manager:
        return jsonify({
            'success': False,
            'error': 'RIST not available'
        }), 503

    try:
        data = request.get_json() if request.is_json else {}

        video_profile_id = data.get('video_profile_id')
        audio_profile_id = data.get('audio_profile_id')
        links = data.get('links', [])
        bonding_method = data.get('bonding_method', 'broadcast')

        if not video_profile_id:
            return jsonify({
                'success': False,
                'error': 'video_profile_id required'
            }), 400

        if not audio_profile_id:
            return jsonify({
                'success': False,
                'error': 'audio_profile_id required'
            }), 400

        if not links:
            return jsonify({
                'success': False,
                'error': 'At least one link required'
            }), 400

        # Get video profile to check if it's premium
        video_profile = get_video_profile(video_profile_id)
        if not video_profile:
            return jsonify({
                'success': False,
                'error': f'Video profile not found: {video_profile_id}'
            }), 404

        # SECURITY CHECK: If profile is premium, validate license
        if video_profile.is_premium:
            license_key = config.get('license_key')

            if not license_key:
                return jsonify({
                    'success': False,
                    'error': 'Premium profile requires license key',
                    'profile': video_profile_id,
                    'upgrade_url': 'https://cloud.gl0w.bot/upgrade'
                }), 403

            # Check if license has RIST_PREMIUM feature
            if pipeline_sync:
                has_premium = pipeline_sync.check_license_feature(license_key, 'RIST_PREMIUM')

                if not has_premium:
                    return jsonify({
                        'success': False,
                        'error': 'RIST Premium license required for this profile',
                        'profile': video_profile_id,
                        'upgrade_url': 'https://cloud.gl0w.bot/upgrade'
                    }), 403
            else:
                # No pipeline_sync available, deny premium access
                return jsonify({
                    'success': False,
                    'error': 'License validation unavailable'
                }), 503

        # Create RIST links
        rist_links = [RISTLink(address=link['address'], port=link['port']) for link in links]

        # Create stream config from separate video and audio profiles
        rist_config, video_config, audio_config = create_stream_config(
            video_profile_id,
            audio_profile_id,
            rist_links,
            BondingMethod(bonding_method)
        )

        if not rist_config or not video_config or not audio_config:
            return jsonify({
                'success': False,
                'error': 'Invalid video or audio profile'
            }), 404

        # Configure and start
        rist_manager.configure(rist_config, video_config, audio_config)

        if rist_manager.start():
            return jsonify({
                'success': True,
                'message': 'RIST stream started',
                'video_profile': video_profile_id,
                'audio_profile': audio_profile_id
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to start stream'
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/rist/stop', methods=['POST'])
def rist_stop():
    """Stop RIST streaming"""
    if not RIST_AVAILABLE or not rist_manager:
        return jsonify({
            'success': False,
            'error': 'RIST not available'
        }), 503

    try:
        if rist_manager.stop():
            return jsonify({
                'success': True,
                'message': 'RIST stream stopped'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Stream was not running'
            }), 400

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/rist/config', methods=['POST'])
def rist_update_config():
    """Update RIST configuration (save to config file)"""
    try:
        if not request.is_json:
            return jsonify({
                'success': False,
                'error': 'Content-Type must be application/json'
            }), 400

        rist_config = request.get_json()

        if not rist_config:
            return jsonify({
                'success': False,
                'error': 'No configuration data provided'
            }), 400

        # Save RIST config via belabox_client
        result = client.save_rist_config(rist_config)

        if result.get('success'):
            return jsonify(result), 200
        else:
            return jsonify(result), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/rist/status', methods=['GET'])
def rist_status():
    """Get RIST streaming status"""
    if not RIST_AVAILABLE or not rist_manager:
        return jsonify({
            'success': False,
            'error': 'RIST not available'
        }), 503

    try:
        status = rist_manager.get_status()
        return jsonify({
            'success': True,
            'status': status
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/rist/profiles', methods=['GET'])
def rist_list_all_profiles():
    """List all available video and audio profiles (overview)"""
    if not RIST_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'RIST not available'
        }), 503

    try:
        video_profiles = get_all_video_profiles()
        audio_profiles = get_all_audio_profiles()

        return jsonify({
            'success': True,
            'video_profiles': len(video_profiles),
            'audio_profiles': len(audio_profiles),
            'total_combinations': len(video_profiles) * len(audio_profiles),
            'endpoints': {
                'video_profiles': '/rist/profiles/video',
                'audio_profiles': '/rist/profiles/audio'
            }
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/rist/profiles/video', methods=['GET'])
def rist_list_video_profiles():
    """List available video profiles"""
    if not RIST_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'RIST not available'
        }), 503

    try:
        profiles = get_all_video_profiles()
        profiles_data = [
            {
                'id': p.id,
                'name': p.name,
                'description': p.description,
                'platform': p.platform.value,
                'category': p.category.value,
                'codec': p.codec.value,
                'resolution': f"{p.width}x{p.height}",
                'width': p.width,
                'height': p.height,
                'framerate': p.framerate,
                'bitrate': p.bitrate,
                'keyframe_interval': p.keyframe_interval,
                'is_premium': p.is_premium
            }
            for p in profiles
        ]

        return jsonify({
            'success': True,
            'count': len(profiles_data),
            'profiles': profiles_data
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/rist/profiles/audio', methods=['GET'])
def rist_list_audio_profiles():
    """List available audio profiles"""
    if not RIST_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'RIST not available'
        }), 503

    try:
        profiles = get_all_audio_profiles()
        profiles_data = [
            {
                'id': p.id,
                'name': p.name,
                'description': p.description,
                'codec': p.codec.value,
                'bitrate': p.bitrate,
                'sample_rate': p.sample_rate,
                'channels': p.channels
            }
            for p in profiles
        ]

        return jsonify({
            'success': True,
            'count': len(profiles_data),
            'profiles': profiles_data
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/rist/profiles/video/<profile_id>', methods=['GET'])
def rist_get_video_profile(profile_id):
    """Get specific video profile"""
    if not RIST_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'RIST not available'
        }), 503

    try:
        profile = get_video_profile(profile_id)
        if not profile:
            return jsonify({
                'success': False,
                'error': f'Video profile not found: {profile_id}'
            }), 404

        return jsonify({
            'success': True,
            'profile': {
                'id': profile.id,
                'name': profile.name,
                'description': profile.description,
                'platform': profile.platform.value,
                'category': profile.category.value,
                'codec': profile.codec.value,
                'resolution': f"{profile.width}x{profile.height}",
                'width': profile.width,
                'height': profile.height,
                'framerate': profile.framerate,
                'bitrate': profile.bitrate,
                'keyframe_interval': profile.keyframe_interval,
                'is_premium': profile.is_premium
            }
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/rist/profiles/audio/<profile_id>', methods=['GET'])
def rist_get_audio_profile(profile_id):
    """Get specific audio profile"""
    if not RIST_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'RIST not available'
        }), 503

    try:
        profile = get_audio_profile(profile_id)
        if not profile:
            return jsonify({
                'success': False,
                'error': f'Audio profile not found: {profile_id}'
            }), 404

        return jsonify({
            'success': True,
            'profile': {
                'id': profile.id,
                'name': profile.name,
                'description': profile.description,
                'codec': profile.codec.value,
                'bitrate': profile.bitrate,
                'sample_rate': profile.sample_rate,
                'channels': profile.channels
            }
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500




@app.route('/rist/profiles/sync', methods=['POST'])
def rist_sync_profiles():
    """Manually trigger profile sync from license server"""
    if not RIST_AVAILABLE or not pipeline_sync:
        return jsonify({
            'success': False,
            'error': 'RIST not available'
        }), 503

    try:
        # Get license key from config
        license_key = config.get('license_key')

        # Sync profiles
        success, msg = pipeline_sync.sync_profiles(license_key)

        if success:
            # Reload profiles in memory
            try:
                from rist_profiles import reload_profiles
                reload_profiles()
            except Exception as e:
                logging.error(f"Failed to reload profiles: {e}")

            return jsonify({
                'success': True,
                'message': msg
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': msg
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/rist/license', methods=['GET'])
def rist_license_info():
    """Get license information including premium status"""
    if not RIST_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'RIST not available'
        }), 503

    try:
        # Get license key from config
        license_key = config.get('license_key')

        # Default to no premium
        has_premium = False

        if license_key and pipeline_sync:
            # Check if user has premium license
            has_premium = pipeline_sync.check_license_feature(license_key, 'RIST_PREMIUM')

        return jsonify({
            'success': True,
            'has_premium': has_premium,
            'license_key_configured': bool(license_key)
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'has_premium': False
        }), 500


if __name__ == '__main__':
    port = config.get('api_port', 3000)

    # Configure Flask for production mode
    import os
    import sys
    import logging
    os.environ['FLASK_ENV'] = 'production'

    # Patch click.secho which Flask uses for the warning
    import click
    original_secho = click.secho

    def filtered_secho(text=None, **kwargs):
        if text and isinstance(text, str):
            if 'development server' in text.lower() or 'production deployment' in text.lower() or 'wsgi server' in text.lower():
                return
        return original_secho(text, **kwargs)

    click.secho = filtered_secho

    # Filter werkzeug logger warnings
    class WerkzeugWarningFilter(logging.Filter):
        def filter(self, record):
            msg = record.getMessage().lower()
            return not ('development server' in msg or 'production deployment' in msg or 'wsgi server' in msg)

    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.addFilter(WerkzeugWarningFilter())

    print(f"Starting BelaBox REST API on port {port}")
    print(f"Cloud API Key: {config.get('cloud_api_key', 'not-set')}")
    print(f"RIST Add-on: {'Available' if RIST_AVAILABLE else 'Not available'}")
    print(f"Box ID: {config.get('box_id', 'not-set')}")

    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
