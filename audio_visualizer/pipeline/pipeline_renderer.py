import cv2
import numpy as np
from typing import List, Dict, Any

from .layer_registry import LayerRegistry
from ..visualizer_factory import IVisualizer


class PipelineRenderer(IVisualizer):
    def __init__(self, config: Dict[str, Any], audio_processor):
        self.config = config
        self.audio = audio_processor
        self.width = config['video']['width']
        self.height = config['video']['height']
        
        if 'pipeline' not in config:
            raise KeyError("Section 'pipeline' missing in config")
        
        self.layer_registry = LayerRegistry()
        self.layers = self._create_layers()
        print(f"Pipeline created: {len(self.layers)} layers")
    
    def _create_layers(self):
        layers = []
        pipeline_order = self.config['pipeline']['order']
        
        for layer_name in pipeline_order:
            try:
                layer = self.layer_registry.create_layer(
                    layer_name, 
                    self.config, 
                    self.audio, 
                    self.width, 
                    self.height
                )
                layers.append(layer)
                print(f"  + {layer_name}")
            except KeyError as e:
                available = self.layer_registry.get_available_layers()
                raise ValueError(
                    f"Unknown layer: '{layer_name}'. "
                    f"Available layers: {available}"
                ) from e
        
        return layers
    
    def render_frame(self, time: float) -> np.ndarray:
        current_frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        
        for layer in self.layers:
            current_frame = layer.render(time, current_frame)
        
        return current_frame
    
    def get_layer_info(self):
        info = []
        for i, layer in enumerate(self.layers):
            info.append({
                'index': i,
                'name': layer.__class__.__name__,
                'type': layer.layer_type if hasattr(layer, 'layer_type') else 'unknown'
            })
        return info