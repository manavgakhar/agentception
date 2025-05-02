from typing import Dict, Any, List, Optional
import os
import subprocess
from datetime import datetime
from agno.knowledge.document import DocumentKnowledgeBase
from agno.vectordb.pgvector import PgVector
from agno.memory.v2.memory import Memory
from agno.models.google import Gemini
from agno.memory.v2.db.sqlite import SqliteMemoryDb
from agno.embedder import Embedder
from google import genai
from dotenv import load_dotenv
from agno.document.base import Document
from .base import BaseTool
import hashlib
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class KnowledgeTools(BaseTool):
    """Tool for retrieving and processing external documentation."""
    
    def __init__(self, db_type: str = "PostgreSQL"):
        super().__init__()
        self.description = "Tool for handling external documentation and knowledge"
        self.db_type = db_type
        
        # Initialize Gemini client
        self.gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        
        # Vector DB setup for document storage
        self.db_url = "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"
        self.vector_db = self._initialize_vector_db()
        
        # Memory setup
        os.makedirs("data", exist_ok=True)
        self.memory_db = SqliteMemoryDb(table_name="memory", db_file="data/memory.db")
        self.memory = Memory(
            model=Gemini(id="gemini-2.0-flash-exp"),
            db=self.memory_db,
        )
        
        # Knowledge base setup
        self.knowledge_base = DocumentKnowledgeBase(
            documents=[],
            vector_db=self.vector_db,
        )

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
                    # Extract the actual list of floats from the response structure
                    # The exact structure might vary slightly based on the genai library version,
                    # but 'embedding' is the common key.
                    if 'embedding' in result:
                         # Check if result['embedding'] is already a list of floats
                         if isinstance(result['embedding'], list) and all(isinstance(x, float) for x in result['embedding']):
                             return result['embedding']
                         # If it's an object with a 'values' attribute (less common now, but for older versions)
                         elif hasattr(result['embedding'], 'values') and isinstance(result['embedding'].values, list):
                             return result['embedding'].values
                    
                    # Handle cases where embedding might fail or return empty/unexpected structure
                    logger.error(f"Failed to get embedding or extract float list for text snippet: '{text[:50]}...'")
                    # Returning a zero vector or raising an error might be options
                    return [0.0] * self.dimensions
                
                # Add this method
                def get_embedding_and_usage(self, text: str) -> tuple[List[float], Dict[str, Any]]:
                    """Gets embedding and returns placeholder usage."""
                    embedding = self.get_embedding(text)
                    # Gemini API client (genai) doesn't directly expose token counts for embeddings easily.
                    # Return a default/placeholder usage dict.
                    usage = {"total_tokens": 0} # Placeholder
                    return embedding, usage
            
            # Initialize PgVector with custom embedder
            vector_db = PgVector(
                table_name="documents",
                db_url=self.db_url,
                schema="ai", # Explicitly set schema, matching example if needed
                embedder=GeminiEmbedder(self.gemini_client)
            )
            # Optionally create the table/schema if it doesn't exist right after init
            try:
                 vector_db.create()
                 logger.info("PgVector table 'ai.documents' checked/created.")
            except Exception as e:
                 logger.error(f"Error creating PgVector table: {e}")
                 # Decide if this should prevent vector_db from being returned

            return vector_db
            
        except Exception as e:
            logger.error(f"Could not initialize PgVector: {str(e)}", exc_info=True)
            print("Falling back to in-memory storage")
            return None
    
    async def add_document(self, content: str, metadata: Dict[str, Any] = None) -> None:
        """Add a new document to the knowledge base's vector store."""
        if not self.vector_db:
            logger.warning("Vector database not available. Document will not be stored.")
            return

        cleaned_content = content.replace("\x00", "\ufffd")
        if not cleaned_content:
             logger.warning("Document content is empty after cleaning. Skipping.")
             return
        content_hash = hashlib.md5(cleaned_content.encode()).hexdigest()

        # Log the content being processed RIGHT BEFORE creating the Document object
        # Be cautious logging potentially large/sensitive content in production
        logger.info(f"Preparing document for upsert. ID: {content_hash}, Content snippet: '{cleaned_content[:100]}...'")

        doc = Document(
            id=content_hash,
            name=content_hash,  # Add name, using content_hash as default
            content=cleaned_content,
            meta_data=metadata or {
                "added_at": datetime.now().isoformat(),
                "type": "document"
            }
        )

        try:
            logger.info(f"Attempting async_upsert for document ID: {doc.id}")
            await self.vector_db.async_upsert([doc])
            logger.info(f"Document async_upsert call completed for ID: {doc.id}")
        except Exception as e:
            # Log the specific error during upsert for better diagnostics
            logger.error(f"Error during async_upsert for document {doc.id}: {e}", exc_info=True)
            # Optionally re-raise or handle the error appropriately
            # raise e
    
    async def search_knowledge(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search the knowledge base for relevant information."""
        if not self.vector_db:
            print("Warning: Vector database not available. Search will return empty results.")
            return []

        # Use the vector_db search directly for potentially more reliable results
        try:
            # Use async_search since the class methods are async
            results: List[Document] = await self.vector_db.async_search(query, limit=limit)

            # Adapt the results. PgVector search returns Document objects.
            # Similarity is not directly attached to the Document object by PgVector search.
            # It's used internally for ordering. If you need similarity scores,
            # you might need to modify PgVector or calculate it separately.
            output_results = []
            for r in results:
                output_results.append({
                    "content": r.content,
                    "metadata": r.meta_data,
                    "similarity": None # Similarity score not directly available from PgVector search result objects
                })
            return output_results
        except Exception as e:
            print(f"Error searching PgVector: {e}")
            return []
    
    async def add_memory(self, user_id: str, content: str) -> None:
        """Add a new memory for a user."""
        await self.memory.create_user_memories(
            message=content,
            user_id=user_id
        )
    
    async def get_memories(self, user_id: str) -> List[Dict[str, Any]]:
        """Retrieve memories for a user."""
        memories = await self.memory.get_user_memories(user_id=user_id)
        return [
            {
                "memory": m.memory,
                "topics": m.topics,
                "created_at": m.created_at
            }
            for m in memories
        ]
    
    async def search_memories(self, user_id: str, query: str) -> List[Dict[str, Any]]:
        """Search user memories based on a query."""
        memories = await self.memory.search_user_memories(
            user_id=user_id,
            query=query
        )
        return [
            {
                "memory": m.memory,
                "topics": m.topics,
                "similarity": m.similarity
            }
            for m in memories
        ] 