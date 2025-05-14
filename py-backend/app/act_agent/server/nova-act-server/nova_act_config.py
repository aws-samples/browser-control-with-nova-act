"""
Configuration settings for Nova Act browser automation
Now imports from central config.py
"""

import sys
import os

# Add the parent directory to path to allow importing config from app.libs
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../../"))

# Import centralized settings
from app.libs.config import (
    BROWSER_HEADLESS,
    BROWSER_START_URL,
    BROWSER_MAX_STEPS,
    BROWSER_TIMEOUT,
    BROWSER_URL_TIMEOUT,
    LOGS_DIRECTORY,
    BROWSER_RECORD_VIDEO,
    BROWSER_QUIET_MODE,
    BROWSER_USER_AGENT,
    BROWSER_USER_DATA_DIR,
    BROWSER_CLONE_USER_DATA,
    BROWSER_SCREENSHOT_QUALITY,
    BROWSER_SCREENSHOT_MAX_WIDTH,
    MCP_SERVER_NAME,
    MCP_VERSION,
    MCP_TRANSPORT,
    MCP_PORT,
    MCP_HOST,
    MCP_LOG_LEVEL
)

# Default browser settings
DEFAULT_BROWSER_SETTINGS = {
    # Browser display settings
    "headless": BROWSER_HEADLESS,
    "start_url": BROWSER_START_URL,
    
    # Performance and timeout settings
    "max_steps": BROWSER_MAX_STEPS,
    "timeout": BROWSER_TIMEOUT,
    "go_to_url_timeout": BROWSER_URL_TIMEOUT,
    
    # Logging and debugging
    "logs_directory": LOGS_DIRECTORY,
    "record_video": BROWSER_RECORD_VIDEO,
    "quiet": BROWSER_QUIET_MODE,
    
    # User agent and authentication settings
    "user_agent": BROWSER_USER_AGENT,
    
    # Browser profile settings (for authentication)
    "user_data_dir": BROWSER_USER_DATA_DIR,
    "clone_user_data_dir": BROWSER_CLONE_USER_DATA,
    
    # Screenshot settings
    "screenshot_quality": BROWSER_SCREENSHOT_QUALITY,
    "screenshot_max_width": BROWSER_SCREENSHOT_MAX_WIDTH,
}

# MCP server settings
MCP_SERVER_SETTINGS = {
    "server_name": MCP_SERVER_NAME,
    "version": MCP_VERSION,
    "transport": MCP_TRANSPORT,
    "port": MCP_PORT,
    "host": MCP_HOST,
    "log_level": MCP_LOG_LEVEL,
}
