import os
from typing import Dict, Any
import google.generativeai as genai
from dotenv import load_dotenv
import json
import logging
import re

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Configure Gemini API
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class GeminiTools:
    """Tools for interacting with Google's Gemini API."""
    
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-2.5-pro-preview-03-25')
        
    async def analyze_prompt(self, prompt: str) -> Dict[str, Any]:
        """Analyze user prompt and convert to structured specification."""
        system_prompt = """You are a JSON generator. Your task is to convert the user's app requirements into a JSON specification.

        IMPORTANT: Your response must contain ONLY valid JSON - no other text, no markdown, no explanations.
        
        Required JSON structure:
        {
            "agents": [
                {
                    "name": "string",
                    "purpose": "string",
                    "tools": ["string"]
                }
            ],
            "workflow": {
                "steps": ["string"],
                "dependencies": ["string"]
            },
            "ui": {
                "components": ["string"],
                "layouts": ["string"]
            },
            "integrations": ["string"]
        }

        Remember: Output ONLY the JSON, nothing else."""
        
        try:
            response = self.model.generate_content(
                f"{system_prompt}\n\nUser prompt: {prompt}"
            )
            
            # Log the raw response for debugging
            logger.info("Raw Gemini response:")
            logger.info(response.text)
            
            # Try to extract JSON from the response
            # First, try direct parsing
            try:
                return json.loads(response.text)
            except json.JSONDecodeError as e:
                logger.warning(f"Direct JSON parsing failed: {e}")
                
                # Try to clean the response - look for JSON-like content
                cleaned_text = response.text
                
                # Remove any markdown code block markers
                if "```json" in cleaned_text:
                    cleaned_text = cleaned_text.split("```json")[-1].split("```")[0]
                elif "```" in cleaned_text:
                    cleaned_text = cleaned_text.split("```")[1]
                    
                # Remove any leading/trailing whitespace and newlines
                cleaned_text = cleaned_text.strip()
                
                logger.info("Cleaned response:")
                logger.info(cleaned_text)
                
                try:
                    return json.loads(cleaned_text)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON parsing failed even after cleaning: {e}")
                    # Return a fallback structure
                    return {
                        "error": "Failed to generate valid specification",
                        "raw_response": response.text[:200] + "...",  # First 200 chars for debugging
                        "agents": [
                            {
                                "name": "DefaultAgent",
                                "purpose": "Basic functionality",
                                "tools": ["basic_tools"]
                            }
                        ],
                        "workflow": {
                            "steps": ["initialize", "process", "complete"],
                            "dependencies": []
                        },
                        "ui": {
                            "components": ["basic_form"],
                            "layouts": ["single_column"]
                        },
                        "integrations": []
                    }
                
        except Exception as e:
            logger.error(f"Gemini API error: {str(e)}")
            return {
                "error": f"API Error: {str(e)}",
                "agents": [],
                "workflow": {"steps": [], "dependencies": []},
                "ui": {"components": [], "layouts": []},
                "integrations": []
            }
    
    async def generate_agent_implementation(self, spec: Dict[str, Any]) -> str:
        """Generate detailed agent implementation based on specification."""
        system_prompt = """
        Generate a complete Python implementation for an LLM agent with the following 
        specification. Include:
        - All necessary imports
        - Tool definitions
        - Main agent class
        - Processing logic
        """
        
        response = self.model.generate_content(
            f"{system_prompt}\n\nSpecification: {str(spec)}"
        )
        
        return self.return_code(response.text)
    
    async def generate_ui_implementation(self, spec: Dict[str, Any], agent_code: str) -> str:
        """Generate Streamlit UI implementation based on specification."""
        system_prompt = """
        Generate a complete Streamlit UI implementation in Python based on the following 
        application specification. The UI should reflect the application's purpose and components.
        
        Include:
        - Necessary imports (especially `streamlit as st`)
        - Functions to structure the UI (if needed)
        - Appropriate Streamlit widgets based on the 'ui' section of the spec (components, layouts) 
          and the overall purpose described by the agents.
        - Basic placeholders for logic integration (e.g., comments indicating where agent calls would happen).
        - Ensure the output is a single, runnable Python script for a Streamlit app.
        
        Specification Details:
        - Agents: {spec.get('agents', [])}
        - Workflow: {spec.get('workflow', {})}
        - UI Components: {spec.get('ui', {}).get('components', [])}
        - UI Layouts: {spec.get('ui', {}).get('layouts', [])}
        - Integrations: {spec.get('integrations', [])}
        
        Generate only the Python code for the Streamlit UI.
        Use the agent code for reference for building the UI.
        """
        # prompt = f"Specification: {json.dumps(spec, indent=2)}" 
        # Append the agent code to the main prompt for context
        prompt = f"Specification: {json.dumps(spec, indent=2)}\n\nReference the following agent code when generating the UI:\n```python\n{agent_code}\n```"
        
        try:
            response = self.model.generate_content(
                f"{system_prompt}\n\n{prompt}"
            )

            # Log the raw response before trying to extract code
            logger.info(f"Raw UI generation response text: {response.text}")

            # Use the existing code extraction logic
            return self.return_code(response.text)

        except Exception as e:
            # Log the specific exception that occurred
            logger.error(f"Error during UI generation: {str(e)}", exc_info=True) 
            # Fallback basic UI
            return """
import streamlit as st

st.title("Generated App")
st.write("UI generation failed. Using fallback UI.")
st.write("Specification:")
st.json(spec) # Display the spec for debugging
            """.replace("spec", f"{spec}") # Embed spec directly in fallback

    def return_code(self, response: str) -> str:
        system_prompt = """
        Given LLM output, extract the python code as-it-is from this and return so I can copy the contents into a .py file.
        Do not add any ''' or any extra jargon, just give me the code text. Extract the code between the ```python ``` block.
        """
        
        response = self.model.generate_content(
            f"{system_prompt}\n\nInput: {response}"
        )

        
        return self.extract_python_code_block(response.text)
    
    def extract_python_code_block(self, markdown: str) -> str:
        """
        Extracts the code from a markdown code block.
        Handles blocks starting with ```python or just ```
        """
        lines = markdown.splitlines()
        in_code_block = False
        code_lines = []

        for line in lines:
            # Start of code block
            if line.strip().startswith("```python"):
                in_code_block = True
                continue
            # End of code block
            elif line.strip() == "```" and in_code_block:
                in_code_block = False
                continue
            # Inside code block
            if in_code_block:
                code_lines.append(line)

        return "\n".join(code_lines)
    
    async def generate_workflow_implementation(self, spec: Dict[str, Any]) -> str:
        """Generate Temporal workflow implementation based on specification."""
        system_prompt = """
        Generate a complete Temporal workflow implementation in Python based on 
        the following specification. Include:
        - Activity definitions
        - Workflow class
        - Error handling
        - Retry policies
        """
        
        response = self.model.generate_content(
            f"{system_prompt}\n\nSpecification: {str(spec)}"
        )
        
        return response.text 