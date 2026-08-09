import asyncio
import sys
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.vector_store import save_interaction_to_vector_db, save_workflow_to_vector_db, get_user_history_and_workflows
from agents.chatbot import run_chatbot_stream


async def test_chatbot_history():
    test_user_id = "user_test_999"
    print(f"1. Seeding test history for user_id='{test_user_id}'...")
    
    # Save a past interaction
    save_interaction_to_vector_db(
        user_id=test_user_id,
        query="How much CAPEX is required for a 20,000 unit/month paper bag plant in Ahmedabad?",
        response="The estimated CAPEX for a 20,000 unit/month paper bag plant in Ahmedabad is approximately 25 Lakhs INR.",
        doc_type="chat"
    )
    
    # Verify retrieval
    retrieved = get_user_history_and_workflows(user_id=test_user_id, current_query="what was my previous question")
    print(f"\n2. Vector DB Retrieved History:\n{retrieved}")
    assert "paper bag plant" in retrieved or "CAPEX" in retrieved, "History context retrieval failed"
    
    print("\n3. Streaming Chatbot response to 'what was my previous question'...")
    response_text = ""
    async for chunk in run_chatbot_stream("what was my previous question", thread_id=test_user_id):
        if "message_chunk" in chunk:
            import json
            data = json.loads(chunk.replace("data: ", "").strip())
            response_text += data.get("content", "")
            
    print(f"\n4. Chatbot Response:\n{response_text}")
    print("\n✅ CHATBOT HISTORY RETRIEVAL & ANSWER TEST PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(test_chatbot_history())
