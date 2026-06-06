import cv2
import numpy as np
from ..base_layer import BaseLayer


class EnergyRingsLayer(BaseLayer):
    """
    Energy Rings - concentric rings that breathe with different frequency bands.
    
    Each ring is assigned a frequency range and a radial zone.
    The ring's radius smoothly oscillates within its zone based on audio energy.
    Rings never overlap — each stays within its own bounded slot.
    Inner rings = high frequencies, outer rings = low frequencies (bass).
    """
    layer_type = "energy_rings"

    def __init__(self, config, audio_processor, width, height):
        super().__init__(config, audio_processor, width, height)
        self.layer_config = config["pipeline"].get("energy_rings", {})
        self.center_x = width // 2
        self.center_y = height // 2

        self.num_rings = self.layer_config.get("num_rings", 8)
        self.base_thickness = self.layer_config.get("base_thickness", 2)
        self.pulse_strength = self.layer_config.get("pulse_strength", 0.5)
        self.rotation_speed = self.layer_config.get("rotation_speed", 0.15)
        self.glow_enabled = self.layer_config.get("glow_enabled", True)

        # Calculate ring zones — each ring gets an equal radial band
        # Total usable radius
        min_r = 40  # innermost ring center
        max_r = int(min(width, height) * 0.4)  # outermost ring center
        
        # Each ring gets a zone: [zone_start, zone_end]
        # Ring radius oscillates within this zone
        zone_size = (max_r - min_r) / self.num_rings
        self.ring_zones = []
        for i in range(self.num_rings):
            zone_start = min_r + i * zone_size
            zone_end = min_r + (i + 1) * zone_size
            # The ring's center is the midpoint; it can move ±margin within the zone
            center = (zone_start + zone_end) / 2
            margin = zone_size * 0.35  # max displacement from center (won't overlap)
            self.ring_zones.append({
                'center': center,
                'margin': margin,
                'min': zone_start + 2,  # small gap so rings don't touch
                'max': zone_end - 2,
            })

        # State for smooth animation
        self.smoothed_energies = np.zeros(self.num_rings)
        self.prev_rms = 0.0

    def _get_frequency_bands(self, audio_segment):
        """Split audio into frequency bands for each ring."""
        if audio_segment is None or len(audio_segment) < 256:
            return np.zeros(self.num_rings)

        fft_size = min(4096, len(audio_segment))
        windowed = audio_segment[:fft_size] * np.hanning(fft_size)
        fft = np.abs(np.fft.rfft(windowed))

        # Limit to useful frequency range (~12kHz)
        sr = self.audio.sample_rate if hasattr(self.audio, '_sample_rate') and self.audio.sample_rate > 0 else 44100
        max_useful_freq = 12000
        max_bin_index = min(len(fft), int(max_useful_freq * fft_size / sr))
        max_bin_index = max(max_bin_index, self.num_rings * 2)
        fft = fft[:max_bin_index]

        fft = np.log1p(fft)

        max_val = np.max(fft)
        if max_val > 0:
            fft = fft / max_val

        # Split into bands using logarithmic spacing
        bands = np.zeros(self.num_rings)
        if len(fft) < self.num_rings:
            return bands

        log_centers = np.logspace(
            np.log10(1),
            np.log10(len(fft) - 1),
            self.num_rings
        )
        log_edges = np.zeros(self.num_rings + 1)
        log_edges[0] = max(0, log_centers[0] - (log_centers[1] - log_centers[0]) / 2)
        log_edges[-1] = min(len(fft), log_centers[-1] + (log_centers[-1] - log_centers[-2]) / 2)
        for i in range(1, self.num_rings):
            log_edges[i] = (log_centers[i - 1] + log_centers[i]) / 2

        for i in range(self.num_rings):
            start = int(log_edges[i])
            end = int(log_edges[i + 1])
            start = max(0, min(start, len(fft) - 1))
            end = max(start + 1, min(end, len(fft)))
            bands[i] = np.mean(fft[start:end])

        # Balance: boost higher bands slightly
        freq_balance = np.linspace(0.7, 1.4, self.num_rings)
        bands = bands * freq_balance

        # Normalize
        max_band = np.max(bands)
        if max_band > 0:
            bands = bands / max_band

        return bands

    def _render_direct(self, time: float, frame: np.ndarray) -> np.ndarray:
        audio_segment = self.audio.get_audio_segment(time, 0.08)

        # Get frequency band energies
        band_energies = self._get_frequency_bands(audio_segment)

        # Overall RMS for global reactivity
        if audio_segment is not None and len(audio_segment) > 0:
            rms = np.sqrt(np.mean(audio_segment ** 2))
        else:
            rms = 0
        rms = self.prev_rms * 0.7 + rms * 0.3
        self.prev_rms = rms

        # Mix band-specific energy with overall RMS so ALL rings react
        for i in range(self.num_rings):
            mixed = band_energies[i] * 0.6 + rms * 3.0 * 0.4
            mixed = min(mixed, 1.0)

            # Responsive smoothing — fast attack, moderate release (like speaker cones)
            if mixed > self.smoothed_energies[i]:
                self.smoothed_energies[i] = self.smoothed_energies[i] * 0.4 + mixed * 0.6
            else:
                self.smoothed_energies[i] = self.smoothed_energies[i] * 0.8 + mixed * 0.2

        # Slow rotation for visual interest
        rotation = time * self.rotation_speed

        # Draw rings (inner = high freq, outer = low freq)
        for i in range(self.num_rings):
            # Ring index: 0 = innermost (highs), num_rings-1 = outermost (bass)
            freq_idx = self.num_rings - 1 - i
            energy = self.smoothed_energies[freq_idx]

            zone = self.ring_zones[i]

            # Ring radius oscillates within its zone based on energy
            # Like a speaker cone: pushes outward with audio energy
            # Use full zone range for dramatic movement
            displacement = energy * zone['margin'] * self.pulse_strength * 4.0
            radius = int(zone['center'] + displacement)
            
            # Clamp to zone boundaries (rings never overlap)
            radius = max(int(zone['min']), min(radius, int(zone['max'])))

            if radius < 3:
                continue

            # All rings use primary color (uniform look)
            color = self.get_color_gradient(0.0)

            # Brightness based on energy — always visible, brighter when active
            brightness = 0.3 + energy * 0.7
            ring_color = (color * brightness).astype(np.uint8)
            color_tuple = tuple(int(c) for c in ring_color)

            # Thickness varies gently with energy
            thickness = max(1, int(self.base_thickness + energy * 3))

            # Slight elliptical distortion for organic feel
            axes_x = radius
            axes_y = int(radius * (0.97 + 0.03 * np.sin(rotation * 1.5 + i * 0.7)))
            angle_deg = int(np.degrees(rotation + i * 0.4))

            cv2.ellipse(frame, (self.center_x, self.center_y),
                        (axes_x, axes_y), angle_deg, 0, 360,
                        color_tuple, thickness, cv2.LINE_AA)

            # Glow effect for high-energy rings
            if self.glow_enabled and energy > 0.4:
                glow_alpha = (energy - 0.4) * 0.5
                glow_color = (color * glow_alpha).astype(np.uint8)
                glow_tuple = tuple(int(c) for c in glow_color)
                glow_thickness = thickness + 2
                cv2.ellipse(frame, (self.center_x, self.center_y),
                            (axes_x + 2, axes_y + 2), angle_deg, 0, 360,
                            glow_tuple, glow_thickness, cv2.LINE_AA)

        # Center dot pulses gently with overall RMS
        center_size = max(2, int(3 + rms * 8))
        center_color = self.get_color_gradient(0.0)
        center_brightness = max(0.3, min(1.0, rms * 2))
        center_c = (center_color * center_brightness).astype(np.uint8)
        center_tuple = tuple(int(c) for c in center_c)
        cv2.circle(frame, (self.center_x, self.center_y), center_size,
                   center_tuple, -1, cv2.LINE_AA)

        return frame
