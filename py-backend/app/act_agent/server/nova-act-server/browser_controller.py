import os
import time
import base64
import tempfile
import logging
from typing import Dict, Any, Optional, Tuple
from nova_act import NovaAct
from nova_act_config import DEFAULT_BROWSER_SETTINGS

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("browser_controller")

class BrowserController:
    def __init__(self):
        self.nova = None
        self.api_key = os.environ.get("NOVA_ACT_API_KEY")
        self.screenshots_dir = os.path.join(tempfile.gettempdir(), "nova_browser_screenshots")
        os.makedirs(self.screenshots_dir, exist_ok=True)
    
    def is_initialized(self) -> bool:
        return self.nova is not None and hasattr(self.nova, 'page')
    
    def normalize_url(self, url: str) -> str:
        if url == "about:blank":
            return url
        if not url.startswith(('http://', 'https://')):
            return 'https://' + url
        return url

    def initialize_browser(self, headless: bool = True, starting_url: str = None) -> Tuple[bool, Optional[Dict[str, Any]]]:
        print(f"DEBUG: Initializing browser with headless={headless}")
        if not self.api_key:
            logger.error("Nova Act API key not found in environment variables")
            return False, None
            
        try:
            url = starting_url or DEFAULT_BROWSER_SETTINGS.get("start_url", "https://www.google.com")
            url = self.normalize_url(url)
            browser_config = {
                "starting_page": url,
                "nova_act_api_key": self.api_key,
                "headless": headless,                
                "quiet": DEFAULT_BROWSER_SETTINGS.get("quiet", False),
                "logs_directory": DEFAULT_BROWSER_SETTINGS.get("logs_directory"),
                "record_video": DEFAULT_BROWSER_SETTINGS.get("record_video", False),
            }
            
            self.nova = NovaAct(
                starting_page=url,
                nova_act_api_key=self.api_key,
                headless=headless,
                user_data_dir=DEFAULT_BROWSER_SETTINGS.get("user_data_dir"),
                clone_user_data_dir=DEFAULT_BROWSER_SETTINGS.get("clone_user_data_dir", True),
                #quiet=DEFAULT_BROWSER_SETTINGS.get("quiet", False),
                logs_directory=DEFAULT_BROWSER_SETTINGS.get("logs_directory"),
                record_video=DEFAULT_BROWSER_SETTINGS.get("record_video", False)
            )
            
            self.nova.start()
            self.nova.page.wait_for_load_state("networkidle", timeout=30000)
            
            screenshot_data = self.take_screenshot()
            logger.info("Browser successfully initialized")
            return True, screenshot_data
            
        except Exception as e:
            logger.error(f"Error initializing browser: {str(e)}")
            return False, None

    def go_to_url(self, url: str, wait_until: str = "networkidle", timeout: int = None) -> Dict[str, Any]:
        if not self.is_initialized():
            raise RuntimeError("Browser not initialized")
            
        try:
            url = self.normalize_url(url)            
            self.nova.go_to_url(url)            
            screenshot_data = self.take_screenshot()
            current_url = self.get_current_url()
            
            return {
                "current_url": current_url,
                "screenshot": screenshot_data
            }
            
        except Exception as e:
            logger.error(f"Error navigating to URL: {str(e)}")
            raise
    
    
    def execute_action(self, instruction: str, schema: Dict = None, max_steps: int = 30, timeout: int = 300) -> Any:
        if not self.is_initialized():
            raise RuntimeError("Browser not initialized")
            
        try:
            result = self.nova.act(
                instruction, 
                max_steps=max_steps,
                timeout=timeout,
                schema=schema 
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing action: {str(e)}")
            raise
    
    def take_screenshot(self, max_width=800, quality=70) -> Dict[str, Any]:
        if not self.is_initialized():
            raise RuntimeError("Browser not initialized")
            
        try:
            screenshot_bytes = self.nova.page.screenshot(type='jpeg', quality=quality)
            
            from PIL import Image
            import io
            
            image = Image.open(io.BytesIO(screenshot_bytes))
            
            if image.width > max_width:
                ratio = max_width / image.width
                new_height = int(image.height * ratio)
                image = image.resize((max_width, new_height), Image.LANCZOS)
                
                buffer = io.BytesIO()
                image.save(buffer, format='JPEG', quality=quality)
                screenshot_bytes = buffer.getvalue()
            
            byte_size = len(screenshot_bytes)
            base64_data = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            return {
                "format": "jpeg",
                "data": base64_data,
                "size": byte_size
            }
            
        except Exception as e:
            logger.error(f"Error taking screenshot: {str(e)}")
            return {"format": "jpeg", "data": "", "size": 0}
    
    def get_current_url(self) -> str:
        if not self.is_initialized():
            return "Browser not initialized"
            
        try:
            return self.nova.page.url
        except Exception as e:
            logger.error(f"Error getting current URL: {str(e)}")
            return "Error getting URL"
    
    def get_page_title(self) -> str:
        if not self.is_initialized():
            return "Browser not initialized"
            
        try:
            return self.nova.page.title()
        except Exception as e:
            logger.error(f"Error getting page title: {str(e)}")
            return "Error getting title"
    
    def get_page_content(self) -> str:
        if not self.is_initialized():
            return "Browser not initialized"
            
        try:
            return self.nova.page.content()
        except Exception as e:
            logger.error(f"Error getting page content: {str(e)}")
            return "Error getting content"
    
    def close(self) -> bool:
        if not self.nova:
            return True
            
        try:
            self.nova.close()
            self.nova = None
            return True
            
        except Exception as e:
            logger.error(f"Error closing browser: {str(e)}")
            return False
