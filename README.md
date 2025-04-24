# Nova Act Browser Automation Chatbot

## Application Overview

Nova Act Browser Automation Chatbot provides an interactive interface for controlling web browsers using natural language commands. It leverages the Nova Act SDK to transform user requests into direct browser actions and integrates with Amazon Bedrock's LLMs to provide intelligent analysis of browser activities.

The application supports two operational modes:

1. **Direct Mode**: Passes user's natural language commands directly to the Nova Act SDK
2. **Agent Mode**: Utilizes multiple AI agents to handle complex browser tasks

## System Requirements (Tested on)

- **Operating System**: Tested on macOS (Apple Silicon)
- **Python Version**: 3.12
- **Dependencies**: See `requirements.txt` for full list

> **Note**: This application has been primarily tested on macOS with Python 3.12. While it may work on other operating systems, some adjustments might be necessary.

## Demo 1 - Shopping (Live)

![Nova Act Shopping Demo Screen](images/nova-act-shopping.gif)

## Demo 2 - Travel Planning (Playback)

![Nova Act Travel Demo Screen](images/nova-act-travel.gif)

## Usage Instructions

### 1. Set Up Nova Act API Key

An API key is required to use Nova Act:

1. Navigate to [https://nova.amazon.com/act](https://nova.amazon.com/act) and generate an API key.
2. Save it as an environment variable by executing in the terminal:

```bash
export NOVA_ACT_API_KEY="your_api_key"
```

### 2. Set Up Virtual Environment

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

### 3. Using Authenticated Browser Sessions

For websites requiring login, configure a persistent browser profile:

```python
# In core/config.py
{
   user_data_dir = "/path/to/chrome/profile"
}
```

> **Security Note**: Be cautious with authenticated sessions to avoid exposing sensitive information

### 4. Mode Selection

When implementing browser automation with Nova Act, choosing the right orchestration mode is crucial for success. Our implementation provides two distinct approaches:

**Direct Mode - Simple and Straightforward** 

Perfect for well-defined workflows with clear steps. Leverages Nova Act's native ability to interpret specific browser instructions.

To launch:
```bash
chainlit run -w nova_act_direct.py
```
Configure operation parameters in `core/config.py`:
- Control headless mode, step limits, timeouts, and user profiles

Try commands like:
- "Go to amazon.com and search for white shirt"
- "Scroll down the page"
- "Click on the third result"

**Agent Mode - Intelligent and Complex**

Handles sophisticated, open-ended tasks through a three-layer AI architecture. Combines Bedrock Agent's reasoning with LangGraph's orchestration to break down complex requests into manageable actions.

To launch:
```bash
chainlit run -w nova_act_agent.py
```

Three-tier Architecture:

![Agent Architecture](images/agent_architecture.svg)

- High Level (LangGraph): Manages conversations, decomposes tasks, and plans high-level strategies
- Mid Level (Bedrock Agent): Breaks down complex tasks and adjusts actions dynamically
- Low Level (Nova Act): Executes specific browser interactions and reports results

Advanced configuration options in core/config.py:
- Browser settings (parallel execution, video recording, screenshots)
- Execution parameters (iteration limits, result collection)
- AI model settings for each processing stage


## License

This library is licensed under the MIT-0 License. See the LICENSE file.
