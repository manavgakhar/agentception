import os
import subprocess
import tempfile
from typing import Dict, Any, Optional, List
from .base import BaseTool
from agno.tools.e2b import E2BTools
import google.generativeai as genai
# import sys
# import os
# sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from .gemini_tools import GeminiTools
import re

class CodeExecutionTools(BaseTool):
    """Tool for executing and testing code in a sandbox environment."""
    
    def __init__(self, execution_env: str = "Local"):
        super().__init__()
        self.execution_env = execution_env
        self.description = "Tool for executing and testing code"
        # self.e2b_tools = E2BTools()
        # self.gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel('gemini-2.5-pro-preview-03-25')
        self.gemini_tools = GeminiTools()
        
    async def analyze_dependencies(self, code: str) -> List[str]:
        """Use LLM to analyze required dependencies from code."""
        prompt = f"""
        Analyze the following Python code and list all external packages that need to be installed.
        Only include direct dependencies that need to be pip installed, not built-in Python modules.
        Format the response as a Python list of strings, each string being a pip package name.
        Include version numbers only if they are critical for compatibility.
        
        Code to analyze:
        ```python
        {code}
        ```
        """
        
        response = self.model.generate_content(prompt)
        
        try:
            # Extract the list from the response
            deps_text = response.text
            # Find anything that looks like a Python list in the response
            match = re.search(r'\[.*?\]', deps_text, re.DOTALL)
            if match:
                # Safely evaluate the list string
                deps_list = eval(match.group())
                if isinstance(deps_list, list):
                    return deps_list
            return []
        except Exception as e:
            print(f"Error parsing dependencies: {str(e)}")
            return []

    async def create_requirements_file(self, dependencies: List[str]) -> str:
        """Create a temporary requirements.txt file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("\n".join(dependencies))
            return f.name

    async def setup_venv(self, requirements_file: str) -> Dict[str, Any]:
        """Set up a virtual environment and install dependencies."""
        venv_dir = "temp_venv"
        try:
            # Create venv
            subprocess.run(["python", "-m", "venv", venv_dir], check=True)
            
            # Install dependencies
            pip_path = os.path.join(venv_dir, "bin", "pip") if os.name != "nt" else os.path.join(venv_dir, "Scripts", "pip")
            python_path = os.path.join(venv_dir, "bin", "python") if os.name != "nt" else os.path.join(venv_dir, "Scripts", "python")
            
            process = subprocess.run(
                [pip_path, "install", "-r", requirements_file],
                capture_output=True,
                text=True
            )
            
            if process.returncode != 0:
                return {
                    "success": False,
                    "error": process.stderr,
                    "venv_dir": None,
                    "python_path": None
                }
            
            return {
                "success": True,
                "venv_dir": venv_dir,
                "python_path": python_path,
                "error": None
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "venv_dir": None,
                "python_path": None
            }

    async def execute_code(self, code: str, language: str = "python") -> Dict[str, Any]:
        """Execute code in the specified environment with dependency management."""
        if self.execution_env == "Local":
            return await self._local_execute_with_deps(code, language)
        else:
            return await self._e2b_execute(code, language)
    
    async def _local_execute_with_deps(self, code: str, language: str = "python") -> Dict[str, Any]:
        """Execute code locally with dependency management."""
        temp_files = []
        venv_dir = None
        
        try:
            # Analyze dependencies
            dependencies = await self.analyze_dependencies(code)
            
            # Create requirements file
            requirements_file = await self.create_requirements_file(dependencies)
            temp_files.append(requirements_file)
            
            # Setup virtual environment
            venv_setup = await self.setup_venv(requirements_file)
            if not venv_setup["success"]:
                return {
                    "success": False,
                    "error": f"Failed to set up virtual environment: {venv_setup['error']}"
                }
            
            venv_dir = venv_setup["venv_dir"]
            python_path = venv_setup["python_path"]
            
            # Write code to temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                code_file = f.name
                temp_files.append(code_file)
            
            # Execute code with the virtual environment's Python
            result = subprocess.run(
                [python_path, code_file],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                # If execution failed, try to regenerate code with error context
                error_context = f"""
                Code execution failed with error:
                {result.stderr}
                
                Original code:
                {code}
                
                Please fix the code and ensure it works with the following dependencies:
                {dependencies}
                """
                
                # model = self.model.generate_content(error_context)
                response = self.model.generate_content(error_context)
                fixed_code = self.gemini_tools.return_code(response.text)
                
                # Try executing the fixed code
                with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                    f.write(fixed_code)
                    fixed_code_file = f.name
                    temp_files.append(fixed_code_file)
                
                result = subprocess.run(
                    [python_path, fixed_code_file],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
            
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None,
                "fixed_code": fixed_code if 'fixed_code' in locals() else None
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
            
        finally:
            # Cleanup
            for file in temp_files:
                try:
                    os.unlink(file)
                except:
                    pass
                    
            if venv_dir and os.path.exists(venv_dir):
                import shutil
                try:
                    shutil.rmtree(venv_dir)
                except:
                    pass

    async def run_streamlit_app(self, app_code: str) -> Dict[str, Any]:
        """Run a Streamlit app in a dedicated virtual environment."""
        temp_files = []
        venv_dir = None
        
        try:
            # Add streamlit to dependencies
            dependencies = await self.analyze_dependencies(app_code)
            if "streamlit" not in dependencies:
                dependencies.append("streamlit")
            
            # Create requirements file
            requirements_file = await self.create_requirements_file(dependencies)
            temp_files.append(requirements_file)
            
            # Setup virtual environment
            venv_setup = await self.setup_venv(requirements_file)
            if not venv_setup["success"]:
                return {
                    "success": False,
                    "error": f"Failed to set up virtual environment: {venv_setup['error']}"
                }
            
            venv_dir = venv_setup["venv_dir"]
            
            # Write app code to file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(app_code)
                app_file = f.name
                temp_files.append(app_file)
            
            # Run streamlit app
            streamlit_path = os.path.join(venv_dir, "bin", "streamlit") if os.name != "nt" else os.path.join(venv_dir, "Scripts", "streamlit")
            process = subprocess.Popen(
                [streamlit_path, "run", app_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Wait a bit to check for immediate errors
            try:
                stdout, stderr = process.communicate(timeout=5)
                if process.returncode is not None and process.returncode != 0:
                    return {
                        "success": False,
                        "error": stderr
                    }
            except subprocess.TimeoutExpired:
                # This is actually good - means the app is running
                return {
                    "success": True,
                    "process": process,
                    "app_file": app_file,
                    "venv_dir": venv_dir
                }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
            
        finally:
            # Note: We don't clean up here as the app might still be running
            # Cleanup should be done when stopping the app
            pass

    async def _e2b_execute(self, code: str, language: str = "python") -> Dict[str, Any]:
        """Execute code using E2B (existing implementation)"""
        try:
            result = await self.e2b_tools.run_code(code)
            return {
                "success": True,
                "output": result.output,
                "error": None
            }
        except Exception as e:
            return {
                "success": False,
                "output": None,
                "error": str(e)
            }
    
    async def run_tests(self, app_dir: str) -> Dict[str, Any]:
        """Run tests for a generated app."""
        results = {
            "success": False,
            "test_output": None,
            "errors": []
        }
        
        try:
            # Run pytest if tests exist
            if os.path.exists(os.path.join(app_dir, "tests")):
                process = subprocess.run(
                    ["pytest", app_dir],
                    capture_output=True,
                    text=True
                )
                results["test_output"] = process.stdout
                if process.returncode == 0:
                    results["success"] = True
                else:
                    results["errors"].append(process.stderr)
                    
        except Exception as e:
            results["errors"].append(str(e))
            
        return results
    
    async def validate_dependencies(self, requirements: str) -> Dict[str, Any]:
        """Validate and install required dependencies."""
        results = {
            "success": False,
            "installed": [],
            "errors": []
        }
        
        try:
            # Create a temporary virtual environment
            venv_dir = ".temp_venv"
            subprocess.run(["python", "-m", "venv", venv_dir], check=True)
            
            # Install requirements
            process = subprocess.run(
                [f"{venv_dir}/bin/pip", "install", "-r", requirements],
                capture_output=True,
                text=True
            )
            
            if process.returncode == 0:
                results["success"] = True
                # Parse installed packages
                for line in process.stdout.split("\n"):
                    if "Successfully installed" in line:
                        results["installed"] = line.replace("Successfully installed", "").strip().split()
            else:
                results["errors"].append(process.stderr)
                
        except Exception as e:
            results["errors"].append(str(e))
            
        finally:
            # Cleanup
            if os.path.exists(venv_dir):
                subprocess.run(["rm", "-rf", venv_dir])
                
        return results 