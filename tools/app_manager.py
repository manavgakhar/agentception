import os
import subprocess
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from agno.vectordb.pgvector import PgVector
from google import genai
from dotenv import load_dotenv
from .base import BaseTool

# Load environment variables
load_dotenv()

class AppManager(BaseTool):
    """Tool for managing generated apps, testing, and debugging."""
    
    def __init__(self):
        super().__init__()
        self.description = "Tool for managing, testing, and debugging generated apps"
        self.apps_dir = "generated_apps"
        self.library_file = "app_library.json"
        self.db_url = "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"
        self.gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self._ensure_dirs()
        self.load_library()
    
    def _ensure_dirs(self):
        """Ensure necessary directories exist."""
        try:
            if not os.path.exists(self.apps_dir):
                os.makedirs(self.apps_dir, exist_ok=True)
            
            # Test if directory is writable using a unique name
            test_file = os.path.join(self.apps_dir, f'.write_test_{os.getpid()}')
            try:
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)
            except (IOError, OSError) as e:
                raise RuntimeError(f"Directory {self.apps_dir} is not writable: {str(e)}")
            except Exception as e:
                if os.path.exists(test_file):
                    try:
                        os.remove(test_file)
                    except:
                        pass
                raise RuntimeError(f"Unexpected error while testing directory permissions: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Failed to create/verify directories: {str(e)}")
    
    def load_library(self):
        """Load the app library catalog."""
        try:
            if os.path.exists(self.library_file):
                with open(self.library_file, 'r') as f:
                    self.library = json.load(f)
            else:
                self.library = {
                    "apps": [],
                    "last_updated": datetime.now().isoformat()
                }
                # Create the initial library file
                self.save_library()
        except Exception as e:
            raise RuntimeError(f"Failed to load/create library file: {str(e)}")
    
    def save_library(self):
        """Save the app library catalog."""
        try:
            self.library["last_updated"] = datetime.now().isoformat()
            with open(self.library_file, 'w') as f:
                json.dump(self.library, f, indent=2)
        except Exception as e:
            raise RuntimeError(f"Failed to save library: {str(e)}")
    
    async def save_app(self, name: str, description: str, files: Dict[str, str]) -> str:
        """Save a generated app to the library."""
        try:
            # Sanitize app name to be filesystem friendly
            safe_name = "".join(c for c in name if c.isalnum() or c in ('-', '_')).lower()
            app_dir = os.path.join(self.apps_dir, safe_name)
            
            # Create app directory
            os.makedirs(app_dir, exist_ok=True)
            
            # Save all app files
            saved_files = []
            for filename, content in files.items():
                file_path = os.path.join(app_dir, filename)
                try:
                    with open(file_path, 'w') as f:
                        f.write(content)
                    saved_files.append(filename)
                except Exception as e:
                    raise RuntimeError(f"Failed to save file {filename}: {str(e)}")
            
            # Add to library only if all files were saved successfully
            app_info = {
                "name": name,
                "description": description,
                "created_at": datetime.now().isoformat(),
                "path": app_dir,
                "files": saved_files
            }
            
            # Check if app already exists in library
            existing_app = next((app for app in self.library["apps"] if app["name"] == name), None)
            if existing_app:
                # Update existing entry
                existing_app.update(app_info)
            else:
                # Add new entry
                self.library["apps"].append(app_info)
            
            self.save_library()
            return app_dir
            
        except Exception as e:
            # Clean up any partially created files/directories
            if 'app_dir' in locals() and os.path.exists(app_dir):
                try:
                    import shutil
                    shutil.rmtree(app_dir)
                except:
                    pass
            raise RuntimeError(f"Failed to save app: {str(e)}")
    
    async def test_app(self, app_dir: str) -> Dict[str, Any]:
        """Test a generated app by running it and checking for errors."""
        results = {
            "success": False,
            "errors": [],
            "logs": []
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
                if process.returncode != 0:
                    results["errors"].append("Tests failed")
            
            # Try running the main app file
            process = subprocess.run(
                ["python", os.path.join(app_dir, "app.py")],
                capture_output=True,
                text=True,
                timeout=5  # 5 second timeout for initial startup
            )
            
            results["logs"].append(process.stdout)
            if process.returncode == 0:
                results["success"] = True
            else:
                results["errors"].append(process.stderr)
                
        except Exception as e:
            results["errors"].append(str(e))
        
        return results
    
    async def debug_app(self, app_dir: str, error_info: Dict[str, Any]) -> Dict[str, Any]:
        """Attempt to debug and fix common issues in the app."""
        fixes = []
        
        for error in error_info["errors"]:
            if "ModuleNotFoundError" in error:
                # Missing dependency
                module = error.split("'")[1]
                fixes.append({
                    "type": "dependency",
                    "module": module,
                    "fix": f"pip install {module}"
                })
            elif "SyntaxError" in error:
                # Syntax error - needs manual review
                fixes.append({
                    "type": "syntax",
                    "error": error,
                    "fix": "Requires manual code review"
                })
        
        return {
            "fixes": fixes,
            "automated_fixes_possible": any(fix["type"] == "dependency" for fix in fixes)
        }
    
    def get_app_library(self) -> List[Dict[str, Any]]:
        """Get the list of all saved apps."""
        return self.library["apps"]

    def _initialize_vector_db(self) -> Optional[PgVector]:
        """Initialize the vector database connection."""
        try:
            # Install psycopg with binary support if not already installed
            try:
                import psycopg
            except ImportError:
                print("Installing psycopg with binary support...")
                subprocess.run(["pip", "install", "psycopg[binary]"], check=True)
                import psycopg
            
            # Try to connect to the database
            conn = psycopg.connect(
                dbname="postgres",
                user="postgres",
                password="postgres",
                host="localhost",
                port="5432"
            )
            
            # Create the vector extension if not exists (ignore if already exists)
            with conn.cursor() as cur:
                try:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                    conn.commit()
                except psycopg.Error as e:
                    # If error is about extension already existing, that's fine
                    if "already exists" not in str(e):
                        raise e
            
            conn.close()
            
            # Create a custom embedder using Gemini
            class GeminiEmbedder(Embedder):
                def __init__(self, client):
                    self.client = client
                    self.dimensions = 768  # Gemini embedding dimensions
                
                def get_embedding(self, text: str) -> List[float]:
                    result = self.client.models.embed_content(
                        model="gemini-embedding-exp-03-07",
                        contents=text
                    )
                    return result.embeddings[0]
            
            # Initialize PgVector with custom embedder
            vector_db = PgVector(
                table_name="documents",
                db_url=self.db_url,
                embedder=GeminiEmbedder(self.gemini_client)  # Pass the custom embedder
            )
            
            return vector_db
            
        except Exception as e:
            print(f"Warning: Could not initialize PgVector: {str(e)}")
            print("Falling back to in-memory storage")
            return None 