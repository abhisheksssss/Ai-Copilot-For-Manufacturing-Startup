from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from langgraph.errors import GraphInterrupt
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
    get_openrouter_llm3,
    get_planning_llm,
    get_manufacturing_llm,
    get_scheme_llm,
    get_research_llm,
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
from .judge import run_judge_agent
from pydantic import BaseModel,Field
from langchain_google_genai import ChatGoogleGenerativeAI
import os
import json
from langgraph.graph import StateGraph, END
from core.vector_store import save_workflow_to_vector_db

 

class RouterOutput(BaseModel):
    required_agents: list[str] = Field(
        description="List of exact agent names required to answer the query. Options: 'planning', 'manufacturing', 'scheme', 'research'. Leave empty if you can answer directly."
    )
    direct_answer: str | None = Field(
        default=None,
        description="If the user's query is basic (e.g., 'hi', 'who are you') and requires NO specialist agents, provide the final answer to the user here."
    )
    use_history: bool = Field(
        default=False,
        description="Always false for factory planner as each plan is generated fresh."
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
                - Every factory plan is a standalone, independent plan.

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
         
    print(f"   -> Selected Agents: {chosen}")
    return {"required_agents": chosen, "use_history": False, "messages": [f"Router selected agents: {chosen}."]}




def _to_text(content) -> str:
    """Helper to safely extract string text from string, dict, or list of message content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
        return "".join(parts)
    return str(content or "")


async def _clean_subagent_output(
    response: dict,
    user_query: str,
    llm,
    agent_type: str = "Market & Supplier Research"
) -> str:
    """
    Cleans sub-agent response and ensures a rich Markdown report is ALWAYS generated.
    If the agent ended on a tool execution, hit step limits, or produced incomplete text,
    it automatically synthesizes all collected tool outputs into a structured Markdown report.
    """
    messages = response.get("messages", [])
    if not messages:
        return f"{agent_type} report unavailable."

    # Look backwards for the latest genuine AIMessage with text content and NO pending tool calls
    candidate_output = ""
    for msg in reversed(messages):
        msg_type = getattr(msg, "type", "") or msg.__class__.__name__.lower()
        if "ai" in msg_type or "assistant" in msg_type:
            tool_calls = getattr(msg, "tool_calls", None)
            raw_content = getattr(msg, "content", "")
            text_content = _to_text(raw_content).strip()
            if text_content and not tool_calls:
                candidate_output = text_content
                break

    # Determine if synthesis is needed
    needs_synthesis = (
        not candidate_output
        or len(candidate_output) < 250
        or "Sorry, need more steps" in candidate_output
        or candidate_output.startswith("Error")
        or candidate_output.startswith("[INFO]")
        or candidate_output.startswith("[TOOL")
    )

    if not needs_synthesis:
        return candidate_output

    print(f"[RECOVERY] Incomplete output detected for {agent_type} (len={len(candidate_output)}). Synthesizing comprehensive report from research data...")
    collected = []
    for msg in messages:
        content = getattr(msg, "content", "")
        text_str = _to_text(content).strip()
        if text_str and len(text_str) > 20 and not text_str.lower().startswith("system:"):
            if "Sorry, need more steps" not in text_str and not text_str.startswith("[INFO]"):
                collected.append(text_str[:1500])

    if collected:
        synthesis_prompt = (
            f"You are an expert industrial {agent_type} analyst.\n"
            f"Synthesize a comprehensive, professional Markdown report for the request: '{user_query}'\n"
            f"Structure the report clearly with headers and bullet points:\n"
            f"1. Executive Summary & Market Intelligence (TAM/SAM/SOM, CAGR, regional demand)\n"
            f"2. Competitive Landscape & Key Players in India (Market share, positioning)\n"
            f"3. Verified Machinery & Equipment Suppliers (Name, Location/Industrial Area, Equipment Specs, Estimated Pricing, Contact/Website)\n"
            f"4. Supply Chain Sourcing & Raw Materials Strategy\n"
            f"5. Industry Trends, BIS Quality Standards & Strategic Outlook\n\n"
            f"Use the following collected research and tool data:\n\n"
            + "\n\n---\n\n".join(collected)
        )
        try:
            syn_resp = await llm.ainvoke([
                SystemMessage(content="Output ONLY a clean, comprehensive, well-formatted Markdown report with clear headers and bullet points. Do not include raw JSON or search snippets."),
                HumanMessage(content=synthesis_prompt)
            ])
            return _to_text(syn_resp.content)
        except Exception as ex:
            print(f"[WARNING] Primary synthesis failed: {ex}. Retrying with fallback LLM...")
            try:
                fallback_llm = get_fallback_llm()
                syn_resp = await fallback_llm.ainvoke([
                    SystemMessage(content="Output ONLY a clean, comprehensive, well-formatted Markdown report with clear headers and bullet points."),
                    HumanMessage(content=synthesis_prompt)
                ])
                return _to_text(syn_resp.content)
            except Exception as ex2:
                print(f"[ERROR] Fallback synthesis failed: {ex2}")
                return "\n\n".join(collected)

    return candidate_output or f"{agent_type} report unavailable."


async def planning_node(state: AgentState):
    print("--- PLANNING AGENT (Roadmap + costs) ---")
    user_query = state.get("user_query", "")
    query = user_query

    try:
        llm = get_planning_llm()
    except Exception:
        llm = get_fallback_llm()

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
        response = await planning_agent.ainvoke(
            {"messages": [system_prompt, HumanMessage(content=query)]},
            config={"recursion_limit": 15}
        )
    except GraphInterrupt:
        raise
    except Exception as e:
        print(f"[WARNING] Planning Agent primary LLM failed: {e}. Retrying with fallback LLM...")
        fallback_llm = get_fallback_llm()
        fallback_agent = create_react_agent(fallback_llm, tools=all_planning_tools)
        try:
            response = await fallback_agent.ainvoke(
                {"messages": [system_prompt, HumanMessage(content=query)]},
                config={"recursion_limit": 15}
            )
        except GraphInterrupt:
            raise
        except Exception as e2:
            print(f"[ERROR] Planning Agent fallback LLM failed: {e2}")
            response = {"messages": [SystemMessage(content=f"Error executing Planning Agent: {e2}")]}

    final_output = await _clean_subagent_output(response, user_query, llm, agent_type="Planning & Financial Strategy")
    return {
        "planning_result": {"report": final_output},
        "messages": ["Planning Agent successfully generated the roadmap and costs."]
    }


async def manufacturing_node(state: AgentState):
    print("--- MANUFACTURING AGENT (Process + Machinery + Setup) ---")
    user_query = state.get("user_query", "")

    # Retrieve context from preceding Planning Agent in the series
    planning_res = state.get("planning_result")
    planning_report = ""
    if isinstance(planning_res, dict):
        planning_report = planning_res.get("report", "")
    elif isinstance(planning_res, str):
        planning_report = planning_res

    query = user_query
    if planning_report and not planning_report.startswith("Error"):
        query = (
            f"{user_query}\n\n"
            f"--- CONTEXT FROM PRECEDING PLANNING AGENT ---\n"
            f"Align your machinery selection, factory layout, and BOM with this established plan:\n"
            f"{planning_report[:2000]}\n"
            f"----------------------------------------------"
        )

    try:
        llm = get_manufacturing_llm()
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
        response = await manufacturing_agent.ainvoke(
            {"messages": [system_prompt, HumanMessage(content=query)]},
            config={"recursion_limit": 15}
        )
    except GraphInterrupt:
        raise
    except Exception as e:
        print(f"[WARNING] Manufacturing Agent primary LLM failed: {e}. Retrying with fallback LLM...")
        fallback_llm = get_fallback_llm()
        fallback_agent = create_react_agent(fallback_llm, tools=all_manufacturing_tools)
        try:
            response = await fallback_agent.ainvoke(
                {"messages": [system_prompt, HumanMessage(content=query)]},
                config={"recursion_limit": 15}
            )
        except GraphInterrupt:
            raise
        except Exception as e2:
            print(f"[ERROR] Manufacturing Agent fallback LLM failed: {e2}")
            response = {"messages": [SystemMessage(content=f"Error executing Manufacturing Agent: {e2}")]}

    final_output = await _clean_subagent_output(response, user_query, llm, agent_type="Manufacturing & Factory Design")
    return {
        "manufacturing_result": {"report": final_output},
        "messages": ["Manufacturing Agent successfully designed the production line."]
    }


async def scheme_node(state: AgentState):
    print("--- SCHEME AGENT (Govt + pvt funding) ---")
    user_query = state.get("user_query", "")

    # Retrieve context from preceding Planning & Manufacturing Agents in the series
    planning_res = state.get("planning_result")
    mfg_res = state.get("manufacturing_result")
    planning_report = planning_res.get("report", "") if isinstance(planning_res, dict) else str(planning_res or "")
    mfg_report = mfg_res.get("report", "") if isinstance(mfg_res, dict) else str(mfg_res or "")

    context_parts = []
    if planning_report and not planning_report.startswith("Error"):
        context_parts.append(f"Planning Context (Budget, Factory Scale, Location):\n{planning_report[:1200]}")
    if mfg_report and not mfg_report.startswith("Error"):
        context_parts.append(f"Manufacturing Context (Machinery & Capex):\n{mfg_report[:1200]}")

    query = user_query
    if context_parts:
        query = (
            f"{user_query}\n\n"
            f"--- CONTEXT FROM PRECEDING AGENTS ---\n"
            f"Calculate exact eligible subsidies, schemes, and financing for these specifications:\n"
            + "\n\n".join(context_parts) + "\n"
            f"------------------------------------"
        )

    try:
        llm = get_scheme_llm()
    except Exception:
        llm = get_fallback_llm()

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
        response = await scheme_agent.ainvoke(
            {"messages": [system_prompt, HumanMessage(content=query)]},
            config={"recursion_limit": 15}
        )
    except GraphInterrupt:
        raise
    except Exception as e:
        print(f"[WARNING] Scheme Agent primary LLM failed: {e}. Retrying with fallback LLM...")
        fallback_llm = get_fallback_llm()
        fallback_agent = create_react_agent(fallback_llm, tools=all_scheme_tools)
        try:
            response = await fallback_agent.ainvoke(
                {"messages": [system_prompt, HumanMessage(content=query)]},
                config={"recursion_limit": 15}
            )
        except GraphInterrupt:
            raise
        except Exception as e2:
            print(f"[ERROR] Scheme Agent fallback LLM failed: {e2}")
            response = {"messages": [SystemMessage(content=f"Error executing Scheme Agent: {e2}")]}

    final_output = await _clean_subagent_output(response, user_query, llm, agent_type="Government Schemes & Subsidies")
    return {
        "scheme_result": {"report": final_output},
        "messages": ["Scheme Agent successfully found applicable schemes and funding."]
    }


async def research_node(state: AgentState):
    print("--- RESEARCH AGENT (Market + trends) ---")
    user_query = state.get("user_query", "")

    # Retrieve context from preceding Planning & Manufacturing Agents in the series
    planning_res = state.get("planning_result")
    mfg_res = state.get("manufacturing_result")
    planning_report = planning_res.get("report", "") if isinstance(planning_res, dict) else str(planning_res or "")
    mfg_report = mfg_res.get("report", "") if isinstance(mfg_res, dict) else str(mfg_res or "")

    context_parts = []
    if mfg_report and not mfg_report.startswith("Error"):
        context_parts.append(f"Manufacturing Equipment & Key Machinery to Find Suppliers For:\n{mfg_report[:1200]}")
    if planning_report and not planning_report.startswith("Error"):
        context_parts.append(f"Target Scale and Location:\n{planning_report[:600]}")

    query = user_query
    if context_parts:
        query = (
            f"{user_query}\n\n"
            f"--- CONTEXT FROM PRECEDING AGENTS ---\n"
            f"Find specific suppliers and market intelligence matching these equipment and setup details:\n"
            + "\n\n".join(context_parts) + "\n"
            f"------------------------------------"
        )

    try:
        llm = get_research_llm()
    except Exception:
        llm = get_fallback_llm()

    all_research_tools = research_tools_list + shared_tools_list
    research_agent = create_react_agent(llm, tools=all_research_tools)

    system_prompt = SystemMessage(content=(
        f"You are an expert Research Agent (Internet Intelligence & Supplier Discovery).\n"
        f"CRITICAL: Focus ONLY on the Product, Industry, and Location from the CURRENT USER REQUEST ('{user_query}').\n"
        f"Do NOT generate a report for any past product in history.\n"
        f"You MUST use your tools (supplier_search, web_search, market_size_calculator, competitor_analyzer) to gather live data.\n"
        f"IMPORTANT: After using tools, YOU MUST OUTPUT A COMPLETE, DETAILED MARKDOWN REPORT containing:\n"
        f"1. Market Overview & Size (TAM, SAM, SOM) with growth forecasts (CAGR)\n"
        f"2. Competitive Landscape & Top Manufacturers in India\n"
        f"3. Verified Machinery & Equipment Suppliers in or near the target location (Name, Location, Specs, Pricing/Contact)\n"
        f"4. Supply Chain Sourcing & Raw Materials Strategy\n"
        f"5. Key Industry Trends & Quality Standards (BIS/ISO)\n\n"
        f"RANKING RULES FOR SUPPLIERS:\n"
        f"1. When listing suppliers, rank actual equipment manufacturers and machinery suppliers in the target location FIRST.\n"
        f"2. Present verified B2B vendors (IndiaMART, TradeIndia, verified corporate domains) with specifications and pricing.\n"
        f"3. NEVER rank generic government portals or policy homepages as top suppliers.\n"
        f"Summarize all findings beautifully in Markdown format."
    ))

    print("-> Thinking and using research tools...")
    try:
        response = await research_agent.ainvoke(
            {"messages": [system_prompt, HumanMessage(content=query)]},
            config={"recursion_limit": 30}
        )
    except GraphInterrupt:
        raise
    except Exception as e:
        print(f"[WARNING] Research Agent primary LLM failed: {e}. Retrying with fallback LLM...")
        fallback_llm = get_fallback_llm()
        fallback_agent = create_react_agent(fallback_llm, tools=all_research_tools)
        try:
            response = await fallback_agent.ainvoke(
                {"messages": [system_prompt, HumanMessage(content=query)]},
                config={"recursion_limit": 30}
            )
        except GraphInterrupt:
            raise
        except Exception as e2:
            print(f"[ERROR] Research Agent fallback LLM failed: {e2}")
            response = {"messages": [SystemMessage(content=f"Error executing Research Agent: {e2}")]}

    final_output = await _clean_subagent_output(response, user_query, llm, agent_type="Market Intelligence & Supplier Discovery")
    return {
        "research_result": {"report": final_output},
        "messages": ["Research Agent successfully analyzed the market and competitors."]
    }


async def judge_node(state: AgentState):
    print("--- JUDGE AGENT (Quality Assurance & Verification) ---")
    user_query = state.get("user_query", "")
    planning_res = state.get("planning_result")
    mfg_res = state.get("manufacturing_result")
    scheme_res = state.get("scheme_result")
    research_res = state.get("research_result")

    judge_result = await run_judge_agent(
        user_query=user_query,
        planning_result=planning_res,
        manufacturing_result=mfg_res,
        scheme_result=scheme_res,
        research_result=research_res
    )
    
    res_dict = judge_result.model_dump()
    print(f"   -> Judge Evaluation Status: {judge_result.status} | Mistakes Found: {len(judge_result.mistakes)}")
    return {
        "judge_result": res_dict,
        "messages": [f"Judge Agent evaluated workflow output with status: {judge_result.status}"]
    }


async def finalize_node(state: AgentState):
    print("--- ORCHESTRATOR COMBINING RESPONSES ---")
    final_report = {
        "query": state.get("user_query"),
        "planning": state.get("planning_result"),
        "manufacturing": state.get("manufacturing_result"),
        "schemes": state.get("scheme_result"),
        "research": state.get("research_result"),
        "judge": state.get("judge_result")
    }
    return {"final_report": final_report, "messages": ["Final report generated."]}


# 1. Initialize the Orchestrator Graph
orchestrator_workflow = StateGraph(AgentState)

# 2. Add nodes (The 4 Specialist Agents + Combiner)
orchestrator_workflow.add_node("router", router_node)
orchestrator_workflow.add_node("planning", planning_node)
orchestrator_workflow.add_node("manufacturing", manufacturing_node)
orchestrator_workflow.add_node("scheme", scheme_node)
orchestrator_workflow.add_node("research", research_node)
# orchestrator_workflow.add_node("judge", judge_node)
orchestrator_workflow.add_node("finalize", finalize_node)


def _get_required_set(state: AgentState) -> set:
    req = state.get("required_agents")
    if req is None:
        return {"planning", "manufacturing", "scheme", "research"}
    return set(req)


def route_after_router(state: AgentState):
    req = _get_required_set(state)
    if not req:
        return "finalize"
    if "planning" in req:
        return "planning"
    if "manufacturing" in req:
        return "manufacturing"
    if "scheme" in req:
        return "scheme"
    if "research" in req:
        return "research"
    return "finalize"


def route_after_planning(state: AgentState):
    req = _get_required_set(state)
    if "manufacturing" in req:
        return "manufacturing"
    if "scheme" in req:
        return "scheme"
    if "research" in req:
        return "research"
    return "finalize"


def route_after_manufacturing(state: AgentState):
    req = _get_required_set(state)
    if "scheme" in req:
        return "scheme"
    if "research" in req:
        return "research"
    return "finalize"


def route_after_scheme(state: AgentState):
    req = _get_required_set(state)
    if "research" in req:
        return "research"
    return "finalize"


# 3. Define the sequential (series) routing / workflow
orchestrator_workflow.set_entry_point("router")

orchestrator_workflow.add_conditional_edges(
    "router",
    route_after_router,
    {
        "planning": "planning",
        "manufacturing": "manufacturing",
        "scheme": "scheme",
        "research": "research",
        "finalize": "finalize",
    }
)

orchestrator_workflow.add_conditional_edges(
    "planning",
    route_after_planning,
    {
        "manufacturing": "manufacturing",
        "scheme": "scheme",
        "research": "research",
        "finalize": "finalize",
    }
)

orchestrator_workflow.add_conditional_edges(
    "manufacturing",
    route_after_manufacturing,
    {
        "scheme": "scheme",
        "research": "research",
        "finalize": "finalize",
    }
)

orchestrator_workflow.add_conditional_edges(
    "scheme",
    route_after_scheme,
    {
        "research": "research",
        "finalize": "finalize",
    }
)

orchestrator_workflow.add_edge("research", "finalize")
orchestrator_workflow.add_edge("finalize", END)
# 4. Compile the Graph

# We don't compile with MemorySaver globally anymore.
# We will compile it dynamically in run_orchestrator using the async context manager.
# orchestrator_workflow.compile()

pool: AsyncConnectionPool | None = None
_fallback_memory_saver = MemorySaver()

async def get_orchestrator_checkpointer():
    global pool, _fallback_memory_saver
    db_url = getattr(settings, "DATABASE_URL", "") or ""
    if db_url.startswith("postgresql") or db_url.startswith("postgres"):
        try:
            from core.dns_fallback import resolve_db_hostaddr
            resolved_db_url = resolve_db_hostaddr(db_url)
            if pool is not None and getattr(pool, "closed", False):
                pool = None
            if pool is None:
                pool = AsyncConnectionPool(
                    conninfo=resolved_db_url,
                    max_size=10,
                    max_idle=30.0,
                    max_lifetime=180.0,
                    check=AsyncConnectionPool.check_connection,
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
            return _fallback_memory_saver
    return _fallback_memory_saver


async def run_orchestrator(query: str, thread_id: str = "default_session"):
    """
    Entry Point for standalone multi-agent factory planning.
    Note: Previous memory is not passed to the planner; memory is reserved for the Chat feature.
    """
    inputs = {
        "user_query": query,
        "semantic_context": "",
        "use_history": False,
        "messages": [],
    }

    checkpointer = await get_orchestrator_checkpointer()
    graph = orchestrator_workflow.compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": thread_id}}

    current_state = await graph.aget_state(config)

    if current_state.values.get("messages"):
        pass

    result = await graph.ainvoke(inputs, config=config)
    
    final_report = result.get("final_report")
    if isinstance(final_report, dict):
        save_workflow_to_vector_db(user_id=thread_id, query=query, final_report=final_report)

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
def save_factory_plan_to_db(user_id: str, query: str, final_report: dict):
    """Saves the final generated factory plan into the relational database table."""
    if not user_id or not final_report:
        return None
    from core.database import SessionLocal, FallbackSessionLocal
    from models.plan import FactoryPlan
    import uuid
    import json
    
    db = None
    try:
        try:
            db = SessionLocal()
        except Exception:
            db = FallbackSessionLocal()
            
        plan_id = f"plan_{uuid.uuid4().hex[:12]}"
        plan_record = FactoryPlan(
            id=plan_id,
            user_id=str(user_id),
            query=query.strip(),
            title=query.strip()[:80],
            plan_data=json.dumps({"final_report": final_report}),
        )
        db.add(plan_record)
        db.commit()
        db.refresh(plan_record)
        print(f"[INFO] Saved factory plan '{plan_id}' to database for user '{user_id}'.")
        return plan_record
    except Exception as e:
        print(f"[WARNING] Failed to save factory plan to database: {e}")
        return None
    finally:
        if db:
            db.close()


async def run_orchestrator_stream(query: str, thread_id: str = "default_session"):
    """
    Streaming Entry Point to trigger the AI brain and yield Server-Sent Events.
    Note: As per requirements, previous memory is NOT passed to the orchestrator;
    memory is reserved exclusively for the Chat feature.
    """
    checkpointer = await get_orchestrator_checkpointer()
    graph = orchestrator_workflow.compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": thread_id}}

    inputs = {
        "user_query": query,
        "semantic_context": "",
        "use_history": False,
        "messages": [],
        "planning_result": None,
        "manufacturing_result": None,
        "scheme_result": None,
        "research_result": None,
        "judge_result": None,
        "final_report": None,
    }
    
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
        # Save generated workflow associated with this user_id for later Chatbot retrieval
        save_workflow_to_vector_db(user_id=thread_id, query=query, final_report=final_report)
        plan_record = save_factory_plan_to_db(user_id=thread_id, query=query, final_report=final_report)
        plan_id = plan_record.id if plan_record else None
        
        yield f"data: {json.dumps({'type': 'final_report', 'data': {'id': plan_id, 'final_report': final_report}})}\n\n"


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
        query = final_state.values.get("user_query", "Resumed query")
        plan_id = None
        if isinstance(final_report, dict):
            save_workflow_to_vector_db(user_id=thread_id, query=query, final_report=final_report)
            plan_record = save_factory_plan_to_db(user_id=thread_id, query=query, final_report=final_report)
            plan_id = plan_record.id if plan_record else None
        
        yield f"data: {json.dumps({'type': 'final_report', 'data': {'id': plan_id, 'final_report': final_report}})}\n\n"

