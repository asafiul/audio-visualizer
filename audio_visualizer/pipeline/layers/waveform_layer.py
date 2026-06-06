import cv2
import numpy as np
from ..base_layer import BaseLayer


class WaveformLayer(BaseLayer):
    layer_type = "waveform"
    
    def __init__(self, config, audio_processor, width, height):
        super().__init__(config, audio_processor, width, height)
        self.waveform_config = self.layer_config
        self.style = self.waveform_config.get('style', 'mirror')
        self.line_width = self.waveform_config.get('line_width', 2)
        self.center_y = self.height // 2
        self.prev_waveform = None
        
    def get_audio_segment(self, time, window_duration=0.05):
        audio_segment = self.audio.get_audio_segment(time, window_duration)
        
        if audio_segment is None or len(audio_segment) == 0:
            if self.prev_waveform is not None:
                return self.prev_waveform * 0.9
            return np.zeros(200)
        
        target_points = min(300, len(audio_segment))
        if len(audio_segment) > target_points:
            # Use proper downsampling with averaging instead of just stepping
            step = len(audio_segment) // target_points
            audio_segment = np.array([
                np.mean(audio_segment[i:i+step]) 
                for i in range(0, len(audio_segment) - step + 1, step)
            ])
            if len(audio_segment) > target_points:
                audio_segment = audio_segment[:target_points]
        
        # Normalize
        max_amp = np.max(np.abs(audio_segment))
        if max_amp > 0:
            audio_segment = audio_segment / max_amp
        
        smoothing = self.waveform_config.get('smoothing', 0.5)
        if self.prev_waveform is not None and smoothing > 0:
            if len(audio_segment) == len(self.prev_waveform):
                audio_segment = self.prev_waveform * smoothing + audio_segment * (1 - smoothing)
            else:
                # Interpolate previous to match current length
                x_old = np.linspace(0, 1, len(self.prev_waveform))
                x_new = np.linspace(0, 1, len(audio_segment))
                prev_interp = np.interp(x_new, x_old, self.prev_waveform)
                audio_segment = prev_interp * smoothing + audio_segment * (1 - smoothing)
        
        self.prev_waveform = audio_segment.copy()
        return audio_segment
    
    def _render_direct(self, time: float, frame: np.ndarray) -> np.ndarray:
        window = self.waveform_config.get('window_duration', 0.05)
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
        y_points = (self.center_y + audio_segment * (self.height * 0.35)).astype(np.int32)
        
        # Draw with gradient color
        for i in range(len(x_points) - 1):
            color_ratio = i / max(len(x_points) - 1, 1)
            color = self.get_color_gradient(color_ratio)
            color_tuple = tuple(int(c) for c in color)
            cv2.line(frame, (x_points[i], y_points[i]), 
                     (x_points[i+1], y_points[i+1]), color_tuple, 
                     self.line_width, cv2.LINE_AA)
    
    def _render_mirror(self, frame, audio_segment, time, amplitude):
        x_points = np.linspace(0, self.width - 1, len(audio_segment), dtype=np.int32)
        displacement = audio_segment * (self.height * 0.35)
        y_top = (self.center_y - displacement).astype(np.int32)
        y_bottom = (self.center_y + displacement).astype(np.int32)
        
        # Draw with gradient colors
        for i in range(len(x_points) - 1):
            color_ratio = i / max(len(x_points) - 1, 1)
            color_top = self.get_color_gradient(color_ratio * 0.6)
            color_bottom = self.get_color_gradient(0.4 + color_ratio * 0.6)
            
            ct_top = tuple(int(c) for c in color_top)
            ct_bottom = tuple(int(c) for c in color_bottom)
            
            cv2.line(frame, (x_points[i], y_top[i]), 
                     (x_points[i+1], y_top[i+1]), ct_top, 
                     self.line_width, cv2.LINE_AA)
            cv2.line(frame, (x_points[i], y_bottom[i]), 
                     (x_points[i+1], y_bottom[i+1]), ct_bottom, 
                     self.line_width, cv2.LINE_AA)
        
        # Draw center line (subtle)
        center_color = self.get_color_gradient(0.5) * 0.3
        center_tuple = tuple(int(c) for c in center_color.astype(np.uint8))
        cv2.line(frame, (0, self.center_y), (self.width, self.center_y), 
                 center_tuple, 1, cv2.LINE_AA)
    
    def _render_filled(self, frame, audio_segment, time, amplitude):
        x_points = np.linspace(0, self.width - 1, len(audio_segment), dtype=np.int32)
        y_points = (self.center_y + audio_segment * (self.height * 0.35)).astype(np.int32)
        
        points = np.column_stack([x_points, y_points])
        fill_points = np.vstack([
            points,
            np.array([[self.width - 1, self.height - 1], [0, self.height - 1]])
        ])
        
        color = self.get_color_gradient(amplitude)
        # Semi-transparent fill
        fill_color = tuple(int(c * 0.4) for c in color)
        cv2.fillPoly(frame, [fill_points], fill_color)
        
        # Draw outline with gradient
        for i in range(len(x_points) - 1):
            color_ratio = i / max(len(x_points) - 1, 1)
            line_color = self.get_color_gradient(color_ratio)
            line_tuple = tuple(int(c) for c in line_color)
            cv2.line(frame, (x_points[i], y_points[i]),
                     (x_points[i+1], y_points[i+1]), line_tuple,
                     self.line_width, cv2.LINE_AA)
    
    def _render_energy(self, frame, audio_segment, time, amplitude):
        x_points = np.linspace(0, self.width - 1, len(audio_segment), dtype=np.int32)
        y_points = (self.center_y + audio_segment * (self.height * 0.35)).astype(np.int32)
        
        for i in range(len(x_points) - 1):
            x1, y1 = x_points[i], y_points[i]
            x2, y2 = x_points[i + 1], y_points[i + 1]
            dy = abs(y2 - y1)
            
            # Thickness varies with energy (amplitude change)
            thickness = int(self.line_width * (1 + dy / 15))
            thickness = max(1, min(thickness, self.line_width * 4))
            
            # Color intensity varies with local energy
            local_energy = abs(audio_segment[i])
            color_ratio = i / max(len(x_points) - 1, 1)
            color = self.get_color_gradient(color_ratio)
            alpha = max(0.3, local_energy * 0.7 + 0.3)
            color = (color * alpha).astype(np.uint8)
            color_tuple = tuple(int(c) for c in color)
            
            cv2.line(frame, (x1, y1), (x2, y2), color_tuple, 
                     thickness, cv2.LINE_AA)
