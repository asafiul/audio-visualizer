from typing import Dict, Type, Any
from .base_layer import BaseLayer


class LayerRegistry:
    def __init__(self):
        self._layer_classes: Dict[str, Type[BaseLayer]] = {}
        self._register_default_layers()
    
    def _register_default_layers(self):
        from .layers.background_layer import BackgroundLayer
        from .layers.particles_layer import ParticlesLayer
        from .layers.spectrum_layer import SpectrumLayer
        from .layers.waveform_layer import WaveformLayer
        from .layers.effects_layer import EffectsLayer
        
        self.register('background', BackgroundLayer)
        self.register('particles', ParticlesLayer)
        self.register('spectrum', SpectrumLayer)
        self.register('waveform', WaveformLayer)
        self.register('effects', EffectsLayer)
    
    def register(self, name: str, layer_class: Type[BaseLayer]):
        if not issubclass(layer_class, BaseLayer):
            raise TypeError(f"Layer must inherit from BaseLayer: {layer_class}")
        self._layer_classes[name] = layer_class
    
    def create_layer(self, name: str, config: Dict[str, Any], 
                     audio_processor, width: int, height: int) -> BaseLayer:
        if name not in self._layer_classes:
            raise KeyError(f"Layer type not registered: {name}")
        
        layer_class = self._layer_classes[name]
        return layer_class(config, audio_processor, width, height)
    
    def get_available_layers(self) -> list:
        return list(self._layer_classes.keys())