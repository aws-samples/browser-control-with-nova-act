import os
import base64
import tempfile
import logging
import traceback
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

    def initialize_browser(self, headless: bool = True, starting_url: str = None) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        print(f"DEBUG: Initializing browser with headless={headless}")
        if not self.api_key:
            error_msg = "Nova Act API key not found in environment variables"
            logger.error(error_msg)
            return False, None, error_msg
            
        try:
            url = starting_url or DEFAULT_BROWSER_SETTINGS.get("start_url", "https://www.google.com")
            url = self.normalize_url(url)
            
            self.nova = NovaAct(
                starting_page=url,
                nova_act_api_key=self.api_key,
                headless=headless,
                user_data_dir=DEFAULT_BROWSER_SETTINGS.get("user_data_dir"),
                clone_user_data_dir=DEFAULT_BROWSER_SETTINGS.get("clone_user_data_dir", True),
                #quiet=DEFAULT_BROWSER_SETTINGS.get("quiet", False),
                screen_width=1600,
                screen_height=1200,
                logs_directory=DEFAULT_BROWSER_SETTINGS.get("logs_directory"),
                record_video=DEFAULT_BROWSER_SETTINGS.get("record_video", False)
            )
            
            self.nova.start()
            try:
                # First wait for DOM to be ready (faster and more reliable)
                self.nova.page.wait_for_load_state("domcontentloaded", timeout=10000)
                logger.info("Page DOM loaded successfully")
                
                # Then give a short time for critical resources
                try:
                    self.nova.page.wait_for_load_state("load", timeout=5000)
                    logger.info("Page fully loaded")
                except Exception:
                    logger.info("Page load event timeout, but DOM is ready - proceeding")
                    
            except Exception as dom_e:
                logger.warning(f"DOM load failed after 10s, checking browser functionality...")
                try:
                    current_url = self.nova.page.url
                    title = self.nova.page.title()
                    logger.info(f"Browser functional: {current_url} - {title}")
                except Exception:
                    raise Exception(f"Browser initialization failed: {dom_e}")
                    
            logger.info("Browser initialization completed")
            
            screenshot_data = self.take_screenshot()
            logger.info("Browser successfully initialized")
            return True, screenshot_data, None
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error initializing browser: {error_msg}")
            return False, None, error_msg

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
            # Use lower quality for better performance
            adjusted_quality = min(quality, 65)  # Cap quality at 65 for better performance
            
            # Use Playwright's built-in clip functionality if available for better performance
            viewport = self.nova.page.viewport_size
            if viewport and max_width < viewport.get('width', 1600):
                # Calculate clip dimensions to reduce image size before processing
                clip_width = min(viewport.get('width', 1600), 1200)  # Reasonable max width
                clip_height = min(viewport.get('height', 900), 1500)  # Reasonable max height
                
                screenshot_bytes = self.nova.page.screenshot(
                    type='jpeg', 
                    quality=adjusted_quality,
                    clip={'x': 0, 'y': 0, 'width': clip_width, 'height': clip_height}
                )
            else:
                # Take full screenshot
                screenshot_bytes = self.nova.page.screenshot(type='jpeg', quality=adjusted_quality)
            
            # Process with PIL only if necessary
            from PIL import Image
            import io
            
            # Use a more efficient approach with BytesIO
            with io.BytesIO(screenshot_bytes) as input_buffer:
                image = Image.open(input_buffer)
                
                # Only resize if needed (significant size reduction)
                if image.width > max_width:
                    ratio = max_width / image.width
                    new_height = int(image.height * ratio)
                    # Use BICUBIC for better performance than LANCZOS
                    image = image.resize((max_width, new_height), Image.BICUBIC)
                    
                    with io.BytesIO() as output_buffer:
                        # Use optimized settings for JPEG
                        image.save(
                            output_buffer, 
                            format='JPEG', 
                            quality=adjusted_quality,
                            optimize=True,
                            progressive=True
                        )
                        screenshot_bytes = output_buffer.getvalue()
            
            # Calculate size and encode
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
        """Close browser and clean up all resources"""
        if not hasattr(self, 'nova') or self.nova is None:
            return True
        
        try:
            logger.info("Closing browser instance")
            
            # Use NovaAct's stop() method to properly close browser
            if hasattr(self.nova, 'stop'):
                try:
                    self.nova.stop()
                    logger.info("Browser stopped via nova.stop()")
                except Exception as e:
                    logger.warning(f"Error calling nova.stop(): {e}")
            
            # Clear the nova instance reference
            self.nova = None
            
            # Force garbage collection
            import gc
            gc.collect()
            
            logger.info("Browser resources cleaned up successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error closing browser: {e}")
            return False