import os
import sys
import uuid
import json
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import threading

sys.path.insert(0, str(Path(__file__).parent.parent))

from audio_visualizer.config_loader import ConfigLoader
from audio_visualizer.audio_processor import AudioProcessor
from audio_visualizer.visualizer_factory import VisualizerFactory
from audio_visualizer.video_renderer import VideoRenderer
from audio_visualizer.pipeline.layer_registry import LayerRegistry

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = Path(__file__).parent / 'uploads'
app.config['OUTPUT_FOLDER'] = Path(__file__).parent / 'outputs'

app.config['UPLOAD_FOLDER'].mkdir(exist_ok=True)
app.config['OUTPUT_FOLDER'].mkdir(exist_ok=True)

jobs = {}

# Known enum values for layer parameters — parsed from default.yaml comments and code
# This map is auto-enriched from the config; string values become enums if we know options
KNOWN_ENUMS = {
    'background': {
        'type': ['gradient', 'animated', 'solid'],
        'direction': ['vertical', 'horizontal', 'radial'],
        'blend_mode': ['overwrite', 'add', 'multiply', 'screen', 'normal'],
    },
    'waveform': {
        'style': ['mirror', 'filled', 'simple', 'energy'],
        'blend_mode': ['overwrite', 'add', 'multiply', 'screen', 'normal'],
    },
    'spectrum': {
        'style': ['bars', 'circular', 'wave'],
        'blend_mode': ['overwrite', 'add', 'multiply', 'screen', 'normal'],
    },
    'particles': {
        'blend_mode': ['overwrite', 'add', 'multiply', 'screen', 'normal'],
    },
    'effects': {
        'blend_mode': ['overwrite', 'add', 'multiply', 'screen', 'normal'],
    },
    'circular_waveform': {
        'style': ['mirror', 'filled', 'bars'],
        'blend_mode': ['overwrite', 'add', 'multiply', 'screen', 'normal'],
    },
    'circular_spectrum': {
        'style': ['bars', 'wave'],
        'blend_mode': ['overwrite', 'add', 'multiply', 'screen', 'normal'],
    },
    'circular_particles': {
        'blend_mode': ['overwrite', 'add', 'multiply', 'screen', 'normal'],
    },
}


def infer_param_type(key, value, layer_name):
    """Infer parameter type from default.yaml value and known enums."""
    # Check if it's a known enum
    if layer_name in KNOWN_ENUMS and key in KNOWN_ENUMS[layer_name]:
        return {
            'type': 'enum',
            'options': KNOWN_ENUMS[layer_name][key],
            'default': value,
        }

    # List of effects — special multi-select
    if key == 'effects' and isinstance(value, list) and all(isinstance(v, str) for v in value):
        return {
            'type': 'multi_enum',
            'options': ['glow', 'vignette', 'grain', 'chromatic'],
            'default': value,
        }

    # Color arrays [r, g, b]
    if isinstance(value, list) and len(value) == 3 and all(isinstance(v, (int, float)) for v in value):
        return {
            'type': 'color',
            'default': value,
        }

    # Boolean
    if isinstance(value, bool):
        return {
            'type': 'boolean',
            'default': value,
        }

    # Integer
    if isinstance(value, int):
        return {
            'type': 'integer',
            'default': value,
            'min': 0,
            'max': max(value * 5, 1000),
            'step': 1,
        }

    # Float
    if isinstance(value, float):
        # Detect 0-1 range params (opacity, smoothing, strength, decay, etc.)
        if 0.0 <= value <= 1.0 and any(hint in key for hint in (
            'opacity', 'smoothing', 'strength', 'decay', 'amount',
            'intensity', 'wave_smoothing',
        )):
            return {
                'type': 'float',
                'default': value,
                'min': 0.0,
                'max': 1.0,
                'step': 0.01,
            }
        return {
            'type': 'float',
            'default': value,
            'min': 0.0,
            'max': max(value * 5, 50.0),
            'step': round(max(value * 0.1, 0.1), 2),
        }

    # String (not in known enums) — treat as text
    if isinstance(value, str):
        return {
            'type': 'string',
            'default': value,
        }

    # Fallback
    return {
        'type': 'unknown',
        'default': value,
    }


def get_layers_metadata():
    """Parse default.yaml and build full layer metadata for the frontend."""
    config = ConfigLoader().config
    registry = LayerRegistry()
    available_layers = registry.get_available_layers()

    pipeline_config = config.get('pipeline', {})
    default_order = pipeline_config.get('order', [])

    layers_meta = {}
    for layer_name in available_layers:
        layer_defaults = pipeline_config.get(layer_name, {})
        params = {}
        for key, value in layer_defaults.items():
            params[key] = infer_param_type(key, value, layer_name)

        layers_meta[layer_name] = {
            'name': layer_name,
            'label': layer_name.replace('_', ' ').title(),
            'params': params,
        }

    return {
        'layers': layers_meta,
        'default_order': default_order,
        'video_defaults': config.get('video', {}),
        'color_defaults': config.get('visualization', {}).get('colors', {}),
    }


def parse_color(hex_color):
    hex_color = hex_color.lstrip('#')
    return [int(hex_color[i:i+2], 16) for i in (0, 2, 4)]


def process_video(job_id, audio_path, output_path, config, visualizer_type='pipeline'):
    try:
        jobs[job_id]['status'] = 'processing'
        jobs[job_id]['progress'] = 5
        jobs[job_id]['message'] = 'Loading audio...'

        audio_proc = AudioProcessor(config)
        audio_proc.load_audio(str(audio_path))

        jobs[job_id]['progress'] = 15
        jobs[job_id]['message'] = 'Creating visualization...'

        visualizer = VisualizerFactory.create(visualizer_type, config, audio_proc)

        jobs[job_id]['progress'] = 20
        jobs[job_id]['message'] = 'Rendering video...'

        render_with_progress(job_id, config, audio_proc, visualizer, str(output_path))

        jobs[job_id]['status'] = 'completed'
        jobs[job_id]['progress'] = 100
        jobs[job_id]['message'] = 'Done!'

    except Exception as e:
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['message'] = str(e)
        import traceback
        traceback.print_exc()


def render_with_progress(job_id, config, audio_proc, visualizer, output_path):
    import cv2
    import tempfile
    import subprocess

    video_config = config['video']
    width = video_config['width']
    height = video_config['height']
    fps = video_config['fps']

    total_frames = int(audio_proc.duration * fps)
    frame_duration = 1.0 / fps

    temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
    temp_path = temp_video.name
    temp_video.close()

    try:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(temp_path, fourcc, fps, (width, height))

        for i in range(total_frames):
            time_point = i * frame_duration
            frame = visualizer.render_frame(time_point)
            writer.write(frame)

            progress = 20 + int((i / total_frames) * 70)
            jobs[job_id]['progress'] = progress
            jobs[job_id]['message'] = f'Frame {i+1}/{total_frames}'

        writer.release()

        jobs[job_id]['progress'] = 95
        jobs[job_id]['message'] = 'Adding audio...'

        cmd = [
            'ffmpeg', '-y',
            '-i', temp_path,
            '-i', audio_proc.original_audio_path,
            '-c:v', 'libx264', '-preset', 'fast',
            '-c:a', 'aac', '-b:a', '192k',
            '-shortest', output_path
        ]
        subprocess.run(cmd, capture_output=True)

    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/layers')
def api_layers():
    """Return all available layers with their parameters, types, and defaults.
    Parsed directly from default.yaml — single source of truth."""
    meta = get_layers_metadata()
    return jsonify(meta)


@app.route('/upload', methods=['POST'])
def upload():
    # Support reusing audio from a previous job
    reuse_job_id = request.form.get('reuse_audio_job_id')
    if reuse_job_id and reuse_job_id in jobs:
        prev_job = jobs[reuse_job_id]
        src_audio = prev_job.get('original_audio_path') or prev_job.get('audio_path')
        if not src_audio or not os.path.exists(src_audio):
            return jsonify({'error': 'Previous audio file not found'}), 400
        job_id = str(uuid.uuid4())[:8]
        filename = prev_job.get('filename', 'audio.mp3')
        # Copy audio to new job path
        import shutil
        audio_path = app.config['UPLOAD_FOLDER'] / f"{job_id}_{filename}"
        shutil.copy2(src_audio, str(audio_path))
    else:
        if 'audio' not in request.files:
            return jsonify({'error': 'No file selected'}), 400

        file = request.files['audio']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        job_id = str(uuid.uuid4())[:8]

        filename = secure_filename(file.filename)
        audio_path = app.config['UPLOAD_FOLDER'] / f"{job_id}_{filename}"
        file.save(str(audio_path))

    # Start from default config
    config = ConfigLoader().config

    # Parse pipeline config from JSON body field
    pipeline_json = request.form.get('pipeline_config')
    if pipeline_json:
        try:
            pipeline_data = json.loads(pipeline_json)
        except json.JSONDecodeError:
            return jsonify({'error': 'Invalid pipeline config JSON'}), 400

        # Set video params
        video = pipeline_data.get('video', {})
        if video.get('width'):
            config['video']['width'] = int(video['width'])
        if video.get('height'):
            config['video']['height'] = int(video['height'])
        if video.get('fps'):
            config['video']['fps'] = int(video['fps'])

        # Set colors
        colors = pipeline_data.get('colors', {})
        if colors.get('primary'):
            config['visualization']['colors']['primary'] = parse_color(colors['primary'])
        if colors.get('secondary'):
            config['visualization']['colors']['secondary'] = parse_color(colors['secondary'])

        # Set pipeline order
        layer_order = pipeline_data.get('order', [])
        if layer_order:
            config['pipeline']['order'] = layer_order

        # Set per-layer params
        layer_params = pipeline_data.get('layer_params', {})
        for layer_name, params in layer_params.items():
            if layer_name not in config['pipeline']:
                config['pipeline'][layer_name] = {}
            for key, value in params.items():
                config['pipeline'][layer_name][key] = value
    else:
        # Fallback: legacy form fields
        config['video']['width'] = int(request.form.get('width', 1920))
        config['video']['height'] = int(request.form.get('height', 1080))
        config['video']['fps'] = int(request.form.get('fps', 30))

        if request.form.get('primary_color'):
            config['visualization']['colors']['primary'] = parse_color(request.form['primary_color'])
        if request.form.get('secondary_color'):
            config['visualization']['colors']['secondary'] = parse_color(request.form['secondary_color'])

        config['pipeline']['order'] = ['background', 'particles', 'waveform', 'spectrum', 'effects']

    # Trim audio if requested
    trim_info = pipeline_data.get('trim', {}) if pipeline_json else {}
    if trim_info and trim_info.get('start') is not None and trim_info.get('end') is not None:
        trim_start = float(trim_info['start'])
        trim_end = float(trim_info['end'])
        trimmed_path = app.config['UPLOAD_FOLDER'] / f"{job_id}_trimmed_{filename}"
        try:
            import subprocess
            duration = trim_end - trim_start
            cmd = [
                'ffmpeg', '-y',
                '-i', str(audio_path),
                '-ss', str(trim_start),
                '-t', str(duration),
                '-c', 'copy',
                str(trimmed_path)
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode == 0 and trimmed_path.exists():
                audio_path = trimmed_path
        except Exception as e:
            print(f"Trim failed, using original: {e}")

    output_path = app.config['OUTPUT_FOLDER'] / f"{job_id}_output.mp4"

    # Store config for history — keep original (untrimmed) audio path for reuse
    jobs[job_id] = {
        'status': 'queued',
        'progress': 0,
        'message': 'Queued...',
        'audio_path': str(audio_path),
        'original_audio_path': str(app.config['UPLOAD_FOLDER'] / f"{job_id}_{filename}"),
        'output_path': str(output_path),
        'filename': filename,
        'config_snapshot': {
            'video': config['video'],
            'order': config['pipeline']['order'],
            'colors': config['visualization']['colors'],
        }
    }

    thread = threading.Thread(target=process_video, args=(job_id, audio_path, output_path, config, 'pipeline'))
    thread.daemon = True
    thread.start()

    return jsonify({'job_id': job_id})


@app.route('/status/<job_id>')
def status(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    job = jobs[job_id]
    return jsonify({
        'status': job['status'],
        'progress': job['progress'],
        'message': job['message'],
        'filename': job.get('filename', ''),
        'config_snapshot': job.get('config_snapshot', {}),
    })


@app.route('/download/<job_id>')
def download(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404

    job = jobs[job_id]
    if job['status'] != 'completed':
        return jsonify({'error': 'Not ready'}), 400

    return send_file(
        job['output_path'],
        mimetype='video/mp4',
        as_attachment=True,
        download_name='visualization.mp4'
    )


@app.route('/preview/<job_id>')
def preview(job_id):
    """Serve video inline for preview (not as attachment)."""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404

    job = jobs[job_id]
    if job['status'] != 'completed':
        return jsonify({'error': 'Not ready'}), 400

    return send_file(
        job['output_path'],
        mimetype='video/mp4',
        as_attachment=False,
    )


@app.route('/audio/<job_id>')
def serve_audio(job_id):
    """Serve the uploaded audio file for a given job (used by restore)."""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404

    job = jobs[job_id]
    audio_path = job.get('original_audio_path') or job.get('audio_path')
    if not audio_path or not os.path.exists(audio_path):
        return jsonify({'error': 'Audio file not found'}), 404

    return send_file(audio_path, as_attachment=False)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
