import cv2
import numpy as np
from ..base_layer import BaseLayer


class BackgroundLayer(BaseLayer):
    layer_type = "background"
    
    def _render_direct(self, time: float, frame: np.ndarray) -> np.ndarray:
        bg_config = self.layer_config
        bg_type = bg_config.get('type', 'gradient')
        
        # Use per-layer color overrides (color_primary / color_secondary),
        # falling back to the old color1/color2 keys, then to dark defaults.
        color1 = np.array(
            bg_config.get('color_primary',
                bg_config.get('color1', [10, 10, 30])),
            dtype=np.uint8
        )
        color2 = np.array(
            bg_config.get('color_secondary',
                bg_config.get('color2', [30, 10, 50])),
            dtype=np.uint8
        )
        
        if bg_type == 'gradient':
            direction = bg_config.get('direction', 'vertical')
            
            if direction == 'vertical':
                y = np.arange(self.height, dtype=np.float32)
                ratio = y / (self.height - 1) if self.height > 1 else 0
                ratio = ratio.reshape(-1, 1, 1)
                frame = (color1 * (1 - ratio) + color2 * ratio).astype(np.uint8)
                frame = np.repeat(frame, self.width, axis=1)
                
            elif direction == 'horizontal':
                x = np.arange(self.width, dtype=np.float32)
                ratio = x / (self.width - 1) if self.width > 1 else 0
                ratio = ratio.reshape(1, -1, 1)
                frame = (color1 * (1 - ratio) + color2 * ratio).astype(np.uint8)
                frame = np.repeat(frame, self.height, axis=0)
                
            elif direction == 'radial':
                center_x, center_y = self.width // 2, self.height // 2
                y_indices, x_indices = np.indices((self.height, self.width))
                
                distances = np.sqrt((x_indices - center_x)**2 + (y_indices - center_y)**2)
                max_distance = np.sqrt(center_x**2 + center_y**2)
                ratio = distances / max_distance
                
                ratio = ratio[:, :, np.newaxis]
                frame = (color1 * (1 - ratio) + color2 * ratio).astype(np.uint8)
        
        elif bg_type == 'animated':
            # Animated background: subtle, slow-moving dark waves
            # Uses color_primary/color_secondary as the two gradient endpoints
            wave_speed1 = bg_config.get('wave_speed1', 0.4)
            wave_speed2 = bg_config.get('wave_speed2', 0.3)
            wave_speed3 = bg_config.get('wave_speed3', 0.5)
            wave_amplitude = bg_config.get('wave_amplitude', 0.15)
            
            y_indices, x_indices = np.indices((self.height, self.width))
            
            # Slow, gentle waves for a subtle animated background
            wave1 = np.sin(y_indices * 0.005 + time * wave_speed1) * wave_amplitude
            wave2 = np.sin(x_indices * 0.004 + time * wave_speed2 + 1.5) * wave_amplitude
            wave3 = np.sin((x_indices + y_indices) * 0.003 + time * wave_speed3) * wave_amplitude * 0.5
            
            # Base gradient ratio (vertical) + wave perturbation
            base_ratio = y_indices.astype(np.float32) / max(self.height - 1, 1)
            ratio = np.clip(base_ratio + wave1 + wave2 + wave3, 0.0, 1.0)
            ratio = ratio[:, :, np.newaxis]
            
            # Interpolate between the two dark colors
            c1 = color1.astype(np.float32)
            c2 = color2.astype(np.float32)
            frame = (c1 * (1 - ratio) + c2 * ratio).astype(np.uint8)
        
        elif bg_type == 'solid':
            # Solid background: fill with color_primary (or explicit 'color' key)
            color = np.array(
                bg_config.get('color', bg_config.get('color_primary', [0, 0, 0])),
                dtype=np.uint8
            )
            frame[:] = color
        
        blur = bg_config.get('blur', 0)
        if blur > 0:
            kernel_size = int(blur * 2) + 1
            kernel_size = max(3, kernel_size | 1)
            frame = cv2.GaussianBlur(frame, (kernel_size, kernel_size), 0)
        
        return frame
