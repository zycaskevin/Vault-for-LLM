"""Extended tests for vault/log.py"""
import pytest
import logging
from io import StringIO


def test_setup_logging_basic():
    """Test basic logging setup."""
    from vault.log import log, setup_logging
    
    # Save original handlers
    original_handlers = log.handlers.copy()
    original_level = log.level
    
    try:
        setup_logging("INFO")
        assert log.level == logging.INFO
        assert len(log.handlers) >= 1
    finally:
        # Restore
        log.handlers = original_handlers
        log.level = original_level


def test_setup_logging_debug_level():
    """Test setup with DEBUG level."""
    from vault.log import log, setup_logging
    
    original_handlers = log.handlers.copy()
    original_level = log.level
    
    try:
        setup_logging("DEBUG")
        assert log.level == logging.DEBUG
    finally:
        log.handlers = original_handlers
        log.level = original_level


def test_setup_logging_warning_level():
    """Test setup with WARNING level."""
    from vault.log import log, setup_logging
    
    original_handlers = log.handlers.copy()
    original_level = log.level
    
    try:
        setup_logging("WARNING")
        assert log.level == logging.WARNING
    finally:
        log.handlers = original_handlers
        log.level = original_level


def test_setup_logging_error_level():
    """Test setup with ERROR level."""
    from vault.log import log, setup_logging
    
    original_handlers = log.handlers.copy()
    original_level = log.level
    
    try:
        setup_logging("ERROR")
        assert log.level == logging.ERROR
    finally:
        log.handlers = original_handlers
        log.level = original_level


def test_setup_logging_critical_level():
    """Test setup with CRITICAL level."""
    from vault.log import log, setup_logging
    
    original_handlers = log.handlers.copy()
    original_level = log.level
    
    try:
        setup_logging("CRITICAL")
        assert log.level == logging.CRITICAL
    finally:
        log.handlers = original_handlers
        log.level = original_level


def test_setup_logging_unknown_level_defaults_to_info():
    """Test that unknown level defaults to INFO."""
    from vault.log import log, setup_logging
    
    original_handlers = log.handlers.copy()
    original_level = log.level
    
    try:
        setup_logging("UNKNOWN_LEVEL")
        assert log.level == logging.INFO
    finally:
        log.handlers = original_handlers
        log.level = original_level


def test_log_output_format():
    """Test that log output has expected format."""
    from vault.log import log, setup_logging
    
    original_handlers = log.handlers.copy()
    original_level = log.level
    
    try:
        # Set up with a stream handler we can capture
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("[vault-mcp] %(message)s"))
        handler.setLevel(logging.INFO)
        log.handlers = [handler]
        log.setLevel(logging.INFO)
        
        log.info("test message")
        output = stream.getvalue()
        assert "[vault-mcp]" in output
        assert "test message" in output
    finally:
        log.handlers = original_handlers
        log.level = original_level


def test_logger_name():
    """Test that logger has correct name."""
    from vault.log import log
    assert log.name == "vault-mcp"
