import os
import sys
import uuid
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import threading

sys.path.insert(0, str(Path(__file__).parent.parent))

from audio_visualizer.config_loader import ConfigLoader
from audio_visualizer.audio_processor import AudioProcessor
from audio_visualizer.visualizer_factory import VisualizerFactory
from audio_visualizer.video_renderer import VideoRenderer

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 
app.config['UPLOAD_FOLDER'] = Path(__file__).parent / 'uploads'
app.config['OUTPUT_FOLDER'] = Path(__file__).parent / 'outputs'

app.config['UPLOAD_FOLDER'].mkdir(exist_ok=True)
app.config['OUTPUT_FOLDER'].mkdir(exist_ok=True)

jobs = {}


def parse_color(hex_color):
    hex_color = hex_color.lstrip('#')
    return [int(hex_color[i:i+2], 16) for i in (0, 2, 4)]


def process_video(job_id, audio_path, output_path, config, visualizer_type='pipeline'):
    try:
        jobs[job_id]['status'] = 'processing'
        jobs[job_id]['progress'] = 5
        jobs[job_id]['message'] = 'Загрузка аудио...'

        audio_proc = AudioProcessor(config)
        audio_proc.load_audio(str(audio_path))

        jobs[job_id]['progress'] = 15
        jobs[job_id]['message'] = 'Создание визуализации...'

        visualizer = VisualizerFactory.create(visualizer_type, config, audio_proc)

        jobs[job_id]['progress'] = 20
        jobs[job_id]['message'] = 'Рендеринг видео...'

        render_with_progress(job_id, config, audio_proc, visualizer, str(output_path))

        jobs[job_id]['status'] = 'completed'
        jobs[job_id]['progress'] = 100
        jobs[job_id]['message'] = 'Готово!'

    except Exception as e:
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['message'] = str(e)


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
            jobs[job_id]['message'] = f'Кадр {i+1}/{total_frames}'

        writer.release()

        jobs[job_id]['progress'] = 95
        jobs[job_id]['message'] = 'Добавление аудио...'

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


@app.route('/upload', methods=['POST'])
def upload():
    if 'audio' not in request.files:
        return jsonify({'error': 'Файл не выбран'}), 400

    file = request.files['audio']
    if file.filename == '':
        return jsonify({'error': 'Файл не выбран'}), 400

    job_id = str(uuid.uuid4())[:8]

    filename = secure_filename(file.filename)
    audio_path = app.config['UPLOAD_FOLDER'] / f"{job_id}_{filename}"
    file.save(str(audio_path))

    config = ConfigLoader().config

    config['video']['width'] = int(request.form.get('width', 1920))
    config['video']['height'] = int(request.form.get('height', 1080))
    config['video']['fps'] = int(request.form.get('fps', 30))

    if request.form.get('primary_color'):
        config['visualization']['colors']['primary'] = parse_color(request.form['primary_color'])
    if request.form.get('secondary_color'):
        config['visualization']['colors']['secondary'] = parse_color(request.form['secondary_color'])

    visualizer_type = request.form.get('visualizer_type', 'pipeline')
    
    if visualizer_type == 'pipeline':
        config['pipeline']['order'] = ['background', 'particles', 'waveform', 'spectrum', 'effects']
    else:
        config['pipeline']['order'] = ['background', visualizer_type]
    
    if 'spectrum' in config['pipeline']['order']:
        config['pipeline']['spectrum']['style'] = request.form.get('spectrum_style', 'bars')
    if 'waveform' in config['pipeline']['order']:
        config['pipeline']['waveform']['style'] = request.form.get('waveform_style', 'mirror')

    output_path = app.config['OUTPUT_FOLDER'] / f"{job_id}_output.mp4"

    jobs[job_id] = {
        'status': 'queued',
        'progress': 0,
        'message': 'В очереди...',
        'audio_path': str(audio_path),
        'output_path': str(output_path)
    }

    thread = threading.Thread(target=process_video, args=(job_id, audio_path, output_path, config, 'pipeline'))
    thread.daemon = True
    thread.start()

    return jsonify({'job_id': job_id})


@app.route('/status/<job_id>')
def status(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(jobs[job_id])


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


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
