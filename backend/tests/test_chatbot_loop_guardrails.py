import asyncio
import sys
import os
import json

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.chatbot import run_chatbot_stream


async def test_chatbot_loop_guardrails():
    query = "Find suppliers in Pune for milk processing plant and estimate CAPEX budget"
    print(f"Testing Chatbot Tool Loop Guardrails with query: '{query}'...")
    
    events = []
    response_text = ""
    
    async for chunk in run_chatbot_stream(query, thread_id="test_loop_user"):
        if chunk.startswith("data: "):
            try:
                data = json.loads(chunk.replace("data: ", "").strip())
                events.append(data)
                if data.get("type") == "message_chunk":
                    response_text += data.get("content", "")
            except Exception:
                pass
                
    tool_starts = [e.get("tool_name") for e in events if e.get("type") == "tool_start"]
    print(f"\nTool Calls Executed in Order: {tool_starts}")
    
    # Verify no tool was executed more than ONCE
    from collections import Counter
    tool_counts = Counter(tool_starts)
    print(f"Tool Execution Frequencies: {dict(tool_counts)}")
    
    for tool_name, count in tool_counts.items():
        assert count <= 1, f"LOOP GUARDRAIL FAILED: Tool '{tool_name}' was called {count} times (max allowed: 1)"
        
    assert len(tool_starts) <= 4, f"LOOP GUARDRAIL FAILED: Total tool calls ({len(tool_starts)}) exceeded MAX_TOTAL_TOOL_CALLS (4)"
    assert len(response_text) > 0, "Chatbot failed to generate a final response"
    
    print("\n✅ CHATBOT LOOP GUARDRAILS TEST PASSED PERFECTLY!")


if __name__ == "__main__":
    asyncio.run(test_chatbot_loop_guardrails())
