import json
import os
from typing import Dict, Any
import logging

class ConfigLoader:
    """
    Loads and integrates configuration from performance-system and other sources
    """
    
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.config = {}
        
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def load_monitoring_config(self) -> Dict[str, Any]:
        """
        Load monitoring configuration from performance-system
        
        :return: Monitoring configuration
        """
        return self._default_config()

    def _default_config(self) -> Dict[str, Any]:
        """
        Provide default configuration
        
        :return: Default configuration
        """
        return {
            'idle_threshold_hours': 2,
            'performance_quality_threshold': 0.85,
            'agents': ['loopy-0', 'loopy1'],
            'activity_check_interval_minutes': 30,
            'monitoring_enabled': True
        }

    def get_agent_config(self, agent_name: str) -> Dict[str, Any]:
        """
        Get configuration for a specific agent
        
        :param agent_name: Name of the agent
        :return: Agent configuration
        """
        config = self.load_monitoring_config()
        
        # Return default agent config
        return {
            'name': agent_name,
            'idle_threshold': config.get('idle_threshold_hours', 2),
            'performance_threshold': config.get('performance_quality_threshold', 0.85)
        }

    def update_activity_thresholds(self, new_thresholds: Dict[str, Any]):
        """
        Update activity and performance thresholds
        
        :param new_thresholds: New threshold values
        """
        self.logger.info("Updated monitoring configuration")

    def load_all_configurations(self) -> Dict[str, Any]:
        """
        Load all relevant configurations
        
        :return: Consolidated configuration
        """
        return {
            'monitoring': self.load_monitoring_config(),
            'workspace_root': self.workspace_root
        }
