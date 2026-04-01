import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from app.models.db_models import HRDocument
from app.core.config import settings

# Usually, embeddings class like langchain_openai would be used:
try:
    from langchain_openai import OpenAIEmbeddings
    has_langchain = True
except ImportError:
    has_langchain = False

logger = logging.getLogger(__name__)

# Initialize engine globally for the service
engine = create_engine(settings.DATABASE_URL)

class RAGEngine:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        if has_langchain:
            self.embeddings = OpenAIEmbeddings(openai_api_key=settings.OPENAI_API_KEY)
        else:
            self.embeddings = None
            self.logger.warning("langchain_openai not installed. Cannot perform real embedding generation.")

    def retrieve_policy(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Perform vector search using pgvector's cosine distance (`<=>` or L2 `<->`).
        """
        self.logger.info(f"Retrieving policies for: {query}")
        
        if not self.embeddings: # Fallback to mock if dependencies missing in this env
            return [{"title": "Fallback", "content": "Requires langchain_openai.", "relevance_score": 0.0}]

        query_embedding = self.embeddings.embed_query(query)

        with Session(engine) as session:
            # Query the database using pgvector's cosine distance `<=>` operator to find closest vectors
            results = session.query(HRDocument).order_by(
                HRDocument.embedding.cosine_distance(query_embedding)
            ).limit(top_k).all()

            docs = []
            for r in results:
                docs.append({
                    "title": r.title,
                    "content": r.content,
                    # We could also compute the exact distance here or return it if requested in query
                })
            return docs

    def format_retrieved_context(self, docs: List[Dict[str, Any]]) -> str:
        """Format the retrieved documents to inject into LLM prompt."""
        if not docs:
            return "No relevant company policy documents found."
        context = ""
        for i, doc in enumerate(docs):
            context += f"Document {i+1}: {doc['title']}\nContent: {doc['content']}\n\n"
        return context

rag_engine = RAGEngine()
