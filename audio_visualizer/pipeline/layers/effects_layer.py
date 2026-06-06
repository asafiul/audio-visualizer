import cv2
import numpy as np
from ..base_layer import BaseLayer


class EffectsLayer(BaseLayer):
    layer_type = "effects"

    def _render_direct(self, time: float, frame: np.ndarray) -> np.ndarray:
        effects = self.layer_config.get("effects", [])

        for effect in effects:
            if effect == "glow":
                frame = self._apply_glow(frame)
            elif effect == "vignette":
                frame = self._apply_vignette(frame)
            elif effect == "grain":
                frame = self._apply_grain(frame, time)
            elif effect == "chromatic":
                frame = self._apply_chromatic_aberration(frame, time)

        return frame

    def _apply_glow(self, frame):
        intensity = self.layer_config.get("glow_intensity", 0.3)
        size = self.layer_config.get("glow_size", 15)

        if intensity <= 0:
            return frame

        # Ensure kernel size is odd
        if size % 2 == 0:
            size += 1

        blurred = cv2.GaussianBlur(frame, (size, size), 0)
        result = cv2.addWeighted(frame, 1.0, blurred, intensity, 0)
        return np.clip(result, 0, 255).astype(np.uint8)

    def _apply_vignette(self, frame):
        strength = self.layer_config.get("vignette_strength", 0.3)

        if strength <= 0:
            return frame

        height, width = frame.shape[:2]
        kernel_x = cv2.getGaussianKernel(width, width / 3)
        kernel_y = cv2.getGaussianKernel(height, height / 3)
        kernel = kernel_y * kernel_x.T

        mask = kernel / kernel.max()
        # Invert: 1 at center, fading to (1-strength) at edges
        vignette_mask = 1.0 - ((1.0 - mask) * strength)
        vignette_mask = np.clip(vignette_mask, 0, 1)

        # Apply to all channels
        result = frame.astype(np.float32)
        for i in range(3):
            result[:, :, i] = result[:, :, i] * vignette_mask

        return np.clip(result, 0, 255).astype(np.uint8)

    def _apply_grain(self, frame, time):
        amount = self.layer_config.get("grain_amount", 0.05)

        if amount <= 0:
            return frame

        noise = np.random.randn(*frame.shape) * amount * 255
        return np.clip(frame.astype(np.float32) + noise, 0, 255).astype(np.uint8)

    def _apply_chromatic_aberration(self, frame, time):
        shift = self.layer_config.get("chromatic_shift", 2)

        if shift <= 0:
            return frame

        b, g, r = cv2.split(frame)

        # Red channel shifts one direction, blue shifts the opposite
        shift_x = int(np.sin(time * 0.5) * shift)
        shift_y = int(np.cos(time * 0.35) * shift)

        if shift_x != 0 or shift_y != 0:
            # Red shifts in positive direction
            M_r = np.float32([[1, 0, shift_x], [0, 1, shift_y]])
            r = cv2.warpAffine(r, M_r, (self.width, self.height))
            # Blue shifts in negative direction (opposite)
            M_b = np.float32([[1, 0, -shift_x], [0, 1, -shift_y]])
            b = cv2.warpAffine(b, M_b, (self.width, self.height))

        return cv2.merge([b, g, r])
