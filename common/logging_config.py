import logging
import os
import re
import sys
from typing import Optional


class SensitiveDataFilter(logging.Filter):
    """Filter to mask sensitive data in log records."""
    
    PATTERNS = [
        (re.compile(r'(password["\']?\s*[:=]\s*["\']?)([^"\'}\s,]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'(api[_-]?key["\']?\s*[:=]\s*["\']?)([^"\'}\s,]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'(token["\']?\s*[:=]\s*["\']?)([^"\'}\s,]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'(authorization["\']?\s*[:=]\s*["\']?)([^"\'}\s,]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'(bearer\s+)([^\s,}\'\"]+)', re.IGNORECASE), r'\1***MASKED***'),
        (re.compile(r'(secret["\']?\s*[:=]\s*["\']?)([^"\'}\s,]+)', re.IGNORECASE), r'\1***MASKED***'),
    ]
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Mask sensitive data in the log message."""
        if isinstance(record.msg, str):
            for pattern, replacement in self.PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)
        
        if hasattr(record, 'args') and record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._mask_value(v) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(self._mask_value(arg) for arg in record.args)
        
        return True
    
    def _mask_value(self, value):
        """Mask sensitive values in arguments."""
        if isinstance(value, str):
            for pattern, replacement in self.PATTERNS:
                value = pattern.sub(replacement, value)
        return value


def setup_logging(
    component_name: str,
    log_level: Optional[str] = None,
    correlation_id: Optional[str] = None
) -> logging.Logger:
    """
    Set up logging configuration for a component.
    
    Args:
        component_name: Name of the component (e.g., 'controller', 'chunkserver', 'cli')
        log_level: Log level (DEBUG, INFO, WARNING, ERROR). Defaults to LOG_LEVEL env var or INFO
        correlation_id: Optional correlation ID to include in log format
        
    Returns:
        Configured logger instance
    """
    if log_level is None:
        log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    
    level = getattr(logging, log_level, logging.INFO)
    
    logger = logging.getLogger(component_name)
    logger.setLevel(level)
    
    if logger.handlers:
        return logger
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    
    if correlation_id:
        formatter = logging.Formatter(
            f'%(asctime)s - %(name)s - %(levelname)s - [{correlation_id}] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    handler.setFormatter(formatter)
    handler.addFilter(SensitiveDataFilter())
    
    logger.addHandler(handler)
    logger.propagate = False
    
    return logger


def get_logger(name: str, correlation_id: Optional[str] = None) -> logging.Logger:
    """
    Get a logger with the given name.
    
    Args:
        name: Logger name (typically __name__)
        correlation_id: Optional correlation ID for request tracing
        
    Returns:
        Logger instance
    """
    logger = logging.getLogger(name)
    
    if correlation_id and not any(
        isinstance(f, SensitiveDataFilter) for handler in logger.handlers for f in handler.filters
    ):
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                formatter = logging.Formatter(
                    f'%(asctime)s - %(name)s - %(levelname)s - [{correlation_id}] - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )
                handler.setFormatter(formatter)
    
    return logger


def set_correlation_id(logger: logging.Logger, correlation_id: str) -> None:
    """
    Update logger handlers to include correlation ID in format.
    
    Args:
        logger: Logger instance to update
        correlation_id: Correlation ID to include
    """
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            formatter = logging.Formatter(
                f'%(asctime)s - %(name)s - %(levelname)s - [{correlation_id}] - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
