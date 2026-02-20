import cv2
import numpy as np
from ..base_layer import BaseLayer


class CircularSpectrumLayer(BaseLayer):
    layer_type = "circular_spectrum"

    def __init__(self, config, audio_processor, width, height):
        super().__init__(config, audio_processor, width, height)
        self.layer_config = config["pipeline"]["circular_spectrum"]
        self.center_x = width // 2
        self.center_y = height // 2
        self.max_radius = min(width, height) // 3
        
    def _render_direct(self, time, frame):
        window = 0.1
        audio_segment = self.audio.get_audio_segment(time, window)
        
        if audio_segment is None or len(audio_segment) < 256:
            return frame
        
        segment = audio_segment[:1024] if len(audio_segment) >= 1024 else audio_segment
        fft = np.abs(np.fft.rfft(segment))
        fft = np.log1p(fft)
        
        freq_weights = np.linspace(0.5, 2.0, len(fft))
        fft = fft * freq_weights
        
        if np.max(fft) > 0:
            fft = fft / np.max(fft)
        
        bins = min(48, self.layer_config.get("bins", 48))
        bar_width = self.layer_config.get("bar_width", 3)
        
        if len(fft) > bins:
            fft_resampled = np.zeros(bins)
            log_indices = np.logspace(0, np.log10(len(fft)-1), bins+1, dtype=int)
            for i in range(bins):
                start = log_indices[i]
                end = log_indices[i+1]
                if end > start:
                    fft_resampled[i] = np.mean(fft[start:end])
                else:
                    fft_resampled[i] = 0
            fft = fft_resampled
        
        angles = np.linspace(0, 2 * np.pi, bins, endpoint=False)
        
        for i, angle in enumerate(angles):
            amplitude = fft[i] if i < len(fft) else 0
            bar_length = self.max_radius * amplitude * 0.8
            
            inner_radius = self.max_radius * 0.3
            outer_radius = inner_radius + bar_length
            
            start_x = int(self.center_x + inner_radius * np.cos(angle))
            start_y = int(self.center_y + inner_radius * np.sin(angle))
            end_x = int(self.center_x + outer_radius * np.cos(angle))
            end_y = int(self.center_y + outer_radius * np.sin(angle))
            
            cv2.line(frame, (start_x, start_y), (end_x, end_y), self._get_color(), bar_width)
            
            cv2.circle(frame, (end_x, end_y), bar_width // 2 + 1, self._get_color(), -1)
        
        return frame
    
    def _get_color(self):
        colors = self.config["visualization"]["colors"]
        primary_color = colors.get("primary", [0, 255, 255])
        return tuple(primary_color)