from typing import Dict, List, Any
from .base import BaseTool
from .gemini_tools import GeminiTools
import logging

logger = logging.getLogger(__name__)

class CodeAnalysisTool(BaseTool):
    """Tool for analyzing code and extracting patterns."""
    
    def __init__(self):
        super().__init__()
        self.description = "Tool for analyzing code and extracting patterns"
    
    def analyze_requirements(self, prompt: str) -> Dict[str, Any]:
        """Analyze user requirements and extract key components."""
        return {
            "agents": self._extract_agent_requirements(prompt),
            "workflows": self._extract_workflow_requirements(prompt),
            "ui_components": self._extract_ui_requirements(prompt)
        }
    
    def _extract_agent_requirements(self, prompt: str) -> List[Dict[str, Any]]:
        """Extract required agents from the prompt."""
        # This will be implemented with Gemini API
        pass
    
    def _extract_workflow_requirements(self, prompt: str) -> List[Dict[str, Any]]:
        """Extract workflow requirements from the prompt."""
        # This will be implemented with Gemini API
        pass
    
    def _extract_ui_requirements(self, prompt: str) -> List[Dict[str, Any]]:
        """Extract UI component requirements from the prompt."""
        # This will be implemented with Gemini API
        pass

class CodeGenerationTool(BaseTool):
    """Tool for generating code based on specifications."""
    
    def __init__(self):
        super().__init__()
        self.description = "Tool for generating code based on specifications"
        self.gemini_tools = GeminiTools()
    
    def generate_agent_code(self, spec: Dict[str, Any]) -> str:
        """Generate LLM agent app code from specification."""
        # Template for agent code generation
        return f"""
class {spec['name']}Agent:
    def __init__(self):
        self.tools = {spec.get('tools', [])}
        self.instructions = {spec.get('instructions', [])}
        
    async def process(self, input_data: Any) -> Any:
        # Implementation will be generated based on spec
        pass
"""
    
    def generate_workflow_code(self, spec: Dict[str, Any]) -> str:
        """Generate Temporal workflow code from specification."""
        return f"""
from temporalio import workflow
from datetime import timedelta

@workflow.defn
class {spec['name']}Workflow:
    @workflow.run
    async def run(self, input_data: Any) -> Any:
        # Workflow implementation will be generated based on spec
        pass
"""
    
    async def generate_ui_code(self, spec: Dict[str, Any], agent_code:str) -> str:
        """Generate Streamlit UI code from specification using Gemini."""
        logger.info(f"Generating UI code for spec: {spec.get('name', 'Unnamed App')}")
        try:
            # Call the new method in GeminiTools
            ui_code = await self.gemini_tools.generate_ui_implementation(spec, agent_code)
            if not ui_code or not ui_code.strip():
                 logger.warning("Gemini UI generation returned empty code. Using basic fallback.")
                 return self._generate_fallback_ui(spec)
            return ui_code
        except Exception as e:
            logger.error(f"Error calling Gemini for UI generation: {str(e)}")
            # Generate a fallback UI if the LLM call fails
            return self._generate_fallback_ui(spec)

    def _generate_fallback_ui(self, spec: Dict[str, Any]) -> str:
        """Generates a very basic fallback UI."""
        # Escape curly braces for json.dumps and the default dict {} within the f-string
        # The f-string for text_input's label is nested and correctly evaluates 'component'.
        return f'''
import streamlit as st
import json

st.title("Generated App: {spec.get('name', 'Unnamed App')}")
st.warning("Using fallback UI due to generation error.")

st.subheader("App Specification")
# Use {{}} to escape the braces meant for the st.json call itself
st.json({{json.dumps(spec)}}) 

st.subheader("Basic Controls (Placeholders)")
# Add some basic controls based on spec if possible
# Use {{}} to escape the braces for the default dictionary in .get()
if spec.get('ui', {{}}).get('components'): 
    for component in spec['ui']['components']:
        # This inner f-string is fine as it evaluates 'component' variable
        st.text_input(f"Input for {{component}}") 
    st.button("Submit")
else:
    st.write("No UI components specified.")

st.sidebar.header("Settings")
st.sidebar.write("Placeholder for settings.")
''' 