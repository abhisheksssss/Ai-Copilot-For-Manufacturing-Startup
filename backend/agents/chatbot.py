import json
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool

from models.llm import get_default_LLM, get_fallback_llm,get_nvidia_llm2
from .state import AgentState

# ==========================================
# PENDING SESSION STORE
# ==========================================
_pending_sessions: dict[str, dict] = {}

_DISMISSIVE_PHRASES = {
    "no", "nope", "nothing", "skip", "proceed", "continue", "just do it",
    "don't ask", "no need", "no requirement", "go ahead", "ignore", "pass",
    "doesn't matter", "don't care", "don't know", "just proceed", "no info",
}

MAX_CLARIFICATION_ATTEMPTS = 1


def _is_dismissive(answer: str) -> bool:
    lower = answer.strip().lower()
    if len(lower) < 3:
        return True
    return any(phrase in lower for phrase in _DISMISSIVE_PHRASES)


# ==========================================
# TOOLS
# ==========================================

@tool
async def ask_user_clarification(question: str) -> str:
    """
    ONLY call this tool if the user's query is completely vague with NO product,
    NO budget, AND NO location mentioned.
    Do NOT call this if the user has provided any of: product type, budget amount,
    or location — even partial info is enough to proceed.
    Ask ONE clear, specific question at a time.
    """
    return f"__CLARIFICATION_NEEDED__:{question}"


@tool
async def trigger_planning_agent(query: str) -> str:
    """Use this tool for business roadmap, CAPEX/OPEX cost estimation, budget planning, break-even analysis, timeline, team requirements, and factory planning."""
    print(f"--- CHATBOT: Passing task to Planning Agent: '{query}' ---")
    from .orchestrator import planning_node
    result = await planning_node({"user_query": query})
    return result.get("planning_result", {}).get("report", "Planning Agent completed the task.")


@tool
async def trigger_manufacturing_agent(query: str) -> str:
    """Use this tool for manufacturing process, machinery, BOM, energy requirements, and factory layout."""
    print(f"--- CHATBOT: Passing task to Manufacturing Agent: '{query}' ---")
    from .orchestrator import manufacturing_node
    result = await manufacturing_node({"user_query": query})
    return result.get("manufacturing_result", {}).get("report", "Manufacturing Agent completed the task.")


@tool
async def trigger_scheme_agent(query: str) -> str:
    """Use this tool for government schemes, subsidies, loans, and MSME benefits."""
    print(f"--- CHATBOT: Passing task to Scheme Agent: '{query}' ---")
    from .orchestrator import scheme_node
    result = await scheme_node({"user_query": query})
    return result.get("scheme_result", {}).get("report", "Scheme Agent completed the task.")


@tool
async def trigger_research_agent(query: str) -> str:
    """Use this tool for market research, competitors, industry trends, and suppliers."""
    print(f"--- CHATBOT: Passing task to Research Agent: '{query}' ---")
    from .orchestrator import research_node
    result = await research_node({"user_query": query})
    return result.get("research_result", {}).get("report", "Research Agent completed the task.")


CHATBOT_TOOLS = [
    ask_user_clarification,
    trigger_planning_agent,
    trigger_manufacturing_agent,
    trigger_scheme_agent,
    trigger_research_agent,
]


# ==========================================
# CHATBOT NODE (used by orchestrator graph)
# ==========================================

async def chatbot_node(state: AgentState):
    print("--- CHATBOT AGENT (Conversing & Delegating) ---")
    query = state.get("user_query", "")

    try:
        llm = get_nvidia_llm2()
    except Exception:
        llm = get_fallback_llm()

    chatbot = create_react_agent(llm, tools=CHATBOT_TOOLS)
    input_messages = [_build_system_prompt(query, allow_clarification=True), HumanMessage(content=query)]

    try:
        response = await chatbot.ainvoke({"messages": input_messages})
    except Exception as e:
        print(f"[WARNING] Chatbot primary LLM failed: {e}. Retrying...")
        fallback_agent = create_react_agent(get_fallback_llm(), tools=CHATBOT_TOOLS)
        response = await fallback_agent.ainvoke({"messages": input_messages})

    final_output = response["messages"][-1].content
    return {
        "final_report": {"chatbot_response": final_output},
        "messages": [f"Chatbot: {final_output}"]
    }


# ==========================================
# STANDALONE CHATBOT STREAM
# ==========================================

async def run_chatbot_stream(query: str, thread_id: str = "default") -> AsyncGenerator[str, None]:
    _pending_sessions.pop(thread_id, None)
    print(f"\n=== CHATBOT STREAM: '{query}' (thread: {thread_id}) ===")

    try:
        llm = get_default_LLM()
    except Exception:
        llm = get_fallback_llm()

    chatbot = create_react_agent(llm, tools=CHATBOT_TOOLS)
    input_messages = [_build_system_prompt(query, allow_clarification=True), HumanMessage(content=query)]

    async for chunk in _stream_agent(chatbot, input_messages, thread_id, query, clarification_count=0):
        yield chunk


async def resume_chatbot_stream(answer: str, thread_id: str = "default") -> AsyncGenerator[str, None]:
    print(f"\n=== CHATBOT RESUME: answer='{answer}' (thread: {thread_id}) ===")

    session = _pending_sessions.pop(thread_id, None)
    prior_count = session.get("clarification_count", 1) if session else 1

    if _is_dismissive(answer):
        original_query = session.get("original_query", answer) if session else answer
        enriched_query = (
            f"{original_query}\n\n"
            "[Note: User chose not to provide additional details. "
            "Proceed immediately with available information. Do NOT ask any more questions.]"
        )
        print("   -> Dismissive answer. Proceeding with original query.")
    elif session:
        original_query = session.get("original_query", answer)
        question = session.get("question", "")
        enriched_query = (
            f"{original_query}\n\n"
            f"[Clarification provided — Question: {question} | Answer: {answer}]\n"
            "[Now proceed immediately with specialist tools. Do NOT ask any more clarification questions.]"
        )
        print("   -> Resuming with enriched query.")
    else:
        enriched_query = answer

    try:
        llm = get_default_LLM()
    except Exception:
        llm = get_fallback_llm()

    chatbot = create_react_agent(llm, tools=CHATBOT_TOOLS)
    # GUARDRAIL: After resume, NEVER allow clarification again
    input_messages = [_build_system_prompt(enriched_query, allow_clarification=False), HumanMessage(content=enriched_query)]

    async for chunk in _stream_agent(chatbot, input_messages, thread_id, enriched_query, clarification_count=prior_count):
        yield chunk


# ==========================================
# SHARED STREAMING HELPER
# ==========================================

async def _stream_agent(
    chatbot,
    input_messages: list,
    thread_id: str,
    original_query: str,
    clarification_count: int = 0,
) -> AsyncGenerator[str, None]:
    """
    Streams chatbot ReAct events with two key guardrails:
    1. tool_depth counter: suppresses message_chunk tokens from sub-agents running
       inside tools (prevents interleaved/garbled markdown from sub-agent calls).
    2. MAX_CLARIFICATION_ATTEMPTS: blocks infinite clarification loops.
    """
    final_content = ""
    active_tool: str | None = None
    tool_depth = 0  # >0 means we're inside a tool call; suppress sub-agent LLM tokens

    async def _run_stream(agent):
        nonlocal final_content, active_tool, tool_depth

        async for event in agent.astream_events({"messages": input_messages}, version="v2"):
            kind = event["event"]
            name = event.get("name", "")

            # ── Tool started ──
            if kind == "on_tool_start":
                tool_depth += 1
                active_tool = name or "tool"
                print(f"  [TOOL START depth={tool_depth}] -> {active_tool}")
                if active_tool != "ask_user_clarification":
                    yield f"data: {json.dumps({'type': 'tool_start', 'tool_name': active_tool})}\n\n"

            # ── Tool finished ──
            elif kind == "on_tool_end":
                tool_name = name or active_tool or "tool"
                raw_output = event.get("data", {}).get("output")
                output = str(raw_output.content if hasattr(raw_output, "content") else raw_output or "")
                tool_depth = max(0, tool_depth - 1)
                print(f"  [TOOL END depth={tool_depth}] -> {tool_name} | out[:80]: {output[:80]}")

                if tool_name == "ask_user_clarification" and "__CLARIFICATION_NEEDED__:" in output:
                    if clarification_count >= MAX_CLARIFICATION_ATTEMPTS:
                        print(f"  [GUARDRAIL] Max clarifications reached ({MAX_CLARIFICATION_ATTEMPTS}). Skipping.")
                        active_tool = None
                        continue  # Let agent proceed to real tool calls

                    question = output.split("__CLARIFICATION_NEEDED__:", 1)[-1].strip()
                    print(f"  [CHATBOT] Clarification (attempt {clarification_count + 1}): {question}")

                    _pending_sessions[thread_id] = {
                        "original_query": original_query,
                        "question": question,
                        "clarification_count": clarification_count + 1,
                    }
                    yield f"data: {json.dumps({'type': 'interrupted', 'data': {'question': question, 'action': 'clarification'}})}\n\n"
                    return  # Pause stream — resume via /api/chat/resume

                elif tool_name != "ask_user_clarification":
                    yield f"data: {json.dumps({'type': 'tool_end', 'tool_name': tool_name})}\n\n"
                    active_tool = None

            # ── LLM streaming a token ──
            # CRITICAL: Only emit when tool_depth == 0
            # This suppresses tokens from sub-agents running inside tools,
            # preventing garbled/interleaved markdown from bleeding into the chat.
            elif kind == "on_chat_model_stream" and tool_depth == 0:
                chunk = event.get("data", {}).get("chunk")
                if chunk:
                    text = _extract_text(getattr(chunk, "content", ""))
                    if text:
                        final_content += text
                        yield f"data: {json.dumps({'type': 'message_chunk', 'content': text})}\n\n"

    try:
        async for chunk in _run_stream(chatbot):
            yield chunk

        # If interrupted, final_content may be empty — that's fine, stream already ended
        if final_content:
            yield f"data: {json.dumps({'type': 'final_report', 'data': {'final_report': {'chatbot_response': final_content}}})}\n\n"

    except Exception as e:
        print(f"[ERROR] Chatbot stream failed: {e}. Retrying with fallback LLM...")
        try:
            fallback_agent = create_react_agent(get_fallback_llm(), tools=CHATBOT_TOOLS)
            final_content = ""
            tool_depth = 0

            async for chunk in _run_stream(fallback_agent):
                yield chunk

            if final_content:
                yield f"data: {json.dumps({'type': 'final_report', 'data': {'final_report': {'chatbot_response': final_content}}})}\n\n"

        except Exception as e2:
            error_msg = f"⚠️ Agent error: {str(e2)}"
            yield f"data: {json.dumps({'type': 'message_chunk', 'content': error_msg})}\n\n"
            yield f"data: {json.dumps({'type': 'final_report', 'data': {'final_report': {'chatbot_response': error_msg}}})}\n\n"


# ==========================================
# HELPERS
# ==========================================

def _build_system_prompt(query: str, allow_clarification: bool = True) -> SystemMessage:
    clarification_rule = (
        "4. ONLY call 'ask_user_clarification' if the query has ZERO product info, "
        "ZERO budget, AND ZERO location. If ANY of these are present (even partially), "
        "proceed directly to specialist tools WITHOUT asking. Examples that have ENOUGH info:\n"
        "   - '₹50L packaging unit' → budget + product → call trigger_planning_agent directly\n"
        "   - 'EV factory in Pune' → product + location → call tools directly\n"
        "   - 'solar panel subsidies Gujarat' → product + location → call tools directly\n"
        "You may ONLY ask clarification ONCE. Never ask again after that."
        if allow_clarification else
        "4. DO NOT call 'ask_user_clarification' under ANY circumstances. "
        "Proceed immediately with specialist tools using the available information."
    )

    return SystemMessage(
        content=(
            "You are the AI Manufacturing Copilot Chat Assistant.\n\n"
            "RULES:\n"
            f"1. Answer ONLY the CURRENT USER REQUEST: '{query}'\n"
            "2. Do NOT reference data from any prior conversation.\n"
            "3. For simple greetings — answer directly without tools.\n"
            f"{clarification_rule}\n"
            "5. Call the relevant specialist tool(s) for: manufacturing, machinery, factory layout, "
            "business roadmap, CAPEX/OPEX, break-even, government schemes, subsidies, loans, "
            "market research, competitors, or suppliers.\n"
            "6. You MAY call multiple tools if the query spans multiple topics.\n"
            "7. Pass the user's EXACT query to each tool.\n"
            "8. Format your final response clearly in Markdown.\n"
            "9. STRICT SCOPE: Only answer questions related to manufacturing, factories, startups, and business planning. If the user asks about unrelated topics, politely decline to answer."
        )
    )


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return ""
