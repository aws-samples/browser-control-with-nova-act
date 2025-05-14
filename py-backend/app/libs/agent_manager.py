import logging
from typing import Dict, Any, Optional
from app.act_agent.client.browser_agent import BrowserAgent
from app.act_agent.client.agent_executor import AgentExecutor
from app.libs.browser_utils import BrowserUtils
from app.libs.config import BROWSER_HEADLESS

logger = logging.getLogger("agent_manager")

class ActAgentManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ActAgentManager, cls).__new__(cls)
            cls._instance._browser_agents = {}
            cls._instance._browser_urls = {} 
            cls._instance._global_agent = None
            cls._instance._logger = logging.getLogger("agent_manager")
        return cls._instance
    
    async def initialize_global_agent(self, server_path: str, headless: bool = False, model_id: str = None, region: str = None) -> BrowserAgent:
        server_config = {}
        if model_id:
            server_config["model_id"] = model_id
        if region:
            server_config["region"] = region
            
        browser_agent = BrowserAgent(server_config=server_config)
        await browser_agent.connect_to_server(server_path)
        await browser_agent.initialize_browser(headless=headless)
        
        self._global_agent = browser_agent
        self._browser_agents["global"] = self._global_agent
        self._logger.info("Global BrowserAgent initialized successfully")
        return browser_agent
    
    async def get_or_create_browser_agent(self, session_id: str, server_path: str, headless: bool = BROWSER_HEADLESS, model_id: str = None, region: str = None, url: str = None) -> BrowserAgent:
        # Check existing agent
        if session_id in self._browser_agents:
            self._logger.info(f"Reusing existing BrowserAgent for session {session_id}")
            browser_agent = self._browser_agents[session_id]
            
            # Check browser state and log
            if browser_agent.browser_initialized and browser_agent.session:
                try:
                    browser_state = await BrowserUtils.get_browser_state(browser_agent)
                    current_url = browser_state.get("current_url", "")
                    has_screenshot = "screenshot" in browser_state and browser_state["screenshot"] is not None
                    
                    self._logger.info(f"Retrieved browser state - URL: {current_url}, Has screenshot: {has_screenshot}")
                except Exception as e:
                    self._logger.error(f"Error checking browser state: {e}")
            
            return browser_agent
            
        # Check global agent reuse
        if self._global_agent and self._can_reuse_global_agent():
            self._logger.info(f"Using global BrowserAgent for session {session_id}")
            self._browser_agents[session_id] = self._global_agent
            
            # Navigate global agent if needed
            if url and self._global_agent.browser_initialized and self._global_agent.session:
                try:
                    await self._global_agent.session.call_tool("navigate", {"url": url})
                    self._browser_urls[session_id] = url
                except Exception as e:
                    self._logger.error(f"Error navigating global agent to URL {url}: {e}")
            
            return self._global_agent
            
        # Create new agent
        self._logger.info(f"Creating new BrowserAgent for session {session_id}")
        
        # Setup configuration
        server_config = {}
        if model_id:
            server_config["model_id"] = model_id
        if region:
            server_config["region"] = region
            
        # Initialize agent
        browser_agent = BrowserAgent(server_config=server_config)
        await browser_agent.connect_to_server(server_path)
        
        # Determine initialization URL
        init_url = url or self._browser_urls.get(session_id, "https://www.google.com")
        self._logger.info(f"Initializing browser with URL: {init_url}")
        
        await browser_agent.initialize_browser(headless=headless, url=init_url)
        
        # Register the new agent
        self._browser_agents[session_id] = browser_agent
        self._browser_urls[session_id] = init_url
        
        return browser_agent
        
    def _can_reuse_global_agent(self) -> bool:
        return True  # Logic for when global agent can be reused
        
    def get_agent_executor(self, browser_agent: BrowserAgent) -> AgentExecutor:
        return AgentExecutor(browser_agent)
        
    async def close_agent(self, session_id: str) -> bool:
        if session_id not in self._browser_agents:
            return False
            
        agent = self._browser_agents[session_id]
        
        # If using global agent, just remove reference
        if agent is self._global_agent and session_id != "global":
            del self._browser_agents[session_id]
            return True
            
        # Save current URL state
        try:
            if agent.browser_initialized and agent.session:
                try:
                    browser_state = await BrowserUtils.get_browser_state(agent)
                    current_url = browser_state.get("current_url")
                    if current_url:
                        self._browser_urls[session_id] = current_url
                        self._logger.info(f"Saved URL state for session {session_id}: {current_url}")
                except Exception as e:
                    self._logger.warning(f"Could not save URL state for session {session_id}: {e}")
        except Exception as e:
            self._logger.error(f"Error saving URL state: {e}")
            
        # Close browser and cleanup resources
        try:
            await agent.close_browser()
            del self._browser_agents[session_id]
            
            if session_id == "global":
                self._global_agent = None
                
            return True
        except Exception as e:
            self._logger.error(f"Error closing agent for session {session_id}: {str(e)}")
            return False

agent_manager = ActAgentManager()
