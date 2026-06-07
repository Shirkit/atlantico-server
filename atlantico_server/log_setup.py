"""Centralized logging configuration for atlantico-server.

Provides consistent logging across CLI and TUI modes with proper log levels,
emoji indicators, and file output for easy tailing.
"""

import logging
import sys
import os


# Log file path
LOG_PATH = os.environ.get('ATLANTICO_SERVER_LOG', 'run/logs/server.log')

# Emoji indicators for different log levels
LEVEL_ICONS = {
    logging.DEBUG: '🔍',
    logging.INFO: 'ℹ️',
    logging.WARNING: '⚠️',
    logging.ERROR: '❌',
    logging.CRITICAL: '🚨',
}


class EmojiFormatter(logging.Formatter):
    """Formatter that adds emoji indicators based on log level"""
    
    def format(self, record):
        # Format: [YYYY-MM-DD HH:MM:SS.mmm] (LEVEL) message (with milliseconds)
        timestamp = self.formatTime(record, '%Y-%m-%d %H:%M:%S')
        # Add milliseconds
        timestamp_with_ms = f"{timestamp}.{int(record.msecs):03d}"
        level = record.levelname
        return f"[{timestamp_with_ms}] ({level}) {record.getMessage()}"


def setup_logging(debug: bool = False, enable_stdout: bool = True) -> logging.Logger:
    """Setup logging with file output (for TUI tailing) and optional stdout.
    
    Args:
        debug: Enable DEBUG level logging
        enable_stdout: Enable stdout handler (disable for TUI mode to prevent interference)
        
    Returns:
        The configured logger instance
    """
    
    # Get or create the server logger
    logger = logging.getLogger('atlantico_server')
    # Prevent duplicate messages by disabling propagation to the root logger
    logger.propagate = False
    
    # Clear existing handlers to prevent duplicates
    for h in logger.handlers[:]:
        logger.removeHandler(h)
    
    # Also clear root handlers to prevent other libraries from cluttering the log
    rl = logging.getLogger()
    for h in rl.handlers[:]:
        rl.removeHandler(h)

    # Set level based on debug flag
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    
    # Always create file handler (TUI will tail this file)
    try:
        os.makedirs(os.path.dirname(LOG_PATH) or '.', exist_ok=True)
        file_handler = logging.FileHandler(LOG_PATH, mode='a', encoding='utf-8')  # 'a' to append
        file_handler.setFormatter(EmojiFormatter())
        file_handler.setLevel(logging.DEBUG if debug else logging.INFO)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not create log file: {e}")
    
    # Add stdout handler only if requested (disabled in TUI mode)
    if enable_stdout:
        stdout_handler = logging.StreamHandler(stream=sys.stdout)
        stdout_handler.setFormatter(EmojiFormatter())
        stdout_handler.setLevel(logging.DEBUG if debug else logging.INFO)
        logger.addHandler(stdout_handler)
    
    return logger


def get_logger(name: str = 'atlantico_server') -> logging.Logger:
    """Get a logger instance.
    
    Args:
        name: Logger name (default: atlantico_server)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)
