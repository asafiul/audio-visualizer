import cv2
import numpy as np
from ..base_layer import BaseLayer


class SpectrumLayer(BaseLayer):
    layer_type = "spectrum"

    def __init__(self, config, audio_processor, width, height):
        super().__init__(config, audio_processor, width, height)
        self.layer_config = config["pipeline"]["spectrum"]
        self.prev_heights = None
        self.prev_spectrum = None

    def get_instant_spectrum(self, time):
        window = 0.08  # Wider window for better frequency resolution
        audio_segment = self.audio.get_audio_segment(time, window)

        target_bins = self.layer_config.get("bins", 64)

        if audio_segment is None or len(audio_segment) < 256:
            if self.prev_spectrum is not None:
                return self.prev_spectrum * 0.9
            return np.zeros(target_bins)

        # Use a larger FFT window for better frequency resolution
        fft_size = min(4096, len(audio_segment))
        # Apply Hann window to reduce spectral leakage
        windowed = audio_segment[:fft_size] * np.hanning(fft_size)
        fft = np.abs(np.fft.rfft(windowed))

        # Limit to useful frequency range (up to ~10kHz instead of full Nyquist ~22kHz)
        # This ensures all bins map to frequencies where music actually has content
        sr = self.audio.sample_rate if hasattr(self.audio, '_sample_rate') and self.audio.sample_rate > 0 else 44100
        max_useful_freq = 12000  # Hz — covers virtually all musical content
        max_bin_index = min(len(fft), int(max_useful_freq * fft_size / sr))
        max_bin_index = max(max_bin_index, target_bins)  # Safety floor
        fft = fft[:max_bin_index]

        # Log scale for perceptual loudness
        fft = np.log1p(fft)

        # Use LOGARITHMIC frequency binning for perceptually even distribution
        if len(fft) > target_bins:
            fft_resampled = np.zeros(target_bins)
            # Create logarithmically spaced center frequencies
            log_centers = np.logspace(
                np.log10(1),  # Start from index 1 (skip DC)
                np.log10(len(fft) - 1),
                target_bins
            )
            # Create bin edges as midpoints between centers
            log_edges = np.zeros(target_bins + 1)
            log_edges[0] = max(0, log_centers[0] - (log_centers[1] - log_centers[0]) / 2)
            log_edges[-1] = min(len(fft), log_centers[-1] + (log_centers[-1] - log_centers[-2]) / 2)
            for i in range(1, target_bins):
                log_edges[i] = (log_centers[i - 1] + log_centers[i]) / 2

            for i in range(target_bins):
                start = int(log_edges[i])
                end = int(log_edges[i + 1])
                start = max(0, min(start, len(fft) - 1))
                end = max(start + 1, min(end, len(fft)))
                fft_resampled[i] = np.mean(fft[start:end])

            fft = fft_resampled
        else:
            # If we have fewer FFT bins than target, interpolate up
            x_old = np.linspace(0, 1, len(fft))
            x_new = np.linspace(0, 1, target_bins)
            fft = np.interp(x_new, x_old, fft)

        # Normalize to 0-1 range
        max_val = np.max(fft)
        if max_val > 0:
            fft = fft / max_val

        # Apply frequency-dependent boost to balance the spectrum
        # Bass tends to dominate even after log binning, boost mids/highs more
        freq_balance = np.linspace(0.6, 1.4, len(fft))
        fft = fft * freq_balance

        # Ensure no completely dead bins at the end — give them a small minimum
        # so the spectrum doesn't look like it cuts off abruptly
        min_floor = 0.02
        fft = np.maximum(fft, min_floor)

        # Re-normalize after balancing
        max_val = np.max(fft)
        if max_val > 0:
            fft = fft / max_val

        # Temporal smoothing — lighter for more responsive feel
        if self.prev_spectrum is not None and len(self.prev_spectrum) == len(fft):
            temporal_smooth = self.layer_config.get("smoothing", 0.15)
            fft = self.prev_spectrum * temporal_smooth + fft * (1 - temporal_smooth)

        self.prev_spectrum = fft.copy()
        return fft

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
        bar_spacing = self.layer_config.get("bar_spacing", 2)

        total_spacing = (num_bars - 1) * bar_spacing
        available_width = self.width - total_spacing
        bar_width = max(2, int(available_width / num_bars))

        total_width = num_bars * bar_width + (num_bars - 1) * bar_spacing
        start_x = (self.width - total_width) // 2

        if self.prev_heights is None or len(self.prev_heights) != num_bars:
            self.prev_heights = np.zeros(num_bars)

        use_alpha = self.layer_config.get("use_alpha", False)

        # Target heights from frequency data
        target_heights = freq_data * self.height * 0.45

        # Smooth bar heights — responsive attack, moderate release
        for i in range(num_bars):
            if target_heights[i] > self.prev_heights[i]:
                # Very fast attack — bars snap up quickly
                self.prev_heights[i] = self.prev_heights[i] * 0.15 + target_heights[i] * 0.85
            else:
                # Moderate release — bars fall at a natural pace
                self.prev_heights[i] = self.prev_heights[i] * 0.75 + target_heights[i] * 0.25

        bar_heights = self.prev_heights.astype(np.int32)

        for i, bar_height in enumerate(bar_heights):
            if bar_height < 2:
                bar_height = 2  # Minimum visible height

            x = start_x + i * (bar_width + bar_spacing)
            y_top = self.height - bar_height

            color_ratio = i / max(num_bars - 1, 1)
            color = self.get_color_gradient(color_ratio)

            if use_alpha:
                alpha = max(0.2, freq_data[i] * 0.8 + 0.2)
                color = (color * alpha).astype(np.uint8)

            color_tuple = tuple(int(c) for c in color)

            # Draw bar with slight rounded top
            cv2.rectangle(
                frame, (x, y_top), (x + bar_width, self.height), color_tuple, -1
            )

            # Add a bright cap on top of each bar
            if bar_height > 4:
                cap_color = tuple(min(255, int(c * 1.5)) for c in color_tuple)
                cv2.rectangle(
                    frame, (x, y_top), (x + bar_width, y_top + 2), cap_color, -1
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

        rotated_angles = angles + rotation
        x1s = (center_x + np.cos(rotated_angles) * inner_radius).astype(np.int32)
        y1s = (center_y + np.sin(rotated_angles) * inner_radius).astype(np.int32)
        x2s = (center_x + np.cos(rotated_angles) * segment_lengths).astype(np.int32)
        y2s = (center_y + np.sin(rotated_angles) * segment_lengths).astype(np.int32)

        thicknesses = np.clip((freq_data * 6 + 2).astype(np.int32), 2, 8)

        for i in range(num_bars):
            color_ratio = i / max(num_bars - 1, 1)
            color = self.get_color_gradient(color_ratio)

            if use_alpha:
                alpha = max(0.2, freq_data[i] * 0.8 + 0.2)
                color = (color * alpha).astype(np.uint8)

            color_tuple = tuple(int(c) for c in color)

            cv2.line(
                frame, (x1s[i], y1s[i]), (x2s[i], y2s[i]), color_tuple, int(thicknesses[i])
            )

    def _render_wave(self, frame, freq_data, time):
        num_points = len(freq_data)
        x_points = np.linspace(0, self.width - 1, num_points, dtype=np.int32)

        if self.prev_heights is None or len(self.prev_heights) != num_points:
            self.prev_heights = np.zeros(num_points)

        smoothing = self.layer_config.get("wave_smoothing", 0.5)
        use_alpha = self.layer_config.get("use_alpha", False)

        target_ys = self.height - (freq_data * self.height * 0.4 + self.height * 0.3)
        smoothed_ys = self.prev_heights * smoothing + target_ys * (1 - smoothing)
        self.prev_heights = smoothed_ys.copy()

        y_points = smoothed_ys.astype(np.int32)
        wave_thickness = self.layer_config.get("wave_thickness", 2)

        for i in range(num_points - 1):
            color_ratio = i / max(num_points - 1, 1)
            color = self.get_color_gradient(color_ratio)

            if use_alpha:
                alpha = max(0.2, (freq_data[i] + freq_data[i + 1]) / 2 * 0.8 + 0.2)
                color = (color * alpha).astype(np.uint8)

            color_tuple = tuple(int(c) for c in color)
            cv2.line(
                frame,
                (x_points[i], y_points[i]),
                (x_points[i + 1], y_points[i + 1]),
                color_tuple,
                wave_thickness,
            )
