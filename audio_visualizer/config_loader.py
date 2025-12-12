import yaml
import os
from typing import Dict, Any


class ConfigLoader:
    def __init__(self, config_path: str = None):
        self.default_config = self._load_default_config()
        
        if config_path:
            if not os.path.exists(config_path):
                raise FileNotFoundError(f"Config not found: {config_path}")
            self.user_config = self._load_user_config(config_path)
            self.config = self._merge_configs()
        else:
            self.config = self.default_config
    
    def _load_default_config(self) -> Dict[str, Any]:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        default_config_path = os.path.join(base_dir, 'configs', 'default.yaml')
        
        if not os.path.exists(default_config_path):
            raise FileNotFoundError(f"Default config not found: {default_config_path}")
        
        with open(default_config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            
        if not config:
            raise ValueError("Default config is empty or invalid")
        
        return config
    
    def _load_user_config(self, config_path: str) -> Dict[str, Any]:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        if not config:
            raise ValueError(f"Config is empty: {config_path}")
        
        return config
    
    def _merge_configs(self) -> Dict[str, Any]:
        import copy
        
        merged = copy.deepcopy(self.default_config)
        self._deep_update(merged, self.user_config)
        return merged
    
    def _deep_update(self, base: Dict, update: Dict):
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_update(base[key], value)
            else:
                base[key] = value
    
    def get(self, key_path: str):
        keys = key_path.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                raise KeyError(f"Key not found in config: {key_path}")
        
        return value
    
    def require_section(self, section: str):
        if section not in self.config:
            raise KeyError(f"Required section missing in config: {section}")
        return self.config[section]


class ConfigError(Exception):
    pass