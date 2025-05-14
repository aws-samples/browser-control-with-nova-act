# Global configuration settings for the application
import os

# LLM Model settings
DEFAULT_MODEL_ID = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"

# Conversation flow settings
MAX_SUPERVISOR_TURNS = 4  # Maximum conversation turns between supervisor and agent
MAX_AGENT_TURNS = 6       # Maximum turns between agent and MCP tools
BROWSER_MAX_STEPS = int(os.environ.get("NOVA_BROWSER_MAX_STEPS", "3"))  # Maximum turns between Nova Act and Browser

# Browser settings - Core
BROWSER_HEADLESS = True  # Set to False for visible browser windows
BROWSER_START_URL = "https://www.google.com"  # Default starting URL
BROWSER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Browser settings - Performance
BROWSER_TIMEOUT = int(os.environ.get("NOVA_BROWSER_TIMEOUT", "100"))
BROWSER_URL_TIMEOUT = int(os.environ.get("NOVA_BROWSER_URL_TIMEOUT", "60"))

# Browser settings - Profiles
BROWSER_USER_DATA_DIR = os.environ.get("NOVA_BROWSER_USER_DATA_DIR", "")
BROWSER_CLONE_USER_DATA = os.environ.get("NOVA_BROWSER_CLONE_USER_DATA", "true").lower() == "true"

# Browser settings - Media
BROWSER_SCREENSHOT_QUALITY = int(os.environ.get("NOVA_BROWSER_SCREENSHOT_QUALITY", "70"))
BROWSER_SCREENSHOT_MAX_WIDTH = int(os.environ.get("NOVA_BROWSER_SCREENSHOT_MAX_WIDTH", "800"))
BROWSER_RECORD_VIDEO = os.environ.get("NOVA_BROWSER_RECORD_VIDEO", "false").lower() == "true"

# API settings
API_TIMEOUT_SECONDS = 60

# Conversation memory settings
MAX_CONVERSATION_MESSAGES = 50  # Maximum number of messages to keep in conversation history
CONVERSATION_STORAGE_TYPE = "memory"  # Options: "memory" or "file"
CONVERSATION_FILE_TTL_DAYS = 7  # Number of days to keep conversation files
CONVERSATION_CLEANUP_INTERVAL = 3600  # Cleanup interval in seconds

# Logging settings
DEBUG_LOGGING = True
LOGS_DIRECTORY = os.environ.get("NOVA_BROWSER_LOGS_DIR", None)
BROWSER_QUIET_MODE = os.environ.get("NOVA_BROWSER_QUIET", "false").lower() == "true"

# MCP server settings
MCP_SERVER_NAME = "nova-browser-automation"
MCP_VERSION = "0.1.0"
MCP_TRANSPORT = os.environ.get("NOVA_MCP_TRANSPORT", "stdio")
MCP_PORT = int(os.environ.get("NOVA_MCP_PORT", "8000"))
MCP_HOST = os.environ.get("NOVA_MCP_HOST", "localhost")
MCP_LOG_LEVEL = os.environ.get("NOVA_MCP_LOG_LEVEL", "WARNING")

# Allow environment variable override of key settings
if os.environ.get("NOVA_BROWSER_HEADLESS", "").lower() in ["true", "false"]:
    BROWSER_HEADLESS = os.environ.get("NOVA_BROWSER_HEADLESS", "false").lower() == "true"