# Browser Automation with Amazon Nova Act

Automate web tasks using natural language with Amazon Nova Act and Bedrock. Transform routine browser interactions into simple conversational commands that free up your time for more meaningful work.

## What is Nova Act?

Nova Act is Amazon's specialized AI model designed specifically for reliable web browser automation. Unlike general-purpose language models, Nova Act excels at translating natural language instructions into precise browser actions—clicking, typing, scrolling, and navigating just like a human would.

## Key Features

### 🎯 **Natural Language Browser Control**
Control any website using simple, conversational commands:
```
"Search for wireless headphones on Amazon"
"Find the best-rated product under $100"
"Add it to my cart and proceed to checkout"
```

### 🧠 **Intelligent Agent Layer** 
Bridges the gap between human intent and browser actions:
- **Purpose-Driven Navigation**: Knows which websites to visit and what elements matter
- **Contextual Continuity**: Maintains context across complex multi-step tasks
- **Smart Task Breakdown**: Converts high-level goals into step-by-step browser actions

### 👥 **Human-in-the-Loop**
Seamlessly handles scenarios that require human judgment:
- Authentication challenges and CAPTCHAs
- Ambiguous UI elements
- Unexpected interface changes
- Intelligent handoff between automated and manual control

### 🔌 **Model Context Protocol (MCP) Integration**
<img src="assets/screenshots/mcp.png" width="600" alt="MCP">

Extensible ecosystem of specialized tools:
- Document processing for web research
- External search APIs for data enrichment
- Database integration for complex workflows
- Standardized tool interface for easy customization

## Demo

### Real-World Use Cases
This system enables automation across various domains:
- **Fashion Research**: Trend analysis and product comparison
- **Financial Analysis**: Market research and data gathering  
- **E-commerce**: Shopping, price comparison, and inventory management
- **News Aggregation**: Technology trends and industry insights
- **Travel Planning**: Flight searches, hotel bookings, and itinerary planning

### E-commerce Shopping (from Search to Cart)
- `Go to Amazon and search for 'laptop stand'. Filter by brand 'AmazonBasics', check customer ratings above 4 stars, and add the adjustable one to your cart.`

<img src="assets/screenshots/shopping.gif" width="800" alt="Retail Demo">

### Financial Product (ETF) Comparison 
- `Go to https://investor.vanguard.com/investment-products/index-fudds`
- `Filter for Stock-Sector funds only, then identify which sector ETF has the best YTD performance. Also note its expense ratio and 5-year return.`

<img src="assets/screenshots/finance.gif" width="800" alt="Finance Demo">

### Fashion Trend Analysis
- `Analyze current fashion trends on Pinterest for “summer 2025 fashion women".`

<img src="assets/screenshots/fashion.gif" width="800" alt="Fashion Demo">

## Quick Start

### Prerequisites
- **Operating System**: MacOS (recommended)
- **Python**: 3.10 or higher
- **Node.js**: 18 or higher
- **Package Manager**: npm or yarn

### Installation

```bash
# Clone the repository
git clone https://github.com/aws-samples/browser-control-with-nova-act.git
cd browser-control-with-nova-act

# Backend setup
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
cd py-backend
pip install -r requirements.txt

# Frontend setup
cd ..
npm install
```

### Configuration

**1. Set up Environment Variables**
```bash
# Copy the example environment file
cd py-backend
cp .env.example .env

# Edit .env file and add your Nova Act API Key
# NOVA_ACT_API_KEY=your_api_key_here
```

**Alternative: Use system environment variables**
```bash
export NOVA_ACT_API_KEY="your_api_key_here"
```

**2. Configure Browser Settings (Optional)**
All browser settings can be configured in the `.env` file or by editing `py-backend/app/libs/config/config.py`:
```python
# Core browser settings
BROWSER_HEADLESS = True  # Set to False for debugging
BROWSER_START_URL = "https://www.google.com"
BROWSER_MAX_STEPS = 2  # Keep small for reliability

# Browser profile (for persistent sessions)
BROWSER_USER_DATA_DIR = '/path/to/chrome/profile'
```

**3. AI Model Configuration**
```python
# Multimodal models required for screenshot interpretation
DEFAULT_MODEL_ID = "us.amazon.nova-premier-v1:0"
# Tested models: Nova Premier, Claude 3.7 Sonnet, Claude 3.5 Sonnet
```

### Running the Application

```bash
npm run dev
```

Visit **http://localhost:3000** to start automating!

## Usage Examples

### Basic Commands
```
# Simple navigation
"Go to amazon.com"
"Search for wireless headphones"

# Interactive actions  
"Click the search bar and type 'gaming laptop'"
"Scroll down to see more products"
"Select the third result"

# Complex research tasks
"Find gaming laptops under $1000 and compare their specs"
"Research the latest AI news and summarize key trends"
"Book a flight from Seattle to New York for next Friday"
```

## Architecture Overview

<img src="assets/architecture.svg" width="900" alt="Architecture">

The system uses a three-tier architecture:
- **Supervisor Layer**: Breaks down complex tasks and coordinates workflow
- **Agent Layer**: Executes browser missions and interprets results  
- **Nova Act Layer**: Performs direct browser interactions

## Learn More

A detailed blog post covering technical implementation, architectural decisions, and advanced usage patterns will be published soon. It will include:
- Deep dive into the agent architecture
- Advanced prompting strategies  
- Performance optimization techniques
- Troubleshooting common issues
- Real-world deployment scenarios

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Ready to automate your web workflows?** Start with `npm run dev` and experience the future of browser automation! 🚀