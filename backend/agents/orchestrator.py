from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from psycopg_pool import AsyncConnectionPool
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, SystemMessage

from .state import AgentState
from models.llm import (
    get_default_LLM,
    get_nvidia_llm,
    get_openrouter_llm,
    get_mistral_llm,
    get_openrouter_llm2,
    get_fallback_llm,
    get_gemini_llm,
    get_nvidia_llm2
)
from core.config import settings
from .tools.planning_tools import planning_tools_list
from .tools.manufacturing_tools import manufacturing_tools_list
from .tools.scheme_tools import scheme_tools_list
from .tools.research_tools import research_tools_list
from .tools.shared_tools import shared_tools_list 
from pydantic import BaseModel,Field
from langchain_google_genai import ChatGoogleGenerativeAI
import os
import json
from langgraph.graph import StateGraph, END
from core.vector_store import get_semantic_context, save_interaction_to_vector_db

 

class RouterOutput(BaseModel):
    required_agents: list[str] = Field(
        description="List of exact agent names required to answer the query. Options: 'planning', 'manufacturing', 'scheme', 'research'. Leave empty if you can answer directly."
    )
    direct_answer: str | None = Field(
        default=None,
        description="If the user's query is basic (e.g., 'hi', 'who are you') and requires NO specialist agents, provide the final answer to the user here."
    )
    use_history: bool | str = Field(
        default=False,
        description="Set to true ONLY IF the user's query depends on or refers to past context/history (e.g. 'tell me more about it', 'what about the second option'). Otherwise false."
    )

async def router_node(state: AgentState):
    print("--- ROUTER AGENT (DECIDING Which agent to run) --- ")
    query = state.get("user_query", "")

    prompt = f"""
                You are the Supervisor Agent for an AI Manufacturing Copilot.

                Your responsibility is to determine whether the user's request is within the platform's supported scope and decide which specialist agents should handle it.

                ========================
                SUPPORTED SCOPE
                ========================

                This platform ONLY helps users with manufacturing startup planning and execution.

                Supported topics include:

                1. Planning
                - Business roadmap
                - Startup planning
                - Factory planning
                - Cost estimation
                - CAPEX/OPEX
                - ROI
                - Timeline
                - Risk analysis
                - Team planning

                2. Manufacturing
                - Manufacturing process
                - Machinery recommendations
                - Bill of Materials (BOM)
                - Factory setup
                - Factory layout
                - Production workflow
                - Utilities
                - Raw materials
                - Quality standards

                3. Government Schemes
                - Government subsidies
                - MSME
                - Startup India
                - SIDBI
                - CGTMSE
                - PLI
                - State schemes
                - Loan recommendations
                - Grants
                - Tax incentives
                - Incubators

                4. Research
                - Market research
                - Competitor analysis
                - Industry trends
                - Supplier search
                - Market size
                - TAM/SAM/SOM
                - Industry reports
                - Manufacturing news

                ========================
                OUT OF SCOPE
                ========================

                Do NOT answer or route requests related to:

                - Programming
                - Coding
                - Debugging
                - Mathematics
                - School homework
                - Essay writing
                - Translation
                - General knowledge
                - Politics
                - Entertainment
                - Sports
                - Medical advice
                - Legal advice
                - Personal finance
                - Stock market
                - Cryptocurrency
                - Travel
                - Cooking
                - Story writing
                - Image generation
                - Casual conversation unrelated to manufacturing startups
                - Any topic unrelated to manufacturing businesses

                ========================
                DECISION RULES
                ========================

                1. If the request is within the supported scope:
                - Return the required specialist agents.
                - Leave direct_answer empty.
                - Set use_history to true ONLY if the user is referring to a previous topic.

                2. If the request is a simple greeting
                (e.g. "Hi", "Hello", "Good Morning"):
                - required_agents should be empty.
                - Respond politely in direct_answer.

                3. If the request is outside the supported scope:
                - required_agents must be empty.
                - Explain politely that this platform specializes in manufacturing startups.
                - Encourage the user to ask questions related to:
                    • manufacturing
                    • factory setup
                    • startup planning
                    • government schemes
                    • market research
                    • supplier discovery

                Never attempt to answer out-of-scope questions.

                ========================
                AVAILABLE AGENTS
                ========================

                planning
                Use for:
                - Business roadmap
                - Timeline
                - Budget
                - Cost estimation
                - Factory planning
                - Risk analysis

                manufacturing
                Use for:
                - Manufacturing process
                - Machinery
                - Factory setup
                - BOM
                - Production workflow
                - Raw materials

                scheme
                Use for:
                - Government schemes
                - Subsidies
                - Grants
                - Loans
                - MSME
                - Startup India
                - PLI
                - SIDBI
                - Tax benefits

                research
                Use for:
                - Market research
                - Competitors
                - Suppliers
                - Industry reports
                - Trends
                - News

                User Query:
                "{query}"
                """ 

    try:
        base_llm = get_nvidia_llm2()
        try:
            structured_llm = base_llm.with_structured_output(RouterOutput, method="json_mode")
            result = await structured_llm.ainvoke(prompt)
        except Exception:
            structured_llm = base_llm.with_structured_output(RouterOutput)
            result = await structured_llm.ainvoke(prompt)
    except Exception as e:
        print(f"[WARNING] Router LLM structured output failed: {e}. Defaulting to all specialist agents.")
        result = RouterOutput(
            required_agents=["planning", "manufacturing", "scheme", "research"],
            direct_answer="",
            use_history=False
        )
    chosen = result.required_agents

    if not chosen and result.direct_answer.strip():
        print(f"   -> Basic Query Detected. Direct Answer: {result.direct_answer}")
        return {
            "required_agents": [], 
            "messages": [f"Router answered directly: {result.direct_answer}"],
            "final_report": {"general": {"report": result.direct_answer}}
        }
    
    if not chosen and not result.direct_answer.strip():
         chosen = ["planning", "manufacturing", "scheme", "research"]
         
    use_history_val = str(result.use_history).strip().lower() == "true"
         
    print(f"   -> Selected Agents: {chosen}, Use History: {use_history_val}")
    return {"required_agents": chosen, "use_history": use_history_val, "messages": [f"Router selected agents: {chosen}. Use history: {use_history_val}"]}




async def planning_node(state: AgentState):
    print("--- PLANNING AGENT (Roadmap + costs) ---")
    user_query = state.get("user_query", "")
    if state.get("use_history") and state.get("semantic_context"):
        ctx = str(state.get("semantic_context", ""))[:800]
        query = f"CURRENT USER REQUEST: {user_query}\n\n[Reference History (Do NOT answer this old request)]: {ctx}"
    else:
        query = user_query

    try:
        llm = get_openrouter_llm2()
    except Exception:
        llm = get_default_LLM()

    all_planning_tools = planning_tools_list + shared_tools_list
    planning_agent = create_react_agent(llm, tools=all_planning_tools)

    system_prompt = SystemMessage(content=(
        f"You are an expert Manufacturing Planning Agent. "
        f"CRITICAL: Focus ONLY on the Product, Budget, and Location from the CURRENT USER REQUEST ('{user_query}'). "
        f"Do NOT generate a report for any past product in history. "
        f"You MUST use your tools to generate a Business Roadmap, Timeline, Milestones, "
        f"Estimated Investment, Risks, Team Requirements, and Factory Size. "
        f"Summarize all the findings beautifully in Markdown format."
    ))

    print("   -> Thinking and using tools....")
    try:
        response = await planning_agent.ainvoke({
            "messages": [system_prompt, HumanMessage(content=query)]
        })
    except Exception as e:
        print(f"[WARNING] Planning Agent primary LLM failed: {e}. Retrying with fallback LLM...")
        fallback_llm = get_fallback_llm()
        fallback_agent = create_react_agent(fallback_llm, tools=all_planning_tools)
        try:
            response = await fallback_agent.ainvoke({
                "messages": [system_prompt, HumanMessage(content=query)]
            })
        except Exception as e2:
            print(f"[ERROR] Planning Agent fallback LLM failed: {e2}")
            response = {"messages": [SystemMessage(content=f"Error executing Planning Agent: {e2}")]}

    final_output = response["messages"][-1].content
    return {
        "planning_result": {"report": final_output},
        "messages": ["Planning Agent successfully generated the roadmap and costs."]
    }


async def manufacturing_node(state: AgentState):
    print("--- MANUFACTURING AGENT (Process + Machinery + Setup) ---")
    user_query = state.get("user_query", "")
    if state.get("use_history") and state.get("semantic_context"):
        ctx = str(state.get("semantic_context", ""))[:800]
        query = f"CURRENT USER REQUEST: {user_query}\n\n[Reference History (Do NOT answer this old request)]: {ctx}"
    else:
        query = user_query

    try:
        llm = get_default_LLM()
    except Exception:
        llm = get_fallback_llm()

    all_manufacturing_tools = manufacturing_tools_list + shared_tools_list
    manufacturing_agent = create_react_agent(llm, tools=all_manufacturing_tools)

    system_prompt = SystemMessage(content=(
        f"You are an expert Manufacturing Agent. "
        f"CRITICAL: Focus ONLY on the Product and Location from the CURRENT USER REQUEST ('{user_query}'). "
        f"Do NOT generate a report for any past product in history. "
        f"You MUST use your tools to generate a comprehensive manufacturing plan including: "
        f"Manufacturing Process, Machinery, Factory Layout, BOM, Quality Standards (BIS), and Energy Requirements. "
        f"Summarize all the findings beautifully in Markdown format."
    ))

    print("   -> Thinking and using manufacturing tools....")
    try:
        response = await manufacturing_agent.ainvoke({
            "messages": [system_prompt, HumanMessage(content=query)]
        })
    except Exception as e:
        print(f"[WARNING] Manufacturing Agent primary LLM failed: {e}. Retrying with fallback LLM...")
        fallback_llm = get_fallback_llm()
        fallback_agent = create_react_agent(fallback_llm, tools=all_manufacturing_tools)
        try:
            response = await fallback_agent.ainvoke({
                "messages": [system_prompt, HumanMessage(content=query)]
            })
        except Exception as e2:
            print(f"[ERROR] Manufacturing Agent fallback LLM failed: {e2}")
            response = {"messages": [SystemMessage(content=f"Error executing Manufacturing Agent: {e2}")]}

    final_output = response["messages"][-1].content
    return {
        "manufacturing_result": {"report": final_output},
        "messages": ["Manufacturing Agent successfully designed the production line."]
    }


async def scheme_node(state: AgentState):
    print("--- SCHEME AGENT (Govt + pvt funding) ---")
    user_query = state.get("user_query", "")
    if state.get("use_history") and state.get("semantic_context"):
        ctx = str(state.get("semantic_context", ""))[:800]
        query = f"CURRENT USER REQUEST: {user_query}\n\n[Reference History (Do NOT answer this old request)]: {ctx}"
    else:
        query = user_query

    try:
        llm = get_openrouter_llm()
    except Exception:
        llm = get_default_LLM()

    all_scheme_tools = scheme_tools_list + shared_tools_list
    scheme_agent = create_react_agent(llm, tools=all_scheme_tools)

    system_prompt = SystemMessage(content=(
        f"You are an expert Government Scheme and Funding Agent for startups in India. "
        f"CRITICAL: Focus ONLY on the Industry, Investment, and Location from the CURRENT USER REQUEST ('{user_query}'). "
        f"Do NOT generate a report for any past product or location in history. "
        f"You MUST use your tools to find Central/State schemes, check eligibility, calculate subsidies, "
        f"and recommend loans and incubators. "
        f"Summarize all the findings beautifully in Markdown format."
    ))
    print(" -> Thinking and using scheme tools...")

    try:
        response = await scheme_agent.ainvoke({
            "messages": [system_prompt, HumanMessage(content=query)]
        })
    except Exception as e:
        print(f"[WARNING] Scheme Agent primary LLM failed: {e}. Retrying with fallback LLM...")
        fallback_llm = get_fallback_llm()
        fallback_agent = create_react_agent(fallback_llm, tools=all_scheme_tools)
        try:
            response = await fallback_agent.ainvoke({
                "messages": [system_prompt, HumanMessage(content=query)]
            })
        except Exception as e2:
            print(f"[ERROR] Scheme Agent fallback LLM failed: {e2}")
            response = {"messages": [SystemMessage(content=f"Error executing Scheme Agent: {e2}")]}

    final_output = response["messages"][-1].content
    return {
        "scheme_result": {"report": final_output},
        "messages": ["Scheme Agent successfully found applicable schemes and funding."]
    }


async def research_node(state: AgentState):
    print("--- RESEARCH AGENT (Market + trends) ---")
    user_query = state.get("user_query", "")
    if state.get("use_history") and state.get("semantic_context"):
        ctx = str(state.get("semantic_context", ""))[:800]
        query = f"CURRENT USER REQUEST: {user_query}\n\n[Reference History (Do NOT answer this old request)]: {ctx}"
    else:
        query = user_query

    try:
        llm = get_default_LLM()
    except Exception:
        llm = get_fallback_llm()

    all_research_tools = research_tools_list + shared_tools_list
    research_agent = create_react_agent(llm, tools=all_research_tools)

    system_prompt = SystemMessage(content=(
        f"You are an expert Research Agent (Internet Intelligence). "
        f"CRITICAL: Focus ONLY on the Product, Industry, and Location from the CURRENT USER REQUEST ('{user_query}'). "
        f"Do NOT generate a report for any past product in history. "
        f"You MUST use your tools to analyze Competitors, Market Size (TAM/SAM/SOM), find Suppliers, "
        f"and get the latest Industry Trends and News. "
        f"Summarize all the findings beautifully in Markdown format."
    ))

    print("-> Thinking and using research tools...")
    try:
        response = await research_agent.ainvoke({
            "messages": [system_prompt, HumanMessage(content=query)]
        })
    except Exception as e:
        print(f"[WARNING] Research Agent primary LLM failed: {e}. Retrying with fallback LLM...")
        fallback_llm = get_fallback_llm()
        fallback_agent = create_react_agent(fallback_llm, tools=all_research_tools)
        try:
            response = await fallback_agent.ainvoke({
                "messages": [system_prompt, HumanMessage(content=query)]
            })
        except Exception as e2:
            print(f"[ERROR] Research Agent fallback LLM failed: {e2}")
            response = {"messages": [SystemMessage(content=f"Error executing Research Agent: {e2}")]}

    final_output = response["messages"][-1].content
    return {
        "research_result": {"report": final_output},
        "messages": ["Research Agent successfully analyzed the market and competitors."]
    }


async def finalize_node(state: AgentState):
    print("--- ORCHESTRATOR COMBINING RESPONSES ---")
    final_report = {
        "query": state.get("user_query"),
        "planning": state.get("planning_result"),
        "manufacturing": state.get("manufacturing_result"),
        "schemes": state.get("scheme_result"),
        "research": state.get("research_result")
    }
    return {"final_report": final_report, "messages": ["Final report generated."]}


# 1. Initialize the Orchestrator Graph
orchestrator_workflow=StateGraph(AgentState)

# 2. Add nodes (The 4 Specialist Agents + Combiner)
orchestrator_workflow.add_node("router", router_node)
orchestrator_workflow.add_node("planning", planning_node)
orchestrator_workflow.add_node("manufacturing", manufacturing_node)
orchestrator_workflow.add_node("scheme", scheme_node)
orchestrator_workflow.add_node("research", research_node)
orchestrator_workflow.add_node("finalize", finalize_node)


def route_agents(state: AgentState):
    # LangGraph will run whatever list of nodes this returns simultaneously
    return state.get("required_agents", ["planning", "manufacturing", "scheme", "research"])






# 3. Define the routing / workflow
# According to the architecture image, the Orchestrator splits work across the 4 agents.
# We run them sequentially here, but LangGraph also supports running them in parallel.
orchestrator_workflow.set_entry_point("router")
orchestrator_workflow.add_conditional_edges(
    "router",
    route_agents,
    ["planning", "manufacturing", "scheme", "research"]
)
orchestrator_workflow.add_edge("planning", "finalize")
orchestrator_workflow.add_edge("manufacturing", "finalize")
orchestrator_workflow.add_edge("scheme", "finalize")
orchestrator_workflow.add_edge("research", "finalize")
orchestrator_workflow.add_edge("finalize", END)

# 4. Compile the Graph

# We don't compile with MemorySaver globally anymore.
# We will compile it dynamically in run_orchestrator using the async context manager.
# orchestrator_workflow.compile()

pool: AsyncConnectionPool | None = None

async def get_orchestrator_checkpointer():
    global pool
    db_url = getattr(settings, "DATABASE_URL", "") or ""
    if db_url.startswith("postgresql") or db_url.startswith("postgres"):
        try:
            if pool is not None and getattr(pool, "closed", False):
                pool = None
            if pool is None:
                pool = AsyncConnectionPool(
                    conninfo=db_url,
                    max_size=20,
                    kwargs={"autocommit": True, "prepare_threshold": 0},
                    open=False
                )
                await pool.open(wait=True, timeout=5.0)
            checkpointer = AsyncPostgresSaver(pool)
            await checkpointer.setup()
            return checkpointer
        except Exception as e:
            print(f"[WARNING] Postgres checkpointer pool connection failed: {e}. Falling back to MemorySaver.")
            pool = None
            return MemorySaver()
    return MemorySaver()


async def run_orchestrator(query: str, thread_id: str = "default_session"):
    """
    Streaming Entry Point to trigger the AI brain and yield Server-Sent Events.
    """

    semantic_context = get_semantic_context(user_id=thread_id, current_query=query, k=3)

    inputs = {"user_query": query, "semantic_context": semantic_context, "messages": []}

    checkpointer = await get_orchestrator_checkpointer()
    graph = orchestrator_workflow.compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": thread_id}}

    current_state = await graph.aget_state(config)

    if current_state.values.get("messages"):
        pass

    result = await graph.ainvoke(inputs, config=config)
    
    final_response_text = str(result.get("final_report", "Business plan generated."))
    
    save_interaction_to_vector_db(user_id=thread_id, query=query, response=final_response_text)

    return result


def _extract_content_text(content) -> str:
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict) and "text" in part:
                text_parts.append(str(part.get("text", "")))
        return "".join(text_parts)
    elif hasattr(content, "text"):
        return str(content.text)
    return ""


async def run_orchestrator_stream(query: str, thread_id: str = "default_session"):
    """
    Streaming Entry Point to trigger the AI brain and yield Server-Sent Events.
    """
    semantic_context = get_semantic_context(user_id=thread_id, current_query=query, k=3)

    checkpointer = await get_orchestrator_checkpointer()
    graph = orchestrator_workflow.compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": thread_id}}

    inputs = {"user_query": query, "semantic_context": semantic_context, "messages": []}
    
    SPECIALIST_NODES = {"planning", "manufacturing", "scheme", "research"}

    async for event in graph.astream_events(inputs, config=config, version="v2"):
        kind = event["event"]
        name = event.get("name", "")
        
        # 1. Stream agent node lifecycle events
        if kind == "on_chain_start" and name in SPECIALIST_NODES:
            yield f"data: {json.dumps({'type': 'agent_start', 'agent': name})}\n\n"
            
        elif kind == "on_chain_end" and name in SPECIALIST_NODES:
            yield f"data: {json.dumps({'type': 'agent_completed', 'agent': name})}\n\n"

        # 2. Stream the text as the LLM types it out
        elif kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk:
                content = getattr(chunk, "content", "")
                content_text = _extract_content_text(content)
                if content_text:
                    yield f"data: {json.dumps({'type': 'message_chunk', 'content': content_text})}\n\n"
                
        # 3. Tell the frontend when a tool starts executing
        elif kind == "on_tool_start":
            tool_name = name or event.get("data", {}).get("name", "tool")
            yield f"data: {json.dumps({'type': 'tool_start', 'tool_name': tool_name})}\n\n"
            
        # 4. Tell the frontend when the tool finishes
        elif kind == "on_tool_end":
            tool_name = name or event.get("data", {}).get("name", "tool")
            yield f"data: {json.dumps({'type': 'tool_end', 'tool_name': tool_name})}\n\n"

    # 5. Once the graph finishes, check if it was interrupted
    final_state = await graph.aget_state(config)
    
    if final_state.tasks:
        for task in final_state.tasks:
            if task.interrupts:
                interrupt_payload = task.interrupts[0].value
                yield f"data: {json.dumps({'type': 'interrupted', 'data': interrupt_payload})}\n\n"
                return

    final_report = final_state.values.get("final_report")
    
    if final_report:
        final_response_text = str(final_report)
        save_interaction_to_vector_db(user_id=thread_id, query=query, response=final_response_text)
        
        yield f"data: {json.dumps({'type': 'final_report', 'data': {'final_report': final_report}})}\n\n"


async def resume_orchestrator_stream(answer: str, thread_id: str = "default_session"):
    """
    Resumes an interrupted graph execution by supplying the user's answer.
    """
    checkpointer = await get_orchestrator_checkpointer()
    graph = orchestrator_workflow.compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": thread_id}}
    
    inputs = Command(resume=answer)
    SPECIALIST_NODES = {"planning", "manufacturing", "scheme", "research"}
    
    async for event in graph.astream_events(inputs, config=config, version="v2"):
        kind = event["event"]
        name = event.get("name", "")
        
        if kind == "on_chain_start" and name in SPECIALIST_NODES:
            yield f"data: {json.dumps({'type': 'agent_start', 'agent': name})}\n\n"
            
        elif kind == "on_chain_end" and name in SPECIALIST_NODES:
            yield f"data: {json.dumps({'type': 'agent_completed', 'agent': name})}\n\n"
            
        elif kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk:
                content = getattr(chunk, "content", "")
                content_text = _extract_content_text(content)
                if content_text:
                    yield f"data: {json.dumps({'type': 'message_chunk', 'content': content_text})}\n\n"
                
        elif kind == "on_tool_start":
            tool_name = name or event.get("data", {}).get("name", "tool")
            yield f"data: {json.dumps({'type': 'tool_start', 'tool_name': tool_name})}\n\n"
            
        elif kind == "on_tool_end":
            tool_name = name or event.get("data", {}).get("name", "tool")
            yield f"data: {json.dumps({'type': 'tool_end', 'tool_name': tool_name})}\n\n"

    final_state = await graph.aget_state(config)
    
    if final_state.tasks:
        for task in final_state.tasks:
            if task.interrupts:
                interrupt_payload = task.interrupts[0].value
                yield f"data: {json.dumps({'type': 'interrupted', 'data': interrupt_payload})}\n\n"
                return

    final_report = final_state.values.get("final_report")
    
    if final_report:
        final_response_text = str(final_report)
        query = final_state.values.get("user_query", "Resumed query")
        save_interaction_to_vector_db(user_id=thread_id, query=query, response=final_response_text)
        
        yield f"data: {json.dumps({'type': 'final_report', 'data': {'final_report': final_report}})}\n\n"
