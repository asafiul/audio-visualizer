import cv2
import numpy as np
from tqdm import tqdm
from moviepy.video.io.ffmpeg_writer import FFMPEG_VideoWriter
import tempfile
import os
import subprocess


class VideoRenderer:
    def __init__(self, config: dict):
        video_config = config['video']
        self.width = video_config['width']
        self.height = video_config['height']
        self.fps = video_config['fps']
    
    def render(self, audio_processor, visualizer, output_path: str):
        print(f"Rendering video {self.width}x{self.height}@{self.fps}fps")
        
        if hasattr(visualizer, 'get_layer_info'):
            layer_info = visualizer.get_layer_info()
            print("Pipeline layers:")
            for i, layer in enumerate(layer_info):
                print(f"  {i+1}. {layer['name']}")
        
        total_frames = int(audio_processor.duration * self.fps)
        frame_duration = 1.0 / self.fps
        
        temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
        temp_video_path = temp_video.name
        temp_video.close()
        
        try:
            writer = FFMPEG_VideoWriter(
                temp_video_path,
                (self.width, self.height),
                self.fps,
                codec='libx264',
                audiofile=None,
                preset='medium',
                ffmpeg_params=['-crf', '18', '-an']
            )
            
            print("Rendering frames...")
            progress_bar = tqdm(total=total_frames, desc="Progress", unit="frame")
            
            for frame_idx in range(total_frames):
                time = frame_idx * frame_duration
                frame = visualizer.render_frame(time)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                writer.write_frame(frame_rgb)
                progress_bar.update(1)
            
            progress_bar.close()
            writer.close()
            print("Adding audio...")
            
            success = self._add_audio(temp_video_path, audio_processor, output_path)
            if success:
                print(f"Video ready: {output_path}")
            else:
                print(f"Video created without audio: {output_path}")
            
        except KeyboardInterrupt:
            print("Rendering interrupted")
            if os.path.exists(temp_video_path):
                import shutil
                shutil.copy2(temp_video_path, output_path.replace('.mp4', '_partial.mp4'))
                print(f"Partial result: {output_path.replace('.mp4', '_partial.mp4')}")
            raise
        finally:
            if os.path.exists(temp_video_path):
                os.unlink(temp_video_path)
    
    def _add_audio(self, video_path: str, audio_processor, output_path: str):
        audio_file = audio_processor.original_audio_path
        
        if not os.path.exists(audio_file):
            print(f"Audio file not found: {audio_file}")
            return False
        
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-i', audio_file,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-shortest',
            '-y',
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        
        if result.returncode == 0:
            return True
        else:
            print(f"FFmpeg error: {result.stderr[:200]}")
            return False