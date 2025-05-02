# Agentic App Generator

This application uses agents to generate other agentic applications based on user requirements. It combines Agno for agent framework, Temporal for workflow orchestration, Streamlit for UI, and Google's Gemini API for intelligence.

## Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
Create a `.env` file with:
```
GEMINI_API_KEY=your_gemini_api_key
```

4. Run the application:
```bash
streamlit run app.py
```

## Usage

1. Open the application in your browser
2. Enter your requirements for an agentic application in the text area
3. Click "Generate App" to create your custom agent-based application
4. The system will generate the necessary code and provide deployment instructions

## Features

- Natural language to agent specification conversion
- Automated code generation for agents
- Temporal workflow orchestration
- Streamlit-based UI generation
- Built-in templates for common agent patterns 