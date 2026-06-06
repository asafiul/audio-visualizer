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
        self.max_radius = int(min(width, height) * 0.42)
        self.prev_spectrum = None
        self.prev_bar_lengths = None

    def _render_direct(self, time, frame):
        window = 0.08  # Wider window for better frequency resolution
        audio_segment = self.audio.get_audio_segment(time, window)

        bins = min(64, self.layer_config.get("bins", 48))

        if audio_segment is None or len(audio_segment) < 256:
            if self.prev_spectrum is not None:
                self.prev_spectrum *= 0.9
                freq_data = self.prev_spectrum
            else:
                return frame
        else:
            # Use larger FFT for better frequency resolution
            fft_size = min(4096, len(audio_segment))
            # Apply Hann window to reduce spectral leakage
            windowed = audio_segment[:fft_size] * np.hanning(fft_size)
            fft = np.abs(np.fft.rfft(windowed))

            # Limit to useful frequency range (~12kHz)
            sr = self.audio.sample_rate if hasattr(self.audio, '_sample_rate') and self.audio.sample_rate > 0 else 44100
            max_useful_freq = 12000
            max_bin_index = min(len(fft), int(max_useful_freq * fft_size / sr))
            max_bin_index = max(max_bin_index, bins)
            fft = fft[:max_bin_index]

            fft = np.log1p(fft)

            # Normalize
            if np.max(fft) > 0:
                fft = fft / np.max(fft)

            # Logarithmic frequency binning for perceptually even distribution
            if len(fft) > bins:
                fft_resampled = np.zeros(bins)
                log_centers = np.logspace(
                    np.log10(1),
                    np.log10(len(fft) - 1),
                    bins
                )
                log_edges = np.zeros(bins + 1)
                log_edges[0] = max(0, log_centers[0] - (log_centers[1] - log_centers[0]) / 2)
                log_edges[-1] = min(len(fft), log_centers[-1] + (log_centers[-1] - log_centers[-2]) / 2)
                for i in range(1, bins):
                    log_edges[i] = (log_centers[i - 1] + log_centers[i]) / 2

                for i in range(bins):
                    start = int(log_edges[i])
                    end = int(log_edges[i + 1])
                    start = max(0, min(start, len(fft) - 1))
                    end = max(start + 1, min(end, len(fft)))
                    fft_resampled[i] = np.mean(fft[start:end])

                freq_data = fft_resampled
            else:
                x_old = np.linspace(0, 1, len(fft))
                x_new = np.linspace(0, 1, bins)
                freq_data = np.interp(x_new, x_old, fft)

            # Normalize again
            max_val = np.max(freq_data)
            if max_val > 0:
                freq_data = freq_data / max_val

            # Balance frequencies
            freq_balance = np.linspace(0.75, 1.15, len(freq_data))
            freq_data = freq_data * freq_balance

            # Ensure no dead bins at the end
            freq_data = np.maximum(freq_data, 0.02)

            max_val = np.max(freq_data)
            if max_val > 0:
                freq_data = freq_data / max_val

            # Temporal smoothing
            smoothing = self.layer_config.get("smoothing", 0.3)
            if self.prev_spectrum is not None and len(self.prev_spectrum) == len(freq_data):
                freq_data = self.prev_spectrum * smoothing + freq_data * (1 - smoothing)

            self.prev_spectrum = freq_data.copy()

        bar_width = self.layer_config.get("bar_width", 3)
        rotation_speed = self.layer_config.get("rotation_speed", 0.3)
        rotation = time * rotation_speed

        num_bars = len(freq_data)
        angles = np.linspace(0, 2 * np.pi, num_bars, endpoint=False)

        # Initialize bar lengths for smooth animation
        if self.prev_bar_lengths is None or len(self.prev_bar_lengths) != num_bars:
            self.prev_bar_lengths = np.zeros(num_bars)

        inner_radius = self.layer_config.get("inner_radius", 250)

        for i, angle in enumerate(angles):
            amplitude = freq_data[i] if i < len(freq_data) else 0

            target_length = self.max_radius * amplitude * 0.3

            # Attack/release smoothing for each bar (faster release)
            if target_length > self.prev_bar_lengths[i]:
                self.prev_bar_lengths[i] = self.prev_bar_lengths[i] * 0.2 + target_length * 0.8
            else:
                self.prev_bar_lengths[i] = self.prev_bar_lengths[i] * 0.7 + target_length * 0.3

            bar_length = self.prev_bar_lengths[i]
            outer_radius = inner_radius + bar_length

            rotated_angle = angle + rotation

            start_x = int(self.center_x + inner_radius * np.cos(rotated_angle))
            start_y = int(self.center_y + inner_radius * np.sin(rotated_angle))
            end_x = int(self.center_x + outer_radius * np.cos(rotated_angle))
            end_y = int(self.center_y + outer_radius * np.sin(rotated_angle))

            # Color gradient based on frequency bin
            color_ratio = i / max(num_bars - 1, 1)
            color = self.get_color_gradient(color_ratio)
            # Apply amplitude-based alpha
            alpha = max(0.3, amplitude * 0.7 + 0.3)
            color = (color * alpha).astype(np.uint8)
            color_tuple = tuple(int(c) for c in color)

            cv2.line(frame, (start_x, start_y), (end_x, end_y), color_tuple, bar_width)

            # Bright dot at the tip
            if bar_length > 3:
                tip_color = tuple(min(255, int(c * 1.4)) for c in color_tuple)
                cv2.circle(frame, (end_x, end_y), bar_width // 2 + 1, tip_color, -1)

        return frame
