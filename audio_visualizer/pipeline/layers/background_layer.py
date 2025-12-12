import cv2
import numpy as np
from ..base_layer import BaseLayer


class BackgroundLayer(BaseLayer):
    layer_type = "background"
    
    def _render_direct(self, time: float, frame: np.ndarray) -> np.ndarray:
        bg_config = self.layer_config
        bg_type = bg_config['type']
        
        if bg_type == 'gradient':
            colors = self.config['visualization']['colors']
            color1 = np.array(bg_config.get('color1', colors['primary']), dtype=np.uint8)
            color2 = np.array(bg_config.get('color2', colors['secondary']), dtype=np.uint8)
            direction = bg_config['direction']
            
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
            colors = self.config['visualization']['colors']
            color1 = np.array(colors['primary'], dtype=np.uint8)
            color2 = np.array(colors['secondary'], dtype=np.uint8)
            
            wave_speed1 = bg_config.get('wave_speed1', 2.0)
            wave_speed2 = bg_config.get('wave_speed2', 1.5)
            wave_speed3 = bg_config.get('wave_speed3', 3.0)
            wave_amplitude = bg_config.get('wave_amplitude', 0.3)
            
            y_indices, x_indices = np.indices((self.height, self.width))
            
            wave1 = np.sin(y_indices * 0.01 + time * wave_speed1) * wave_amplitude + 0.7
            wave2 = np.sin(y_indices * 0.015 + time * wave_speed2) * wave_amplitude + 0.7
            wave3 = np.sin(x_indices * 0.01 + time * wave_speed3) * wave_amplitude + 0.7
            
            ratio = (wave1 + wave2 + wave3) / 3
            ratio = ratio[:, :, np.newaxis]
            
            frame = (color1 * ratio + color2 * (1 - ratio)).astype(np.uint8)
        
        elif bg_type == 'solid':
            colors = self.config['visualization']['colors']
            color = np.array(bg_config.get('color', colors['background']), dtype=np.uint8)
            frame[:] = color
        
        blur = bg_config.get('blur', 0)
        if blur > 0:
            kernel_size = int(blur * 2) + 1
            kernel_size = max(3, kernel_size | 1)
            frame = cv2.GaussianBlur(frame, (kernel_size, kernel_size), 0)
        
        return frame