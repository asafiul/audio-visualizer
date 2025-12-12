import cv2
import numpy as np
from ..base_layer import BaseLayer


class SpectrumLayer(BaseLayer):
    layer_type = "spectrum"

    def __init__(self, config, audio_processor, width, height):
        super().__init__(config, audio_processor, width, height)
        self.layer_config = config["pipeline"]["spectrum"]
        self.prev_heights = None

    def get_instant_spectrum(self, time):
        window = 0.05
        audio_segment = self.audio.get_audio_segment(time, window)

        if audio_segment is None or len(audio_segment) < 256:
            return np.zeros(self.layer_config["bins"])

        segment = audio_segment[:512] if len(audio_segment) >= 512 else audio_segment
        fft = np.abs(np.fft.rfft(segment))
        fft = np.log1p(fft)

        if np.max(fft) > 0:
            fft = fft / np.max(fft)

        target_bins = min(64, self.layer_config["bins"])

        if len(fft) > target_bins:
            step = len(fft) // target_bins
            fft = np.array(
                [np.mean(fft[i : i + step]) for i in range(0, len(fft), step)]
            )
            fft = fft[:target_bins]

        return fft[:target_bins]

    def _render_direct(self, time: float, frame: np.ndarray) -> np.ndarray:
        freq_data = self.get_instant_spectrum(time)

        if len(freq_data) == 0:
            return frame

        style = self.layer_config["style"]

        if style == "bars":
            self._render_bars(frame, freq_data, time)
        elif style == "circular":
            self._render_circular(frame, freq_data, time)
        elif style == "wave":
            self._render_wave(frame, freq_data, time)

        return frame

    def _render_bars(self, frame, freq_data, time):
        num_bars = len(freq_data)
        bar_spacing = self.layer_config["bar_spacing"]

        total_spacing = (num_bars - 1) * bar_spacing
        available_width = self.width - total_spacing
        bar_width = max(1, int(available_width / num_bars))

        total_width = num_bars * bar_width + (num_bars - 1) * bar_spacing
        start_x = (self.width - total_width) // 2

        if self.prev_heights is None:
            self.prev_heights = np.zeros(num_bars)

        use_alpha = self.layer_config.get("use_alpha", False)
        smoothing = self.layer_config.get("smoothing", 0.3)

        target_heights = freq_data * self.height * 0.7
        smoothed_heights = (
            self.prev_heights * (1 - smoothing) + target_heights * smoothing
        )
        self.prev_heights = smoothed_heights.copy()

        bar_heights = smoothed_heights.astype(np.int32)

        for i, bar_height in enumerate(bar_heights):
            x = start_x + i * (bar_width + bar_spacing)
            y_top = self.height - bar_height

            color_ratio = i / max(num_bars, 1)
            color = self.get_color_gradient(color_ratio)

            if use_alpha:
                alpha = freq_data[i] * 0.8 + 0.2
                color = (color * alpha).astype(np.uint8)

            color_tuple = tuple(int(c) for c in color)

            cv2.rectangle(
                frame, (x, y_top), (x + bar_width, self.height), color_tuple, -1
            )

    def _render_circular(self, frame, freq_data, time):
        center_x, center_y = self.width // 2, self.height // 2
        inner_radius = self.layer_config.get("inner_radius", 50)
        outer_radius = min(center_x, center_y) - 10

        num_bars = len(freq_data)
        angles = np.linspace(0, 2 * np.pi, num_bars, endpoint=False)

        rotation = time * self.layer_config.get("rotation_speed", 0.3)
        use_alpha = self.layer_config.get("use_alpha", False)

        max_length = outer_radius - inner_radius
        segment_lengths = inner_radius + freq_data * max_length

        x1s = (center_x + np.cos(angles + rotation) * inner_radius).astype(np.int32)
        y1s = (center_y + np.sin(angles + rotation) * inner_radius).astype(np.int32)
        x2s = (center_x + np.cos(angles + rotation) * segment_lengths).astype(np.int32)
        y2s = (center_y + np.sin(angles + rotation) * segment_lengths).astype(np.int32)

        thicknesses = (freq_data * 8 + 1).astype(np.int32)

        for i in range(num_bars):
            color_ratio = i / num_bars
            color = self.get_color_gradient(color_ratio)

            if use_alpha:
                alpha = freq_data[i] * 0.8 + 0.2
                color = (color * alpha).astype(np.uint8)

            color_tuple = tuple(int(c) for c in color)

            cv2.line(
                frame, (x1s[i], y1s[i]), (x2s[i], y2s[i]), color_tuple, thicknesses[i]
            )

    def _render_wave(self, frame, freq_data, time):
        num_points = len(freq_data)
        x_points = np.linspace(0, self.width - 1, num_points, dtype=np.int32)

        if self.prev_heights is None:
            self.prev_heights = np.zeros(num_points)

        smoothing = self.layer_config.get("wave_smoothing", 0.5)
        use_alpha = self.layer_config.get("use_alpha", False)

        target_ys = self.height - (freq_data * self.height * 0.4 + self.height * 0.3)
        smoothed_ys = self.prev_heights * (1 - smoothing) + target_ys * smoothing
        self.prev_heights = smoothed_ys.copy()

        y_points = smoothed_ys.astype(np.int32)
        wave_thickness = self.layer_config.get("wave_thickness", 2)

        for i in range(num_points - 1):
            color_ratio = i / max(num_points, 1)
            color = self.get_color_gradient(color_ratio)

            if use_alpha:
                alpha = (freq_data[i] + freq_data[i + 1]) / 2 * 0.8 + 0.2
                color = (color * alpha).astype(np.uint8)

            color_tuple = tuple(int(c) for c in color)
            cv2.line(
                frame,
                (x_points[i], y_points[i]),
                (x_points[i + 1], y_points[i + 1]),
                color_tuple,
                wave_thickness,
            )
