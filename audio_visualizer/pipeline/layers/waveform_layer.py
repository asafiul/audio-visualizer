import cv2
import numpy as np
from ..base_layer import BaseLayer


class WaveformLayer(BaseLayer):
    layer_type = "waveform"
    
    def __init__(self, config, audio_processor, width, height):
        super().__init__(config, audio_processor, width, height)
        self.waveform_config = self.layer_config
        self.style = self.waveform_config['style']
        self.line_width = self.waveform_config['line_width']
        self.center_y = self.height // 2
        self.prev_waveform = None
        
    def get_audio_segment(self, time, window_duration=0.5):
        audio_segment = self.audio.get_audio_segment(time, window_duration)
        
        if len(audio_segment) == 0:
            return np.zeros(100)
        
        target_points = min(200, len(audio_segment))
        if len(audio_segment) > target_points:
            step = len(audio_segment) // target_points
            audio_segment = audio_segment[::step]
            if len(audio_segment) > target_points:
                audio_segment = audio_segment[:target_points]
        
        smoothing = self.waveform_config.get('smoothing', 0.7)
        if self.prev_waveform is not None and smoothing > 0:
            if len(audio_segment) == len(self.prev_waveform):
                audio_segment = audio_segment * (1 - smoothing) + self.prev_waveform * smoothing
        
        self.prev_waveform = audio_segment.copy()
        return audio_segment
    
    def _render_direct(self, time: float, frame: np.ndarray) -> np.ndarray:
        window = self.waveform_config['window_duration']
        audio_segment = self.get_audio_segment(time, window)
        
        if len(audio_segment) < 2:
            return frame
        
        amplitude = np.mean(np.abs(audio_segment))
        
        if self.style == 'mirror':
            self._render_mirror(frame, audio_segment, time, amplitude)
        elif self.style == 'filled':
            self._render_filled(frame, audio_segment, time, amplitude)
        elif self.style == 'simple':
            self._render_simple(frame, audio_segment, time, amplitude)
        elif self.style == 'energy':
            self._render_energy(frame, audio_segment, time, amplitude)
        
        return frame
    
    def _render_simple(self, frame, audio_segment, time, amplitude):
        x_points = np.linspace(0, self.width - 1, len(audio_segment), dtype=np.int32)
        y_points = (self.center_y + audio_segment * (self.height * 0.4)).astype(np.int32)
        points = np.column_stack([x_points, y_points])
        
        color = self.get_color_gradient(amplitude)
        color_tuple = tuple(int(c) for c in color)
        
        cv2.polylines(frame, [points], False, color_tuple, self.line_width)
    
    def _render_mirror(self, frame, audio_segment, time, amplitude):
        x_points = np.linspace(0, self.width - 1, len(audio_segment), dtype=np.int32)
        y_top = (self.center_y - audio_segment * (self.height * 0.4)).astype(np.int32)
        y_bottom = (self.center_y + audio_segment * (self.height * 0.4)).astype(np.int32)
        
        points_top = np.column_stack([x_points, y_top])
        points_bottom = np.column_stack([x_points, y_bottom])
        
        color_top = self.get_color_gradient(0.3)
        color_bottom = self.get_color_gradient(0.7)
        color_top_tuple = tuple(int(c) for c in color_top)
        color_bottom_tuple = tuple(int(c) for c in color_bottom)
        
        cv2.polylines(frame, [points_top], False, color_top_tuple, self.line_width)
        cv2.polylines(frame, [points_bottom], False, color_bottom_tuple, self.line_width)
    
    def _render_filled(self, frame, audio_segment, time, amplitude):
        x_points = np.linspace(0, self.width - 1, len(audio_segment), dtype=np.int32)
        y_points = (self.center_y + audio_segment * (self.height * 0.4)).astype(np.int32)
        
        points = np.column_stack([x_points, y_points])
        fill_points = np.vstack([
            points,
            np.array([[self.width - 1, self.height - 1], [0, self.height - 1]])
        ])
        
        color = self.get_color_gradient(amplitude)
        color_tuple = tuple(int(c) for c in color)
        
        cv2.fillPoly(frame, [fill_points], color_tuple)
        
        if self.line_width > 0:
            cv2.polylines(frame, [points], False, (255, 255, 255), self.line_width)
    
    def _render_energy(self, frame, audio_segment, time, amplitude):
        x_points = np.linspace(0, self.width - 1, len(audio_segment), dtype=np.int32)
        y_points = (self.center_y + audio_segment * (self.height * 0.4)).astype(np.int32)
        
        points = np.column_stack([x_points, y_points])
        color = self.get_color_gradient(amplitude)
        color_tuple = tuple(int(c) for c in color)
        
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            dy = abs(y2 - y1)
            thickness = int(self.line_width * (1 + dy / 10))
            cv2.line(frame, (x1, y1), (x2, y2), color_tuple, max(1, thickness))