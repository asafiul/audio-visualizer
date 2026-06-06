import os
import sys
import uuid
import json
import time as _time
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import threading

sys.path.insert(0, str(Path(__file__).parent.parent))

from audio_visualizer.config_loader import ConfigLoader
from audio_visualizer.audio_processor import AudioProcessor
from audio_visualizer.visualizer_factory import VisualizerFactory
# from audio_visualizer.video_renderer import VideoRenderer
from audio_visualizer.pipeline.layer_registry import LayerRegistry

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = Path(__file__).parent / 'uploads'
app.config['OUTPUT_FOLDER'] = Path(__file__).parent / 'outputs'
app.config['SAMPLES_FOLDER'] = Path(__file__).parent / 'samples'

app.config['UPLOAD_FOLDER'].mkdir(exist_ok=True)
app.config['OUTPUT_FOLDER'].mkdir(exist_ok=True)
app.config['SAMPLES_FOLDER'].mkdir(exist_ok=True)

jobs = {}


class CancelledError(Exception):
    """Raised when a render job is cancelled by the user."""
    pass

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
        'style': ['mirror', 'filled', 'bars', 'energy'],
        'blend_mode': ['overwrite', 'add', 'multiply', 'screen', 'normal'],
    },
    'circular_spectrum': {
        'style': ['bars', 'wave'],
        'blend_mode': ['overwrite', 'add', 'multiply', 'screen', 'normal'],
    },
    'circular_particles': {
        'blend_mode': ['overwrite', 'add', 'multiply', 'screen', 'normal'],
    },
    'energy_rings': {
        'blend_mode': ['overwrite', 'add', 'multiply', 'screen', 'normal'],
    },
}


# Короткие подсказки к параметрам pipeline (на русском)
COMMON_PARAM_DESCRIPTIONS_RU = {
    'blend_mode': 'Как смешивать слой с нижними',
    'opacity': 'Прозрачность слоя (0 — невидим, 1 — полный)',
    'style': 'Стиль отображения',
    'smoothing': 'Плавность анимации (0–1)',
    'line_width': 'Толщина линии, px',
    'window_duration': 'Длина аудио-окна, сек',
    'bins': 'Число частотных полос',
    'bar_spacing': 'Отступ между столбцами, px',
    'use_alpha': 'Полупрозрачная отрисовка',
    'rotation_speed': 'Скорость вращения',
    'count': 'Количество частиц',
    'max_speed': 'Максимальная скорость частиц',
    'min_speed': 'Минимальная скорость частиц',
    'force_multiplier': 'Насколько сильно звук толкает частицы',
    'decay_min': 'Мин. затухание жизни частицы за кадр',
    'decay_max': 'Макс. затухание жизни частицы за кадр',
    'spawn_rate': 'Как часто появляются новые частицы',
}

LAYER_PARAM_DESCRIPTIONS_RU = {
    'background': {
        'type': 'Тип фона: градиент, однотонный или анимированный',
        'color1': 'Первый цвет градиента',
        'color2': 'Второй цвет градиента',
        'direction': 'Направление градиента',
        'blur': 'Размытие фона, px',
    },
    'waveform': {
        'style': 'Форма волны: зеркало, заливка, простая, энергия',
    },
    'spectrum': {
        'style': 'Вид спектра: столбцы, круг или волна',
        'inner_radius': 'Внутренний радиус в круговом режиме, px',
        'wave_smoothing': 'Сглаживание линии волны (0–1)',
        'wave_thickness': 'Толщина линии волны, px',
    },
    'particles': {
        'bounce_strength': 'Сила отскока от краёв экрана (0–1)',
        'trail_enabled': 'Рисовать шлейф за частицами',
    },
    'circular_waveform': {
        'style': 'Форма круговой волны: зеркало, заливка или столбцы',
        'radius': 'Радиус круга, px',
        'center_x': 'Положение центра по горизонтали, px',
        'center_y': 'Положение центра по вертикали, px',
    },
    'circular_spectrum': {
        'style': 'Вид кругового спектра: столбцы или волна',
        'inner_radius': 'Внутренний радиус кольца, px',
        'outer_radius': 'Внешний радиус кольца, px',
    },
    'circular_particles': {
        'orbit_radius_min': 'Мин. радиус орбиты частиц, px',
        'orbit_radius_max': 'Макс. радиус орбиты частиц, px',
    },
    'effects': {
        'effects': 'Эффекты постобработки: свечение, виньетка, зерно, аберрация',
        'glow_intensity': 'Яркость свечения (0–1)',
        'glow_size': 'Размер размытия свечения, px',
        'vignette_strength': 'Затемнение по краям кадра (0–1)',
        'grain_amount': 'Интенсивность плёночного зерна (0–1)',
        'chromatic_shift': 'Сдвиг RGB-каналов для аберрации, px',
    },
}


def get_param_description(layer_name, key):
    """Return a short Russian tooltip for a pipeline parameter."""
    return (
        LAYER_PARAM_DESCRIPTIONS_RU.get(layer_name, {}).get(key)
        or COMMON_PARAM_DESCRIPTIONS_RU.get(key)
        or ''
    )


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
            param_info = infer_param_type(key, value, layer_name)
            description = get_param_description(layer_name, key)
            if description:
                param_info['description'] = description
            params[key] = param_info

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


def _update_job(job_id, **kwargs):
    """Update job fields and refresh last_update timestamp."""
    job = jobs[job_id]
    for k, v in kwargs.items():
        job[k] = v
    job['last_update'] = _time.time()


def process_video(job_id, audio_path, output_path, config, visualizer_type='pipeline'):
    try:
        _update_job(job_id, status='processing', progress=5, message='Loading audio...')

        audio_proc = AudioProcessor(config)
        audio_proc.load_audio(str(audio_path))

        _update_job(job_id, progress=15, message='Creating visualization...')

        visualizer = VisualizerFactory.create(visualizer_type, config, audio_proc)

        _update_job(job_id, progress=20, message='Rendering video...')

        render_with_progress(job_id, config, audio_proc, visualizer, str(output_path))

        _update_job(job_id, status='completed', progress=100, message='Done!')

    except CancelledError:
        _update_job(job_id, status='cancelled', message='Cancelled by user')
        # Clean up partial output
        if os.path.exists(str(output_path)):
            os.unlink(str(output_path))

    except Exception as e:
        # Provide user-friendly error messages
        err_msg = str(e)
        if 'NoBackendError' in type(e).__name__ or 'NoBackendError' in err_msg:
            err_msg = 'Failed to load audio file. The file may be corrupted or not a valid audio format.'
        elif 'Format not recognised' in err_msg or 'LibsndfileError' in type(e).__name__:
            err_msg = 'Unsupported audio format. Please use MP3, WAV, OGG, or FLAC.'
        _update_job(job_id, status='error', message=err_msg)
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

        cancelled = False
        for i in range(total_frames):
            # Check cancel flag each frame
            if jobs[job_id].get('cancel'):
                cancelled = True
                break

            time_point = i * frame_duration
            frame = visualizer.render_frame(time_point)
            writer.write(frame)

            progress = 20 + int((i / total_frames) * 70)
            _update_job(job_id, progress=progress, message=f'Frame {i+1}/{total_frames}')

        writer.release()

        if cancelled:
            raise CancelledError()

        _update_job(job_id, progress=95, message='Adding audio...')

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


@app.route('/api/samples')
def api_samples():
    """Return list of available sample audio files."""
    samples_dir = app.config['SAMPLES_FOLDER']
    AUDIO_EXT = {'.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a'}
    samples = []
    for f in sorted(samples_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in AUDIO_EXT:
            samples.append({'name': f.stem.replace('_', ' ').title(), 'filename': f.name})
    return jsonify(samples)


@app.route('/sample/<filename>')
def serve_sample(filename):
    """Serve a sample audio file."""
    safe_name = secure_filename(filename)
    sample_path = app.config['SAMPLES_FOLDER'] / safe_name
    if not sample_path.exists():
        return jsonify({'error': 'Sample not found'}), 404
    return send_file(str(sample_path), as_attachment=False)


@app.route('/upload', methods=['POST'])
def upload():
    # Support reusing audio from a previous job
    reuse_job_id = request.form.get('reuse_audio_job_id')
    sample_file = request.form.get('sample_file')

    if reuse_job_id:
        src_audio = None
        original_filename = 'audio.mp3'

        # Try in-memory jobs dict first
        if reuse_job_id in jobs:
            prev_job = jobs[reuse_job_id]
            src_audio = prev_job.get('original_audio_path') or prev_job.get('audio_path')
            original_filename = prev_job.get('original_filename') or prev_job.get('filename', 'audio.mp3')

        # Fallback: search on disk (survives server restart)
        if not src_audio or not os.path.exists(src_audio):
            src_audio = _find_audio_on_disk(reuse_job_id)
            if src_audio:
                original_filename = os.path.basename(src_audio)

        if not src_audio or not os.path.exists(src_audio):
            return jsonify({'error': 'Previous audio file not found. Please re-upload the audio.'}), 400

        job_id = str(uuid.uuid4())[:8]
        filename = secure_filename(original_filename)
        # Copy audio to new job path
        import shutil
        audio_path = app.config['UPLOAD_FOLDER'] / f"{job_id}_{filename}"
        shutil.copy2(src_audio, str(audio_path))
    elif sample_file:
        # Use a sample audio file
        safe_name = secure_filename(sample_file)
        sample_path = app.config['SAMPLES_FOLDER'] / safe_name
        if not sample_path.exists():
            return jsonify({'error': 'Sample file not found'}), 400

        job_id = str(uuid.uuid4())[:8]
        original_filename = safe_name
        filename = safe_name
        import shutil
        audio_path = app.config['UPLOAD_FOLDER'] / f"{job_id}_{filename}"
        shutil.copy2(str(sample_path), str(audio_path))
    else:
        if 'audio' not in request.files:
            return jsonify({'error': 'No file selected'}), 400

        file = request.files['audio']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        # Validate audio file extension
        ALLOWED_AUDIO_EXT = {'.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a', '.wma', '.opus'}
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_AUDIO_EXT:
            return jsonify({'error': f'Unsupported file format "{ext}". Please upload an audio file (mp3, wav, ogg, flac, aac, m4a).'}), 400

        job_id = str(uuid.uuid4())[:8]

        original_filename = file.filename  # Keep the user's original filename
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
        'original_filename': original_filename,  # Clean name without job ID prefix
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


STALL_TIMEOUT = 15  # seconds without progress update → consider stalled


@app.route('/status/<job_id>')
def status(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    job = jobs[job_id]

    # Detect stalled processing (no update for STALL_TIMEOUT seconds)
    if job['status'] == 'processing':
        last = job.get('last_update', 0)
        if last and (_time.time() - last) > STALL_TIMEOUT:
            job['status'] = 'error'
            job['message'] = 'Render appears to have stalled (no progress for 60s)'

    return jsonify({
        'status': job['status'],
        'progress': job['progress'],
        'message': job['message'],
        'filename': job.get('filename', ''),
        'config_snapshot': job.get('config_snapshot', {}),
    })


@app.route('/cancel/<job_id>', methods=['POST'])
def cancel(job_id):
    """Set cancel flag on a running job."""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    job = jobs[job_id]
    if job['status'] != 'processing':
        return jsonify({'error': 'Job is not running'}), 400
    job['cancel'] = True
    return jsonify({'ok': True})


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


def _find_audio_on_disk(job_id):
    """Search uploads folder for audio files matching a job ID prefix (survives server restart)."""
    upload_dir = app.config['UPLOAD_FOLDER']
    # Look for files starting with the job_id prefix
    for f in sorted(upload_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.name.startswith(job_id + '_') and f.is_file():
            ext = f.suffix.lower()
            if ext in {'.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a', '.wma', '.opus'}:
                return str(f)
    return None


@app.route('/audio/<job_id>')
def serve_audio(job_id):
    """Serve the uploaded audio file for a given job (used by restore)."""
    audio_path = None

    # Try in-memory jobs dict first
    if job_id in jobs:
        job = jobs[job_id]
        audio_path = job.get('original_audio_path') or job.get('audio_path')

    # Fallback: search on disk (survives server restart)
    if not audio_path or not os.path.exists(audio_path):
        audio_path = _find_audio_on_disk(job_id)

    if not audio_path or not os.path.exists(audio_path):
        return jsonify({'error': 'Audio file not found'}), 404

    return send_file(audio_path, as_attachment=False)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
