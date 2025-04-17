# Agent Mode Documentation

## Application Overview

The Agent Mode provides browser automation capabilities through natural language commands. Developed to handle complex web tasks, the system decomposes larger operations into manageable subtasks.

### Architecture

The application follows a hierarchical architecture:

1. **High Level (LangGraph)** - Planning and task coordination
2. **Mid Level (Bedrock Agent)** - Task execution and reasoning
3. **Low Level (Nova Act)** - Direct browser control

### Task Handling Approach

The system uses a plan-execute pattern to break down tasks:

- Tasks receive sequence numbers based on dependencies
- Tasks with the same sequence number execute in parallel using independent browser instances
- Tasks with different sequence numbers execute sequentially

### Customization Options

#### Prompt Customization

Default prompts in `core/config.py` are generalized. For specialized automation needs, you can optimize these prompts:

```python
# In core/config.py
BROWSER_AGENT_INSTRUCTION = """
Your customized instructions here
"""

PLANNER_SYSTEM_PROMPT = """
Your customized planning instructions here
"""
```

### Customization Options

#### Parallelism Control

```python
# In core/config.py
DEFAULT_BROWSER_SETTINGS = {
    "parallel_mode": True,  # Enable/disable parallel execution
    "max_concurrent_browsers": 2,  # Maximum concurrent browser instances
}

```
*Note*: High concurrency may trigger throttling in Nova Act services or Bedrock Agent APIs.

#### Browser Visibility

```python
# In core/config.py
DEFAULT_BROWSER_SETTINGS = {
    "headless": True,  # Set to False for visible browser windows
}
```

#### Execution Limits

```python
# In core/config.py
DEFAULT_BROWSER_SETTINGS = {
    "timeout": 90,  # Maximum execution time in seconds
    "max_steps": 5   # Maximum steps in a single Nova Act call
}
```

The default `max_steps` is intentionally set to 5, allowing the agent to regain control and implement recovery strategies if needed. Adjust based on task requirements.

#### Model Configuration

```python
# In core/config.py
MODEL_CONFIG = {
    "decision_model": "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    "planner_model": "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    "browser_agent_model": "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    "region": "us-west-2",
    "temperature": {
        "decision": 0.2,
        "planner": 0.2,
        "browser_agent": 0.2
    }
}
```


#### Agent Execution Configuration

```python
# In core/config.py
EXECUTION_CONFIG = {
    "max_turns": 15,  # Maximum iterations for the Bedrock Agent
    "collect_results": False  # Whether to collect final results
}
```

### Advanced Usage

#### Error Recovery Strategies

The agent implements several recovery approaches when encountering issues:
- For CAPTCHA challenges: The agent can detect and report these limitations
- For navigation errors: Fallback to search engines using `Browser::go_to_url` tool
- For stuck states: Automatically attempts scrolling or alternate interaction methods

#### Custom Schema Extraction

Extract structured data using custom schemas:

```python
# Example of using a custom schema with Browser::data tool
custom_schema = {
    "type": "object",
    "properties": {
        "product_name": {"type": "string"},
        "price": {"type": "string"},
        "rating": {"type": "string"},
        "in_stock": {"type": "boolean"}
    }
}
# This can be used through the ExtractDataTool
```

