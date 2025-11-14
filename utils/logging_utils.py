"""Simple logging utility wrapper."""
import logging
from typing import Optional, Dict

_loggers: Dict[str, logging.Logger] = {}


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Get or create a logger instance.
    
    Args:
        name: Logger name (typically __name__)
        level: Logging level
        
    Returns:
        Logger instance
    """
    if name not in _loggers:
        logger = logging.getLogger(name)
        logger.setLevel(level)
        
        # Create console handler if not exists
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(level)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        _loggers[name] = logger
    
    return _loggers[name]

