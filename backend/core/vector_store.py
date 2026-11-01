import os
import re
from sqlalchemy import create_engine
from core.config import settings

embeddings = None
vector_store = None

DATABASE_URL = getattr(settings, "DATABASE_URL", "") or ""

if DATABASE_URL and (DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres")):
    try:
        from langchain_postgres.vectorstores import PGVector
        
        # 1. Primary Embedding Model: Gemini Embedding (live & verified on API)
        gemini_key = getattr(settings, "GEMINI_API_KEY", None)
        if gemini_key:
            try:
                from langchain_google_genai import GoogleGenerativeAIEmbeddings
                embeddings = GoogleGenerativeAIEmbeddings(
                    model="models/gemini-embedding-001",
                    google_api_key=gemini_key
                )
                # Verify that model responds
                embeddings.embed_query("ping")
                print("[INFO] Initialized and verified Google Generative AI Embeddings (gemini-embedding-001) for vector store.")
            except Exception as gemini_err:
                print(f"[WARNING] Gemini embedding check failed: {gemini_err}.")
                embeddings = None

        # 2. Fallback to FakeEmbeddings if no live embedding provider
        if not embeddings:
            from langchain_community.embeddings import FakeEmbeddings
            embeddings = FakeEmbeddings(size=384)
            print("[INFO] Initialized FakeEmbeddings for vector store fallback.")

        from core.dns_fallback import resolve_db_hostaddr
        resolved_db_url = resolve_db_hostaddr(DATABASE_URL)
        engine = create_engine(resolved_db_url, pool_pre_ping=True, pool_recycle=300)
        vector_store = PGVector(
            embeddings=embeddings,
            collection_name="chat_history_v2",
            connection=engine,
            use_jsonb=True
        )
    except Exception as e:
        print(f"[WARNING] Could not initialize Postgres vector store: {e}. Semantic context disabled.")
        vector_store = None
else:
    print("[WARNING] DATABASE_URL not set or not Postgres. Semantic vector memory disabled.")


def _rebuild_vector_store():
    global vector_store, embeddings
    if not DATABASE_URL or not (DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres")):
        return None
    try:
        from core.dns_fallback import resolve_db_hostaddr
        resolved_db_url = resolve_db_hostaddr(DATABASE_URL)
        eng = create_engine(resolved_db_url, pool_pre_ping=True, pool_recycle=300)
        from langchain_postgres.vectorstores import PGVector
        vector_store = PGVector(
            embeddings=embeddings,
            collection_name="chat_history_v2",
            connection=eng,
            use_jsonb=True
        )
        return vector_store
    except Exception as ex:
        print(f"[WARNING] Rebuilding vector store connection failed: {ex}")
        return None


def save_interaction_to_vector_db(user_id: str, query: str, response: str, doc_type: str = "chat"):
    """Saves a user query and the AI's response into the vector database if available."""
    if vector_store is None or not user_id:
        return
    clean_resp = str(response)[:1200]
    content = f"[{doc_type.upper()}] User asked: {query[:300]}\nAI replied: {clean_resp}"
    metadata = {"user_id": str(user_id), "doc_type": doc_type}
    try:
        vector_store.add_texts(texts=[content], metadatas=[metadata])
    except Exception as e:
        if "could not translate host name" in str(e) or "Name or service not known" in str(e):
            print("[RECOVERY] DNS error detected in vector store. Refreshing hostaddr and retrying...")
            vs = _rebuild_vector_store()
            if vs:
                try:
                    vs.add_texts(texts=[content], metadatas=[metadata])
                    print("[INFO] Successfully saved interaction to vector DB on retry.")
                    return
                except Exception as e2:
                    print(f"[WARNING] Failed to save interaction after refresh: {e2}")
                    return
        print(f"[WARNING] Failed to save interaction to vector DB: {e}")


def _chunk_markdown_text(text: str, max_chunk_size: int = 1000, overlap: int = 150) -> list[str]:
    """Splits markdown text cleanly along headers or paragraphs into semantic chunks."""
    if not text or not text.strip():
        return []

    sections = re.split(r'(?=\n##+ )', text.strip())
    chunks = []

    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        if len(sec) <= max_chunk_size:
            chunks.append(sec)
        else:
            paragraphs = sec.split("\n\n")
            curr_chunk = ""
            for p in paragraphs:
                p = p.strip()
                if not p:
                    continue
                if len(curr_chunk) + len(p) + 2 <= max_chunk_size:
                    curr_chunk = f"{curr_chunk}\n\n{p}".strip()
                else:
                    if curr_chunk:
                        chunks.append(curr_chunk)
                    if len(p) > max_chunk_size:
                        for i in range(0, len(p), max_chunk_size - overlap):
                            sub = p[i:i + max_chunk_size].strip()
                            if sub:
                                chunks.append(sub)
                        curr_chunk = ""
                    else:
                        curr_chunk = p
            if curr_chunk:
                chunks.append(curr_chunk)
    return chunks


def save_workflow_to_vector_db(user_id: str, query: str, final_report: dict):
    """
    Saves generated LLM factory plans into the vector database.
    Chunks the plan by section (planning, manufacturing, schemes, research, etc.)
    and stores each section with its vector so fine-grained semantic search
    (e.g., OPEX, CAPEX, machinery, BOM, subsidies) can retrieve the exact relevant sections.
    """
    if vector_store is None or not user_id or not final_report:
        return

    clean_query = query.strip()
    texts = []
    metadatas = []

    # 1. Store Executive Overview chunk
    overview_parts = []
    if isinstance(final_report, dict):
        for key, val in final_report.items():
            if isinstance(val, dict) and "report" in val:
                first_part = str(val["report"])[:350].strip()
                overview_parts.append(f"[{key.upper()} OVERVIEW]\n{first_part}")
            elif key == "judge" and isinstance(val, dict):
                overview_parts.append(f"[JUDGE VERIFICATION]\nStatus: {val.get('status')}\nSummary: {val.get('summary')}")

    if overview_parts:
        overview_content = (
            f"[FACTORY PLAN: {clean_query}]\n"
            f"[SECTION: OVERVIEW]\n"
            + "\n\n".join(overview_parts)
        )
        texts.append(overview_content)
        metadatas.append({
            "user_id": str(user_id),
            "doc_type": "workflow",
            "plan_query": clean_query[:200],
            "section": "overview",
        })

    # 2. Store detailed section chunks for each specialist agent report
    if isinstance(final_report, dict):
        for key, val in final_report.items():
            report_text = ""
            if isinstance(val, dict) and "report" in val:
                report_text = str(val.get("report", ""))
            elif isinstance(val, str):
                report_text = val

            if not report_text.strip() or key in ("query", "judge"):
                continue

            chunks = _chunk_markdown_text(report_text, max_chunk_size=1000, overlap=150)
            for idx, ch in enumerate(chunks):
                chunk_content = (
                    f"[FACTORY PLAN: {clean_query}]\n"
                    f"[SECTION: {key.upper()} (Part {idx + 1})]\n"
                    f"{ch}"
                )
                texts.append(chunk_content)
                metadatas.append({
                    "user_id": str(user_id),
                    "doc_type": "workflow",
                    "plan_query": clean_query[:200],
                    "section": key,
                })

    if not texts:
        return

    try:
        vector_store.add_texts(texts=texts, metadatas=metadatas)
        print(f"[INFO] Successfully saved {len(texts)} plan chunk vectors for user_id='{user_id}' to vector DB.")
    except Exception as e:
        if "could not translate host name" in str(e) or "Name or service not known" in str(e):
            print("[RECOVERY] DNS error detected in vector store. Refreshing hostaddr and retrying...")
            vs = _rebuild_vector_store()
            if vs:
                try:
                    vs.add_texts(texts=texts, metadatas=metadatas)
                    print(f"[INFO] Successfully saved {len(texts)} plan chunk vectors for user_id='{user_id}' on retry.")
                    return
                except Exception as e2:
                    print(f"[WARNING] Failed to save plan chunks after refresh: {e2}")
                    return
        print(f"[WARNING] Failed to save workflow chunks to vector DB: {e}")


def get_user_history_and_workflows(user_id: str, current_query: str, k: int = 5) -> str:
    """
    Retrieves previous chats and generated workflows strictly for the specified user_id.
    Uses the exact technical query directly without overriding it.
    """
    if vector_store is None or not user_id:
        return ""
    try:
        filter_dict = {"user_id": {"$eq": str(user_id)}}

        # Clean search query directly from user's input - DO NOT overwrite with generic text!
        search_query = current_query.strip()
        if not search_query:
            return ""

        results = vector_store.similarity_search(
            query=search_query,
            k=k,
            filter=filter_dict
        )

        # Fallback ONLY for pure generic conversational meta-queries if nothing returned
        if not results:
            lower_q = current_query.lower()
            if any(w in lower_q for w in ["previous question", "prior question", "last question", "what did i ask", "chat history"]):
                results = vector_store.similarity_search(
                    query="user asked",
                    k=k,
                    filter=filter_dict
                )

        if not results:
            return ""

        context_str = f"--- RELEVANT CONVERSATION & FACTORY PLAN MEMORY FOR USER ({user_id}) ---\n"
        for doc in results:
            context_str += doc.page_content + "\n" + "=" * 40 + "\n"
        return context_str
    except Exception as e:
        if "could not translate host name" in str(e) or "Name or service not known" in str(e):
            print("[RECOVERY] DNS error detected in vector store. Refreshing hostaddr and retrying...")
            vs = _rebuild_vector_store()
            if vs:
                try:
                    results = vs.similarity_search(
                        query=current_query.strip(),
                        k=k,
                        filter={"user_id": {"$eq": str(user_id)}}
                    )
                    if results:
                        context_str = f"--- RELEVANT CONVERSATION & FACTORY PLAN MEMORY FOR USER ({user_id}) ---\n"
                        for doc in results:
                            context_str += doc.page_content + "\n" + "=" * 40 + "\n"
                        return context_str
                except Exception as e2:
                    print(f"[WARNING] Retry retrieval failed: {e2}")
        print(f"[WARNING] Failed to retrieve user history and workflows from vector DB: {e}")
        return ""


def get_semantic_context(user_id: str, current_query: str, k: int = 3) -> str:
    """Retrieves top k semantically similar past entries if available."""
    return get_user_history_and_workflows(user_id=user_id, current_query=current_query, k=k)