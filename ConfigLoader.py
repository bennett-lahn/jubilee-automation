"""
Configuration loader for Jubilee automation system.
Loads system-wide configuration parameters from JSON files.
"""

import json
import os
from typing import Dict, Any

class ConfigLoader:
    """Loads and manages system configuration"""
    
    _instance = None
    _config = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigLoader, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._config is None:
            self._load_config()
    
    def _load_config(self):
        """Load configuration from JSON file"""
        config_path = os.path.join("jubilee_api_config", "system_config.json")
        try:
            with open(config_path, "r") as f:
                self._config = json.load(f)
        except FileNotFoundError:
            print(f"Warning: Config file {config_path} not found, using defaults")
            self._config = self._get_default_config()
        except json.JSONDecodeError as e:
            print(f"Error loading config: {e}, using defaults")
            self._config = self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Return default configuration if file loading fails"""
        return {
            "safety": {
                "safe_z": 195,
                "safe_z_offset": 20,
                "max_weight_per_well": 10.0,
                "weight_tolerance": 0.001
            },
            "machine": {
                "default_feedrate": 3000,
                "tamper_travel_position": 30,
                "tamper_working_position": 50
            },
            "wells": {
                "default_diameter": 15,
                "default_depth": 8,
                "well_spacing_x": 100,
                "well_spacing_y": 100
            }
        }
    
    def get(self, key_path: str, default=None):
        """Get configuration value using dot notation (e.g., 'safety.safe_z')"""
        keys = key_path.split('.')
        value = self._config
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def get_safe_z(self) -> float:
        """Get safe Z height"""
        return self.get("safety.safe_z", 195)
    
    def get_safe_z_offset(self) -> float:
        """Get safe Z offset"""
        return self.get("safety.safe_z_offset", 20)
    
    def get_max_weight_per_well(self) -> float:
        """Get maximum weight per well"""
        return self.get("safety.max_weight_per_well", 10.0)
    
    def get_weight_tolerance(self) -> float:
        """Get weight tolerance"""
        return self.get("safety.weight_tolerance", 0.001)
    
    def get_duet_ip(self) -> str:
        """Get DUET IP address"""
        return self.get("machine.duet_ip", "192.168.1.2")

# Global config instance
config = ConfigLoader()
