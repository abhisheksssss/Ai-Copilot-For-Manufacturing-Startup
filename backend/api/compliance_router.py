from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional

from models.compliance import (
    ComplianceAssessmentRequest,
    ComplianceAssessmentResponse,
    AIComplianceQueryRequest,
    SectorSummary
)
from services.compliance_service import (
    list_all_sectors,
    run_compliance_assessment,
    ai_parse_and_assess_compliance,
    load_master_sectors,
    read_sector_markdown
)
from core.auth import get_current_user_id

router = APIRouter(prefix="/api/compliance", tags=["ESG & Regulatory Compliance"])


@router.get("/sectors", response_model=List[SectorSummary])
def get_cpcb_sectors(
    q: Optional[str] = Query(None, description="Search term for industry name or tags"),
    category: Optional[str] = Query(None, description="Filter by category: Red, Orange, Green, White, Blue"),
    limit: int = Query(50, ge=1, le=200, description="Max results to return")
):
    """
    Search and retrieve CPCB official industrial sectors for dropdown autocomplete.
    """
    return list_all_sectors(query=q, category=category, limit=limit)


@router.post("/assess", response_model=ComplianceAssessmentResponse)
def assess_compliance(
    request: ComplianceAssessmentRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Run full ESG & Regulatory Compliance analysis:
    - SPCB Pollution Category (Red / Orange / Green / White / Blue) & Pollution Index score
    - Mandatory statutory permits & licenses (CTE, CTO, Factory License, Fire NOC, Boilers)
    - Scope 1 & Scope 2 carbon footprint per month and per product unit
    - Rooftop solar sizing, capital investment, annual power savings, and payback period
    - CPCB OKF technical guidance and statutory compliance roadmap
    """
    try:
        return run_compliance_assessment(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to assess compliance: {str(e)}")


@router.post("/ai-query", response_model=ComplianceAssessmentResponse)
def ai_query_compliance(
    request: AIComplianceQueryRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Accepts a natural language query describing a factory,
    extracts operational parameters, searches the 419 CPCB sectors knowledge base,
    and returns a tailored statutory & ESG assessment.
    """
    try:
        return ai_parse_and_assess_compliance(request.query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Compliance assessment failed: {str(e)}")


@router.get("/sectors/{slug}")
def get_sector_details(slug: str):
    """
    Fetch full CPCB OKF technical concept markdown and metadata for a specific sector.
    """
    sectors = load_master_sectors()
    if slug not in sectors:
        raise HTTPException(status_code=404, detail=f"Sector '{slug}' not found.")

    item = sectors[slug]
    rel_path = item.get("relative_path", "")
    markdown_content = read_sector_markdown(rel_path) if rel_path else None

    return {
        "metadata": item,
        "content_markdown": markdown_content
    }
