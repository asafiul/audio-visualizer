from typing import Dict, Any, Type
from abc import ABC, abstractmethod

class IVisualizer(ABC):
    @abstractmethod
    def render_frame(self, time: float):
        pass
    
    @abstractmethod
    def get_layer_info(self):
        pass


class VisualizerFactory:
    _registry: Dict[str, Type] = {}
    
    @classmethod
    def register(cls, name: str, visualizer_class: Type):
        if not issubclass(visualizer_class, IVisualizer):
            raise TypeError(f"Visualizer must implement IVisualizer: {visualizer_class}")
        cls._registry[name] = visualizer_class
    
    @classmethod
    def create(cls, name: str, config: Dict[str, Any], audio_processor) -> IVisualizer:
        if name not in cls._registry:
            available = list(cls._registry.keys())
            raise ValueError(
                f"Unknown visualizer: '{name}'. "
                f"Available: {available}"
            )
        
        visualizer_class = cls._registry[name]
        return visualizer_class(config, audio_processor)
    
    @classmethod
    def get_available_types(cls) -> list:
        return list(cls._registry.keys())