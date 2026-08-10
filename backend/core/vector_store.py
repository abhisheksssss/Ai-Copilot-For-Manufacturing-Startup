import os
from sqlalchemy import create_engine
from core.config import settings

embeddings = None
vector_store = None

DATABASE_URL = getattr(settings, "DATABASE_URL", "") or ""

if DATABASE_URL and (DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres")):
    try:
        from langchain_postgres.vectorstores import PGVector
        key = getattr(settings, "NVIDIA_API_KEY_2", None) or getattr(settings, "NVIDIA_API_KEY", None)
        if key:
            try:
                from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings
                embeddings = NVIDIAEmbeddings(
                    model="nvidia/nv-embedqa-e5-v5",
                    nvidia_api_key=key
                )
                print("[INFO] Initialized NVIDIA Embeddings (nvidia/nv-embedqa-e5-v5) for vector store.")
            except Exception as nvidia_err:
                print(f"[WARNING] Failed to load NVIDIAEmbeddings: {nvidia_err}.")
                embeddings = None

        if not embeddings and getattr(settings, "GEMINI_API_KEY", None):
            try:
                from langchain_google_genai import GoogleGenerativeAIEmbeddings
                embeddings = GoogleGenerativeAIEmbeddings(
                    model="models/text-embedding-004",
                    google_api_key=settings.GEMINI_API_KEY
                )
                print("[INFO] Initialized Google Generative AI Embeddings for vector store.")
            except Exception as gemini_err:
                print(f"[WARNING] Failed to load GoogleGenerativeAIEmbeddings: {gemini_err}.")
                embeddings = None

        if not embeddings:
            from langchain_community.embeddings import FakeEmbeddings
            embeddings = FakeEmbeddings(size=384)
            print("[INFO] Initialized FakeEmbeddings for vector store fallback.")

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


def save_interaction_to_vector_db(user_id: str, query: str, response: str, doc_type: str = "chat"):
    """Saves a user query and the AI's response into the vector database if available."""
    if vector_store is None or not user_id:
        return
    try:
        clean_resp = str(response)[:1200]
        content = f"[{doc_type.upper()}] User asked: {query[:300]}\nAI replied: {clean_resp}"
        metadata = {"user_id": str(user_id), "doc_type": doc_type}
        vector_store.add_texts(texts=[content], metadatas=[metadata])
    except Exception as e:
        print(f"[WARNING] Failed to save interaction to vector DB: {e}")


def save_workflow_to_vector_db(user_id: str, query: str, final_report: dict):
    """Saves generated LLM workflow reports under the user_id in the vector database."""
    if vector_store is None or not user_id or not final_report:
        return
    try:
        report_parts = []
        if isinstance(final_report, dict):
            for key, val in final_report.items():
                if isinstance(val, dict) and "report" in val:
                    report_parts.append(f"=== {key.upper()} WORKFLOW REPORT ===\n{val['report'][:400]}")
                elif key == "judge" and isinstance(val, dict):
                    report_parts.append(f"=== JUDGE VERIFICATION ===\nStatus: {val.get('status')}\nSummary: {val.get('summary')}")
        
        report_text = "\n\n".join(report_parts) if report_parts else str(final_report)[:1000]
        content = f"[WORKFLOW GENERATED for User {user_id}]\nQuery: {query[:300]}\n\nGenerated Workflow Details:\n{report_text[:1200]}"
        metadata = {"user_id": str(user_id), "doc_type": "workflow"}
        vector_store.add_texts(texts=[content], metadatas=[metadata])
        print(f"[INFO] Successfully saved generated workflow for user_id='{user_id}' to vector DB.")
    except Exception as e:
        print(f"[WARNING] Failed to save workflow to vector DB: {e}")


def get_user_history_and_workflows(user_id: str, current_query: str, k: int = 5) -> str:
    """
    Retrieves previous chats and generated workflows strictly for the specified user_id.
    This context is passed exclusively to the Chatbot.
    """
    if vector_store is None or not user_id:
        return ""
    try:
        filter_dict = {"user_id": {"$eq": str(user_id)}}
        
        meta_query = current_query.lower()
        is_meta = any(w in meta_query for w in ["previous", "prior", "last", "history", "earlier", "before", "asked", "question", "workflow", "plan"])
        search_query = "manufacturing factory business plan user query" if is_meta else current_query

        results = vector_store.similarity_search(
            query=search_query,
            k=k,
            filter=filter_dict
        )
        
        if not results and is_meta:
            results = vector_store.similarity_search(
                query="user asked",
                k=k,
                filter=filter_dict
            )

        if not results:
            return ""
        
        context_str = f"--- PREVIOUS CHATS & GENERATED WORKFLOWS FOR USER ({user_id}) ---\n"
        for doc in results:
            context_str += doc.page_content + "\n" + "=" * 40 + "\n"
        return context_str
    except Exception as e:
        print(f"[WARNING] Failed to retrieve user history and workflows from vector DB: {e}")
        return ""


def get_semantic_context(user_id: str, current_query: str, k: int = 3) -> str:
    """Retrieves top k semantically similar past entries if available."""
    return get_user_history_and_workflows(user_id=user_id, current_query=current_query, k=k)