import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
import traceback
import json
import time

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table

from core.config import settings
from agents.orchestrator import run_orchestrator
from fastapi.middleware.cors import CORSMiddleware

from fastapi import FastAPI, Depends
from core.database import engine, Base
from api.auth_router import router as auth_router
from core.auth import get_current_user_id, require_admin
from models.user import User
from fastapi.responses import StreamingResponse
from agents.orchestrator import run_orchestrator_stream, resume_orchestrator_stream


Base.metadata.create_all(bind=engine)

console = Console()

app = FastAPI(title=settings.PROJECT_NAME)

origins = [
    "http://localhost:3000",  # Next.js
    "http://localhost:3001",  # Next.js fallback
    "http://localhost:5173",  # Vite
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "project": settings.PROJECT_NAME
    }

@app.get("/api/admin/dashboard")
def admin_dashboard(user: User = Depends(require_admin)):
    return {
        "message": f"Welcome Admin {user.email}!",
        "status": "success",
        "role": user.role
    }


class PlanRequest(BaseModel):
    query: str


def show_agent(agent_name: str, report: dict):

    console.rule(f"[bold cyan]{agent_name}")

    if isinstance(report, dict):
        text = report.get("report", json.dumps(report, indent=2))
        
        # Google Gemini via LangChain sometimes returns a list of dicts for .content
        if isinstance(text, list):
            extracted = []
            for block in text:
                if isinstance(block, dict) and "text" in block:
                    extracted.append(block["text"])
                elif isinstance(block, str):
                    extracted.append(block)
            text = "\n".join(extracted) if extracted else str(text)
            
    else:
        text = str(report)

    console.print(
        Panel.fit(
            str(text),
            border_style="green",
            title=agent_name
        )
    )


@app.post("/api/plan")
async def generate_business_plan(
    request: PlanRequest,
    user_id: str = Depends(get_current_user_id)
):




    start = time.perf_counter()

    try:

        result = await run_orchestrator(request.query, thread_id=user_id)

        duration = time.perf_counter() - start

        console.clear()

        console.print(
            Panel.fit(
                "[bold cyan]AI Manufacturing Copilot[/bold cyan]\n"
                "[green]Multi-Agent Business Orchestrator[/green]",
                border_style="bright_blue"
            )
        )

        console.print()

        console.print(
            Panel(
                request.query,
                title="📥 User Query",
                border_style="yellow"
            )
        )

        if result.get("messages"):

            table = Table(title="🤖 Agent Execution Status")

            table.add_column("Status", style="green", justify="center")
            table.add_column("Message", style="white")

            for msg in result["messages"]:
                table.add_row("✅", msg)

            console.print(table)

        final = result.get("final_report", {})

        show_agent(
            "🧠 Planning Agent",
            final.get("planning", {})
        )

        show_agent(
            "🏭 Manufacturing Agent",
            final.get("manufacturing", {})
        )

        show_agent(
            "💰 Scheme Agent",
            final.get("schemes", {})
        )

        show_agent(
            "🔍 Research Agent",
            final.get("research", {})
        )

        console.print(Rule(style="cyan"))

        summary = Table(title="📊 Execution Summary")

        summary.add_column("Metric", style="cyan")
        summary.add_column("Value", style="green")

        summary.add_row("Execution Time", f"{duration:.2f} sec")
        summary.add_row("Agents", "4")
        summary.add_row("Status", "Completed ✅")

        console.print(summary)

        console.print(Rule("[bold green]Final JSON"))

        syntax = Syntax(
            json.dumps(result, indent=2),
            "json",
            theme="monokai",
            line_numbers=False
        )

        console.print(syntax)

        console.print(
            Panel.fit(
                "[bold green]✓ Request Completed Successfully[/bold green]",
                border_style="green"
            )
        )

        return result

    except Exception as e:

        console.print(
            Panel.fit(
                "[bold red]❌ ORCHESTRATOR FAILED[/bold red]",
                border_style="red"
            )
        )

        console.print_exception()

        raise HTTPException(
            status_code=500,
            detail=f"Internal Server Error: {str(e)}"
        )

@app.post("/api/chat/stream")
async def chat_stream(
    request: PlanRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Streams the chatbot's ReAct loop directly. The chatbot decides which specialist
    tools (planning, manufacturing, scheme, research) to invoke itself.
    No orchestrator router graph is involved.
    """
    return StreamingResponse(
        run_chatbot_stream(request.query, thread_id=user_id),
        media_type="text/event-stream"
    )

class ResumeRequest(BaseModel):
    answer: str

@app.post("/api/chat/resume")
async def chat_resume(
    request: ResumeRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Handles follow-up messages in the chatbot conversation.
    """
    return StreamingResponse(
        resume_chatbot_stream(request.answer, thread_id=user_id),
        media_type="text/event-stream"
    )

@app.post("/api/plan/stream")
async def plan_stream(
    request: PlanRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Streams the Multi-Agent Business Plan Orchestrator graph execution.
    Determines required specialist agents (planning, manufacturing, scheme, research)
    and streams live events + final multi-agent reports.
    """
    return StreamingResponse(
        run_orchestrator_stream(request.query, thread_id=user_id),
        media_type="text/event-stream"
    )

@app.post("/api/plan/resume")
async def plan_resume(
    request: ResumeRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Resumes an interrupted Multi-Agent Orchestrator graph execution with user feedback.
    """
    return StreamingResponse(
        resume_orchestrator_stream(request.answer, thread_id=user_id),
        media_type="text/event-stream"
    )

# ─────────────────────────────────────────────────────────────────────────────
# DIGITAL TWIN ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

class DigitalTwinRequest(BaseModel):
    query: str

class WhatIfRequest(BaseModel):
    query: str
    modification: str = Field(default="", description="What-if modification, e.g. 'increase production to 100k/month'")


async def _stream_digital_twin(query: str):
    """
    SSE stream for the Digital Twin agent.
    Emits progress events then the final JSON payload.
    """
    import json as _json

    STAGES = [
        ("parsing",    "🔍 Parsing factory requirements..."),
        ("simulating", "⚙️ Running production simulation..."),
        ("financial",  "💰 Computing financial projections..."),
        ("scene",      "🏭 Building 3D factory scene..."),
        ("summary",    "📝 Generating insights..."),
    ]

    # Emit all progress stages
    for stage_id, stage_msg in STAGES:
        yield f"data: {_json.dumps({'type': 'progress', 'stage': stage_id, 'message': stage_msg})}\n\n"

    try:
        result = await run_digital_twin_agent(query)
        yield f"data: {_json.dumps({'type': 'digital_twin_result', 'data': result})}\n\n"
    except Exception as e:
        console.print_exception()
        yield f"data: {_json.dumps({'type': 'error', 'message': str(e)})}\n\n"


async def _stream_what_if(query: str, modification: str):
    """
    SSE stream for what-if analysis — re-runs the agent with the modification appended.
    """
    import json as _json
    enriched_query = f"{query}\n\nWhat-if modification: {modification}"

    yield f"data: {_json.dumps({'type': 'progress', 'stage': 'what_if', 'message': f'🔄 Simulating: {modification}'})}\n\n"

    try:
        result = await run_digital_twin_agent(enriched_query)
        yield f"data: {_json.dumps({'type': 'digital_twin_result', 'data': result})}\n\n"
    except Exception as e:
        yield f"data: {_json.dumps({'type': 'error', 'message': str(e)})}\n\n"


# @app.post("/api/digital-twin/generate")
# async def digital_twin_generate(
#     request: DigitalTwinRequest,
#     user_id: str = Depends(get_current_user_id),
# ):
#     """
#     Generate an AI Factory Digital Twin from a natural-language query.
#     Streams SSE progress events, then emits the complete twin JSON.
#     """
#     return StreamingResponse(
#         _stream_digital_twin(request.query),
#         media_type="text/event-stream",
#     )


# @app.post("/api/digital-twin/what-if")
# async def digital_twin_what_if(
#     request: WhatIfRequest,
#     user_id: str = Depends(get_current_user_id),
# ):
#     """
#     Run a what-if scenario on an existing factory configuration.
#     Re-runs the full Digital Twin pipeline with the modification applied.
#     """
#     return StreamingResponse(
#         _stream_what_if(request.query, request.modification),
#         media_type="text/event-stream",
#     )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
