from abc import ABC, abstractmethod
import numpy as np
import cv2
from typing import Dict, Any


class BaseLayer(ABC):
    layer_type: str = "base"
    
    def __init__(self, config: Dict[str, Any], audio_processor, width: int, height: int):
        self.config = config
        self.audio = audio_processor
        self.width = width
        self.height = height
        
        layer_name = self.layer_type
        
        if 'pipeline' in config and layer_name in config['pipeline']:
            self.layer_config = config['pipeline'][layer_name]
        else:
            self.layer_config = {}
        
        self.opacity = self.layer_config.get('opacity', 1.0)
        self.blend_mode = self.layer_config.get('blend_mode', 'overwrite')
    
    def render(self, time: float, frame: np.ndarray) -> np.ndarray:
        if self.blend_mode == 'overwrite' or self.opacity >= 0.99:
            return self._render_direct(time, frame)
        else:
            layer_canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            layer_canvas = self._render_direct(time, layer_canvas)
            return self._apply_blend(frame, layer_canvas)
    
    @abstractmethod
    def _render_direct(self, time: float, canvas: np.ndarray) -> np.ndarray:
        pass
    
    def _apply_blend(self, background: np.ndarray, foreground: np.ndarray) -> np.ndarray:
        if self.blend_mode == 'overwrite':
            return foreground
        elif self.blend_mode == 'normal':
            return cv2.addWeighted(background, 1 - self.opacity, 
                                 foreground, self.opacity, 0)
        elif self.blend_mode == 'add':
            blended = cv2.add(background, (foreground * self.opacity).astype(np.uint8))
            return np.clip(blended, 0, 255)
        elif self.blend_mode == 'multiply':
            bg_float = background.astype(np.float32) / 255.0
            fg_float = foreground.astype(np.float32) / 255.0
            result = bg_float * (fg_float * self.opacity + (1 - self.opacity))
            return (result * 255).astype(np.uint8)
        elif self.blend_mode == 'screen':
            bg_float = 1.0 - background.astype(np.float32) / 255.0
            fg_float = 1.0 - foreground.astype(np.float32) / 255.0
            result = 1.0 - (bg_float * fg_float * self.opacity + bg_float * (1 - self.opacity))
            return (result * 255).astype(np.uint8)
        else:
            return foreground
    
    def get_color_gradient(self, ratio: float):
        colors = self.config['visualization']['colors']
        primary = np.array(colors['primary'])
        secondary = np.array(colors['secondary'])
        return (primary * (1 - ratio) + secondary * ratio).astype(np.uint8)