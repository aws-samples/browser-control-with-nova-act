import asyncio
import sys
import os
import argparse
from pathlib import Path

current_file = Path(__file__).absolute()
actual_project_root = current_file.parent.parent.parent.parent  
app_dir = actual_project_root / "py-backend"
act_agent_dir = app_dir / "app" / "act_agent"

sys.path.insert(0, str(actual_project_root))
sys.path.insert(0, str(app_dir))
sys.path.insert(0, str(act_agent_dir))
sys.path.insert(0, str(act_agent_dir.parent))  

from app.act_agent.client.agent import ActAgent

async def main():
    parser = argparse.ArgumentParser(description="Run Act Agent with Nova Act Server")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--url", default="https://www.google.com", help="Starting URL")
    parser.add_argument("--max-steps", type=int, default=30, help="Max steps for actions")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout for actions")
    args = parser.parse_args()
    server_path = str(act_agent_dir / "server" / "nova-act-server" / "nova_act_server.py")
    
    try:
        agent = ActAgent()  
        await agent.connect_to_server(server_path)
        await agent.chat_loop()
    finally:
        if 'agent' in locals():
            await agent.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
