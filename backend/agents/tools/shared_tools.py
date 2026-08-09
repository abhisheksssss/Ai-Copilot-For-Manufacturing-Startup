import io
import sys
import math
import traceback
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class DocumentInput(BaseModel):
    file_path: str = Field(description="Path or URL to the document (PDF, DOCX, Markdown)")

class CalculatorInput(BaseModel):
    expression: str = Field(description="Math expression to evaluate (e.g., '2000000 * 0.6')")

class MemoryInput(BaseModel):
    key: str = Field(description="The key to store or retrieve data")
    value: str = Field(description="The value to store (leave empty for retrieval)", default="")

class ReportInput(BaseModel):
    content: str = Field(description="The markdown content to generate a report from")
    format: str = Field(description="The format (PDF, DOCX, PPT)", default="PDF")

class CitationInput(BaseModel):
    source_id: str = Field(description="The ID of the government document or manual to cite")

class PythonSandboxInput(BaseModel):
    code: str = Field(
        description="Python code to execute for business, financial, engineering, or mathematical calculations. "
                    "You MUST use print() statements to display output results."
    )



@tool("document_reader", args_schema=DocumentInput)
def document_reader(file_path: str) -> str:
    """Reads content from PDFs, DOCX, or Excel files for RAG."""
    print("\n[TOOL CALLED] -> document_reader")
    # In Phase 2, this will use PyMuPDF or Docling to extract real text.
    return f"Extracted text content from {file_path}"


@tool("calculator", args_schema=CalculatorInput)
def calculator(expression: str) -> str:
    """Performs financial calculations like ROI, EMI, break-even, and investment."""
    print("\n[TOOL CALLED] -> calculator")
    try:
        # Note: eval is used here for simplicity in MVP. Use a safer math parser in production!
        result = eval(expression, {"__builtins__": None}, {})
        return str(result)
    except Exception as e:
        return f"Error calculating {expression}: {str(e)}"


# Simple in-memory dict to act as short-term memory across agent nodes
_project_memory = {}

@tool("memory_tool", args_schema=MemoryInput)
def memory_tool(key: str, value: str = "") -> str:
    """Stores or retrieves project context (Budget, Industry, Location) across agents."""
    print("\n[TOOL CALLED] -> memory_tool")
    if value:
        _project_memory[key] = value
        return f"Stored '{value}' under '{key}'."
    else:
        return _project_memory.get(key, f"No memory found for '{key}'.")


# @tool("report_generator", args_schema=ReportInput)
# def report_generator(content: str, format: str = "PDF") -> str:
#     """Converts the final merged markdown into a downloadable PDF/DOCX/PowerPoint."""
#     print("\n[TOOL CALLED] -> report_generator")
#     return f"Successfully generated {format} report. (Download link placeholder)"


@tool("citation_engine", args_schema=CitationInput)
def citation_engine(source_id: str) -> str:
    """Generates official citations back to government documents and industrial manuals."""
    print("\n[TOOL CALLED] -> citation_engine")
    return f"[Citation: Official Source Document {source_id}, 2024]"

from langgraph.types import interrupt

class AskHumanInput(BaseModel):
    question: str = Field(description="The clarifying question to ask the user.")

@tool("ask_human", args_schema=AskHumanInput)
def ask_human(question: str) -> str:
    """Use this tool to ask the user a clarifying question when you are missing critical information. Execution will pause until the user answers."""
    print(f"\n[TOOL CALLED] -> ask_human: {question}")
    answer = interrupt({"action": "ask_human", "question": question})
    return f"User answered: {answer}"


@tool("python_code_sandbox", args_schema=PythonSandboxInput)
def python_code_sandbox(code: str) -> str:
    """
    Executes Python code in a secure sandbox to perform complex calculations 
    such as NPV, IRR, CAPEX/OPEX modeling, loan amortization (EMI), break-even analysis, 
    unit economics, power load requirements, and production throughput.
    Always use print() to output results.
    """
    print("\n[TOOL CALLED] -> python_code_sandbox")
     
    #capture standard stdout
    buffer=io.StringIO()
    old_stdout=sys.stdout
    sys.stdout=buffer
    
    safe_globals = {
        "__builtins__": {
            "print": print,
            "range": range,
            "len": len,
            "int": int,
            "float": float,
            "str": str,
            "list": list,
            "dict": dict,
            "set": set,
            "tuple": tuple,
            "sum": sum,
            "min": min,
            "max": max,
            "abs": abs,
            "round": round,
            "enumerate": enumerate,
            "zip": zip,
            "bool": bool,
        },
        "math": math
    }
    safe_locals = {}

    try:
            exec(code, safe_globals, safe_locals)
            output = buffer.getvalue()
            if output.strip():
                return f"Sandbox Output:\n{output.strip()}"
            else:
                return "Execution completed successfully (no print output detected). Please ensure you call print() to view results."
    except Exception as e:
            return f"Error executing Python code:\n{str(e)}"
    finally:
            sys.stdout = old_stdout




from .planning_tools import industrial_land_search

shared_tools_list = [
    document_reader,
    calculator,
    memory_tool,
    python_code_sandbox,
    industrial_land_search,
    # report_generator,
    citation_engine,
    ask_human
]


