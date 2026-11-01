import json
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.prebuilt import create_react_agent
from langgraph.errors import GraphInterrupt
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


@tool
async def trigger_compliance_agent(query: str) -> str:
    """Use this tool for environmental compliance, CPCB/SPCB pollution category (Red, Orange, Green, White, Blue), Consent to Establish (CTE), Consent to Operate (CTO), Factory License, Fire NOC, Scope 1 & 2 carbon footprint, and rooftop solar payback ROI."""
    print(f"--- CHATBOT: Passing task to Compliance Agent: '{query}' ---")
    from .tools.compliance_tools import check_factory_environmental_compliance
    return check_factory_environmental_compliance.invoke({"industry_type": query})


@tool
async def find_industrial_locations(query: str) -> str:
    """Find and rank saved Indian industrial parks for a factory-location request.

    Use this whenever the user asks where to establish a unit, requests industrial
    parks in a state/district, or needs location options for a sector. Results are
    from the local industrial-park catalogue and may contain live Google Places
    details only when that API is configured. Do not invent land availability.
    """
    from services.industry_location_service import search_industry_locations

    result = await search_industry_locations(query, limit=5, enrich=True)
    return json.dumps(result, ensure_ascii=False)


CHATBOT_TOOLS = [
    ask_user_clarification,
    trigger_planning_agent,
    trigger_manufacturing_agent,
    trigger_scheme_agent,
    trigger_research_agent,
    trigger_compliance_agent,
    find_industrial_locations,
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
    except GraphInterrupt:
        raise
    except Exception as e:
        print(f"[WARNING] Chatbot primary LLM failed: {e}. Retrying...")
        fallback_agent = create_react_agent(get_fallback_llm(), tools=CHATBOT_TOOLS)
        try:
            response = await fallback_agent.ainvoke({"messages": input_messages})
        except GraphInterrupt:
            raise

    final_output = response["messages"][-1].content
    return {
        "final_report": {"chatbot_response": final_output},
        "messages": [f"Chatbot: {final_output}"]
    }


# ==========================================
# STANDALONE CHATBOT STREAM
# ==========================================

async def run_chatbot_stream(
    query: str,
    thread_id: str = "default",
    history: list | None = None,
    planner_query: str | None = None,
) -> AsyncGenerator[str, None]:
    _pending_sessions.pop(thread_id, None)
    history_len = len(history) if history else 0
    print(f"\n=== CHATBOT STREAM: '{query}' (thread: {thread_id}, history turns: {history_len}, planner_query: '{planner_query}') ===")

    try:
        llm = get_default_LLM()
    except Exception:
        llm = get_fallback_llm()

    chatbot = create_react_agent(llm, tools=CHATBOT_TOOLS)

    semantic_history = ""
    planner_context = ""
    try:
        from core.vector_store import get_user_history_and_workflows
        # 1. Targeted semantic search for the specific planner run if selected by the user
        if planner_query:
            targeted_plan_query = f"{planner_query}: {query}"
            planner_context = get_user_history_and_workflows(user_id=thread_id, current_query=targeted_plan_query, k=5)
            if not planner_context:
                planner_context = get_user_history_and_workflows(user_id=thread_id, current_query=planner_query, k=5)
            print(f"  [SEMANTIC SEARCH] Retrieved {len(planner_context)} chars for planner query '{planner_query}'")

        # 2. General semantic history for the current question
        semantic_history = get_user_history_and_workflows(user_id=thread_id, current_query=query, k=3)
    except Exception as e:
        print(f"[WARNING] Could not fetch semantic history: {e}")

    system_prompt = _build_system_prompt(
        query,
        allow_clarification=True,
        semantic_history=semantic_history,
        planner_context=planner_context,
        planner_query=planner_query,
    )
    input_messages = [system_prompt]

    # Prepend multi-turn conversation history
    if history:
        for msg in history[-12:]:
            role = msg.get("role", "user") if isinstance(msg, dict) else getattr(msg, "role", "user")
            content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
            if not content or not str(content).strip():
                continue
            if role in ("user", "human"):
                input_messages.append(HumanMessage(content=str(content)))
            elif role in ("assistant", "ai", "bot"):
                input_messages.append(AIMessage(content=str(content)))

    input_messages.append(HumanMessage(content=query))

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
            try:
                from core.vector_store import save_interaction_to_vector_db
                save_interaction_to_vector_db(user_id=thread_id, query=original_query, response=final_content, doc_type="chat")
            except Exception as e:
                print(f"[WARNING] Could not save chat interaction to vector store: {e}")

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
                try:
                    from core.vector_store import save_interaction_to_vector_db
                    save_interaction_to_vector_db(user_id=thread_id, query=original_query, response=final_content, doc_type="chat")
                except Exception as e:
                    print(f"[WARNING] Could not save chat interaction to vector store: {e}")

                yield f"data: {json.dumps({'type': 'final_report', 'data': {'final_report': {'chatbot_response': final_content}}})}\n\n"

        except Exception as e2:
            error_msg = f"⚠️ Agent error: {str(e2)}"
            yield f"data: {json.dumps({'type': 'message_chunk', 'content': error_msg})}\n\n"
            yield f"data: {json.dumps({'type': 'final_report', 'data': {'final_report': {'chatbot_response': error_msg}}})}\n\n"


# ==========================================
# HELPERS
# ==========================================

def _build_system_prompt(
    query: str,
    allow_clarification: bool = True,
    semantic_history: str = "",
    planner_context: str = "",
    planner_query: str | None = None,
) -> SystemMessage:
    clarification_rule = (
        "4. ONLY call 'ask_user_clarification' if the query has ZERO product info, "
        "ZERO budget, AND ZERO location, AND the context cannot be inferred from conversation history or the loaded factory plan. If ANY of these are present (even partially), "
        "proceed directly to specialist tools WITHOUT asking. Examples that have ENOUGH info:\n"
        "   - '₹50L packaging unit' → budget + product → call trigger_planning_agent directly\n"
        "   - 'EV factory in Pune' → product + location → call tools directly\n"
        "   - 'solar panel subsidies Gujarat' → product + location → call tools directly\n"
        "You may ONLY ask clarification ONCE. Never ask again after that."
        if allow_clarification else
        "4. DO NOT call 'ask_user_clarification' under ANY circumstances. "
        "Proceed immediately with specialist tools using the available information."
    )

    history_context = ""
    if semantic_history and semantic_history.strip():
        history_context = f"\n\n[RELEVANT PAST CONVERSATIONS & WORKFLOWS FROM MEMORY]:\n{semantic_history.strip()}\n"

    loaded_plan_section = ""
    if planner_context and planner_context.strip():
        loaded_plan_section = (
            f"\n\n=======================================================\n"
            f"🎯 ACTIVE FACTORY PLAN SELECTED BY USER (Retrieved via Semantic Search for: '{planner_query}'):\n"
            f"{planner_context.strip()}\n"
            f"=======================================================\n"
            f"INSTRUCTIONS FOR LOADED PLAN:\n"
            f"- The user specifically opened this conversation to discuss their factory plan for '{planner_query}'.\n"
            f"- Ground your answers in the numbers, machines, costs, subsidies, and strategy from this loaded plan.\n"
            f"- You can calculate adjustments, compare options, explain BOM/machinery, explore subsidies, or suggest optimizations based directly on this plan.\n"
        )

    return SystemMessage(
        content=(
            "You are the AI Manufacturing Copilot Chat Assistant.\n\n"
            "RULES:\n"
            "1. You maintain continuous conversational context across the conversation. Reference earlier messages, follow-up questions, and any loaded factory plan context when answering.\n"
            "2. If the user asks about previous topics, earlier queries, or asks follow-up questions (e.g. 'what was my previous conversation', 'what did we discuss earlier', 'summarize our chat'), summarize or answer accurately using the conversation history and memory.\n"
            "3. For simple greetings, pleasantries, or conversation meta-questions — answer directly in a polite, helpful manner without calling specialist tools.\n"
            f"{clarification_rule}\n"
            "5. Call the relevant specialist tool(s) for technical inquiries: manufacturing, machinery, factory layout, "
            "business roadmap, CAPEX/OPEX, break-even, government schemes, subsidies, loans, "
            "market research, competitors, suppliers, or industrial-park location recommendations.\n"
            "6. You MAY call multiple tools if the query spans multiple topics.\n"
            "7. Pass relevant query parameters to each tool.\n"
            "8. Format your final response clearly in Markdown.\n"
            "9. Maintain helpful focus on manufacturing, factory planning, schemes, compliance, and startup guidance."
            f"{loaded_plan_section}"
            f"{history_context}"
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
