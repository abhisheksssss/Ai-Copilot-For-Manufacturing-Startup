import os
from sqlalchemy import create_engine
from core.config import settings

embeddings = None
vector_store = None

DATABASE_URL = getattr(settings, "DATABASE_URL", "") or ""

if DATABASE_URL and (DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres")):
    try:
        from langchain_postgres.vectorstores import PGVector
        if getattr(settings, "NVIDIA_API_KEY", None):
            try:
                from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings
                embeddings = NVIDIAEmbeddings(
                    model="NV-Embed-QA",
                    nvidia_api_key=settings.NVIDIA_API_KEY_2
                )
                print("[INFO] Initialized NVIDIA Embeddings for vector store.")
            except Exception as nvidia_err:
                print(f"[WARNING] Failed to load NVIDIAEmbeddings: {nvidia_err}. Falling back to HuggingFace.")
                from langchain_huggingface import HuggingFaceEmbeddings
                embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        else:
            from langchain_huggingface import HuggingFaceEmbeddings
            embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

        engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
        vector_store = PGVector(
            embeddings=embeddings,
            collection_name="chat_history",
            connection=engine,
            use_jsonb=True
        )
    except Exception as e:
        print(f"[WARNING] Could not initialize Postgres vector store: {e}. Semantic context disabled.")
        vector_store = None
else:
    print("[WARNING] DATABASE_URL not set or not Postgres. Semantic vector memory disabled.")


def save_interaction_to_vector_db(user_id: str, query: str, response: str):
    """Saves a user query and the AI's response into the vector database if available."""
    if vector_store is None:
        return
    try:
        content = f"User asked: {query}\nAI replied: {response}"
        metadata = {"user_id": user_id}
        vector_store.add_texts(texts=[content], metadatas=[metadata])
    except Exception as e:
        print(f"[WARNING] Failed to save interaction to vector DB: {e}")


def get_semantic_context(user_id: str, current_query: str, k: int = 3) -> str:
    """Retrieves the top k most semantically similar past conversations if available."""
    if vector_store is None:
        return ""
    try:
        filter_dict = {"user_id": {"$eq": user_id}}
        results = vector_store.similarity_search(
            query=current_query,
            k=k,
            filter=filter_dict
        )
        if not results:
            return ""
        
        context_str = "--- RELEVANT PAST CONVERSATIONS ---\n"
        for doc in results:
            context_str += doc.page_content + "\n\n"
        return context_str
    except Exception as e:
        print(f"[WARNING] Failed to retrieve semantic context from vector DB: {e}")
        return ""