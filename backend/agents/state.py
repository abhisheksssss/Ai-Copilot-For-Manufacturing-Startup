from typing import TypedDict, List, Annotated
import operator


class AgentState(TypedDict):
    user_query:str
    semantic_context: str
    use_history: bool

    current_agent:str

    required_agents:List[str]

    # Store outputs from specialist agents
    planning_result: dict | None
    manufacturing_result: dict | None
    scheme_result: dict | None
    research_result: dict | None
    judge_result: dict | None

     # Log of what happened
    messages: Annotated[List[str], operator.add]

    final_report:dict| None
