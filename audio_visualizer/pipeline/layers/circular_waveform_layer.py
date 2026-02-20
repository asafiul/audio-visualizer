import cv2
import numpy as np
from ..base_layer import BaseLayer


class CircularWaveformLayer(BaseLayer):
    layer_type = "circular_waveform"

    def __init__(self, config, audio_processor, width, height):
        super().__init__(config, audio_processor, width, height)
        self.layer_config = config["pipeline"]["circular_waveform"]
        self.center_x = width // 2
        self.center_y = height // 2
        self.max_radius = min(width, height) // 3
        
    def _render_direct(self, time, frame):
        window_duration = self.layer_config.get("window_duration", 0.5)
        audio_segment = self.audio.get_audio_segment(time, window_duration)
        
        if audio_segment is None or len(audio_segment) < 256:
            return frame
        
        max_amplitude = np.max(np.abs(audio_segment))
        if max_amplitude == 0:
            return frame
        audio_normalized = audio_segment / max_amplitude
        
        style = self.layer_config.get("style", "mirror")
        line_width = self.layer_config.get("line_width", 2)
        smoothing = self.layer_config.get("smoothing", 0.7)
        points_count = self.layer_config.get("points", 360)
        
        angles = np.linspace(0, 2 * np.pi, points_count)
        
        if style == "mirror":
            waveform_points = []
            for i, angle in enumerate(angles):
                audio_index = int((i / points_count) * len(audio_normalized))
                if audio_index >= len(audio_normalized):
                    audio_index = len(audio_normalized) - 1
                
                amplitude = audio_normalized[audio_index]
                radius = self.max_radius * (1 + amplitude * 0.5)
                
                x = int(self.center_x + radius * np.cos(angle))
                y = int(self.center_y + radius * np.sin(angle))
                waveform_points.append((x, y))
            
            if len(waveform_points) > 1:
                pts = np.array(waveform_points, np.int32)
                pts = pts.reshape((-1, 1, 2))
                cv2.polylines(frame, [pts], True, self._get_color(), line_width)
                
        elif style == "filled":
            waveform_points = []
            for i, angle in enumerate(angles):
                audio_index = int((i / points_count) * len(audio_normalized))
                if audio_index >= len(audio_normalized):
                    audio_index = len(audio_normalized) - 1
                
                amplitude = audio_normalized[audio_index]
                radius = self.max_radius * (1 + amplitude * 0.3)
                
                x = int(self.center_x + radius * np.cos(angle))
                y = int(self.center_y + radius * np.sin(angle))
                waveform_points.append((x, y))
            
            if len(waveform_points) > 2:
                pts = np.array(waveform_points, np.int32)
                cv2.fillPoly(frame, [pts], self._get_color())
                
        elif style == "bars":
            bar_width = 2 * np.pi / points_count
            for i, angle in enumerate(angles):
                audio_index = int((i / points_count) * len(audio_normalized))
                if audio_index >= len(audio_normalized):
                    audio_index = len(audio_normalized) - 1
                
                amplitude = audio_normalized[audio_index]
                bar_length = self.max_radius * amplitude
                
                start_x = int(self.center_x + (self.max_radius - 10) * np.cos(angle))
                start_y = int(self.center_y + (self.max_radius - 10) * np.sin(angle))
                end_x = int(self.center_x + (self.max_radius + bar_length) * np.cos(angle))
                end_y = int(self.center_y + (self.max_radius + bar_length) * np.sin(angle))
                
                cv2.line(frame, (start_x, start_y), (end_x, end_y), self._get_color(), line_width)
        
        return frame
    
    def _get_color(self):
        colors = self.config["visualization"]["colors"]
        primary_color = colors.get("primary", [0, 255, 255])
        return tuple(primary_color)