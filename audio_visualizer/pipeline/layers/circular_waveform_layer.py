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
        self.prev_waveform = None

    def _render_direct(self, time, frame):
        window_duration = self.layer_config.get("window_duration", 0.05)
        audio_segment = self.audio.get_audio_segment(time, window_duration)

        if audio_segment is None or len(audio_segment) < 64:
            return frame

        max_amplitude = np.max(np.abs(audio_segment))
        if max_amplitude == 0:
            return frame
        audio_normalized = audio_segment / max_amplitude

        style = self.layer_config.get("style", "mirror")
        line_width = self.layer_config.get("line_width", 2)
        smoothing = self.layer_config.get("smoothing", 0.7)
        points_count = self.layer_config.get("points", 360)
        rotation_speed = self.layer_config.get("rotation_speed", 0.2)

        # Downsample audio to target points count
        if len(audio_normalized) > points_count:
            step = len(audio_normalized) // points_count
            audio_normalized = audio_normalized[::step][:points_count]
        elif len(audio_normalized) < points_count:
            # Interpolate up
            x_old = np.linspace(0, 1, len(audio_normalized))
            x_new = np.linspace(0, 1, points_count)
            audio_normalized = np.interp(x_new, x_old, audio_normalized)

        # Apply temporal smoothing
        if self.prev_waveform is not None and len(self.prev_waveform) == len(audio_normalized):
            audio_normalized = self.prev_waveform * smoothing + audio_normalized * (1 - smoothing)
        self.prev_waveform = audio_normalized.copy()

        # Rotation over time
        rotation = time * rotation_speed

        angles = np.linspace(0, 2 * np.pi, len(audio_normalized), endpoint=True)
        rotated_angles = angles + rotation

        if style == "mirror":
            self._render_mirror_circular(frame, audio_normalized, rotated_angles, line_width)
        elif style == "filled":
            self._render_filled_circular(frame, audio_normalized, rotated_angles, line_width)
        elif style == "bars":
            self._render_bars_circular(frame, audio_normalized, rotated_angles, line_width)
        elif style == "energy":
            self._render_energy_circular(frame, audio_normalized, rotated_angles, line_width)

        return frame

    def _render_mirror_circular(self, frame, audio, angles, line_width):
        # Outer ring (positive amplitude)
        points_outer = []
        # Inner ring (negative/mirror amplitude)
        points_inner = []

        for i in range(len(audio)):
            amplitude = audio[i]
            angle = angles[i]

            # Outer: base radius + positive displacement (gentle)
            r_outer = self.max_radius * (1.0 + amplitude * 0.2)
            x = int(self.center_x + r_outer * np.cos(angle))
            y = int(self.center_y + r_outer * np.sin(angle))
            points_outer.append((x, y))

            # Inner: base radius - displacement (mirror, gentle)
            r_inner = self.max_radius * (1.0 - abs(amplitude) * 0.12)
            x2 = int(self.center_x + r_inner * np.cos(angle))
            y2 = int(self.center_y + r_inner * np.sin(angle))
            points_inner.append((x2, y2))

        if len(points_outer) > 1:
            # Draw outer ring with gradient
            pts = np.array(points_outer, np.int32).reshape((-1, 1, 2))
            for i in range(len(points_outer) - 1):
                color_ratio = i / max(len(points_outer) - 1, 1)
                color = self.get_color_gradient(color_ratio)
                color_tuple = tuple(int(c) for c in color)
                cv2.line(frame, points_outer[i], points_outer[i + 1],
                         color_tuple, line_width, cv2.LINE_AA)
            # Close the loop
            color = self.get_color_gradient(1.0)
            color_tuple = tuple(int(c) for c in color)
            cv2.line(frame, points_outer[-1], points_outer[0],
                     color_tuple, line_width, cv2.LINE_AA)

        if len(points_inner) > 1:
            # Draw inner ring with dimmer gradient
            for i in range(len(points_inner) - 1):
                color_ratio = i / max(len(points_inner) - 1, 1)
                color = self.get_color_gradient(color_ratio) * 0.6
                color_tuple = tuple(int(c) for c in color.astype(np.uint8))
                cv2.line(frame, points_inner[i], points_inner[i + 1],
                         color_tuple, max(1, line_width - 1), cv2.LINE_AA)
            color = self.get_color_gradient(1.0) * 0.6
            color_tuple = tuple(int(c) for c in color.astype(np.uint8))
            cv2.line(frame, points_inner[-1], points_inner[0],
                     color_tuple, max(1, line_width - 1), cv2.LINE_AA)

    def _render_filled_circular(self, frame, audio, angles, line_width):
        waveform_points = []
        for i in range(len(audio)):
            amplitude = audio[i]
            angle = angles[i]
            radius = self.max_radius * (1 + amplitude * 0.3)

            x = int(self.center_x + radius * np.cos(angle))
            y = int(self.center_y + radius * np.sin(angle))
            waveform_points.append((x, y))

        if len(waveform_points) > 2:
            pts = np.array(waveform_points, np.int32)
            # Fill with semi-transparent color
            color = self.get_color_gradient(0.5)
            fill_color = tuple(int(c * 0.3) for c in color)
            cv2.fillPoly(frame, [pts], fill_color)

            # Draw outline with gradient
            for i in range(len(waveform_points) - 1):
                color_ratio = i / max(len(waveform_points) - 1, 1)
                color = self.get_color_gradient(color_ratio)
                color_tuple = tuple(int(c) for c in color)
                cv2.line(frame, waveform_points[i], waveform_points[i + 1],
                         color_tuple, line_width, cv2.LINE_AA)
            color = self.get_color_gradient(1.0)
            color_tuple = tuple(int(c) for c in color)
            cv2.line(frame, waveform_points[-1], waveform_points[0],
                     color_tuple, line_width, cv2.LINE_AA)

    def _render_bars_circular(self, frame, audio, angles, line_width):
        # Reduce number of bars for cleaner look
        step = max(1, len(audio) // 72)

        for i in range(0, len(audio), step):
            amplitude = abs(audio[i])
            angle = angles[i]
            bar_length = self.max_radius * amplitude * 0.5

            inner_r = self.max_radius * 0.9
            outer_r = inner_r + bar_length

            start_x = int(self.center_x + inner_r * np.cos(angle))
            start_y = int(self.center_y + inner_r * np.sin(angle))
            end_x = int(self.center_x + outer_r * np.cos(angle))
            end_y = int(self.center_y + outer_r * np.sin(angle))

            color_ratio = i / max(len(audio) - 1, 1)
            color = self.get_color_gradient(color_ratio)
            alpha = max(0.3, amplitude * 0.7 + 0.3)
            color = (color * alpha).astype(np.uint8)
            color_tuple = tuple(int(c) for c in color)

            cv2.line(frame, (start_x, start_y), (end_x, end_y),
                     color_tuple, line_width + 1, cv2.LINE_AA)

        return frame

    def _render_energy_circular(self, frame, audio, angles, line_width):
        """Energy style: line thickness and brightness vary with local amplitude."""
        points = []
        for i in range(len(audio)):
            amplitude = audio[i]
            angle = angles[i]
            r = self.max_radius * (1.0 + amplitude * 0.2)
            x = int(self.center_x + r * np.cos(angle))
            y = int(self.center_y + r * np.sin(angle))
            points.append((x, y))

        if len(points) < 2:
            return

        for i in range(len(points) - 1):
            local_energy = abs(audio[i])
            # Thickness varies with energy
            thickness = max(1, int(line_width * (1 + local_energy * 3)))
            thickness = min(thickness, line_width * 5)

            color_ratio = i / max(len(points) - 1, 1)
            color = self.get_color_gradient(color_ratio)
            # Brightness varies with energy
            alpha = max(0.25, local_energy * 0.75 + 0.25)
            color = (color * alpha).astype(np.uint8)
            color_tuple = tuple(int(c) for c in color)

            cv2.line(frame, points[i], points[i + 1],
                     color_tuple, thickness, cv2.LINE_AA)

        # Close the loop
        local_energy = abs(audio[-1])
        thickness = max(1, int(line_width * (1 + local_energy * 3)))
        thickness = min(thickness, line_width * 5)
        color = self.get_color_gradient(1.0)
        alpha = max(0.25, local_energy * 0.75 + 0.25)
        color = (color * alpha).astype(np.uint8)
        color_tuple = tuple(int(c) for c in color)
        cv2.line(frame, points[-1], points[0],
                 color_tuple, thickness, cv2.LINE_AA)
