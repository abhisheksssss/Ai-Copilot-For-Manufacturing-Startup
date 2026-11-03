from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from core.auth import get_current_user_id
from services.industry_location_service import search_industry_locations, list_all_states


router = APIRouter(prefix="/api/locations", tags=["Industrial locations"])


class LocationSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500, description="Natural-language plant description or target location")
    limit: int = Field(default=5, ge=1, le=10)
    enrich: bool = Field(default=True, description="Add live Google Places details when configured")
    state_filter: Optional[str] = Field(default=None, description="Optional Indian state filter")
    mode: str = Field(default="auto", description="'auto' (smart detect), 'specific' (honor location only), or 'recommendation' (advisor mode)")


class LocationRecommendRequest(BaseModel):
    industry_description: str = Field(min_length=3, max_length=500, description="Product, technology, or plant specifications")
    state_preference: Optional[str] = Field(default=None, description="Optional target state preference (e.g. 'Maharashtra' or None for Pan-India)")
    limit: int = Field(default=5, ge=1, le=10)
    enrich: bool = Field(default=True, description="Add live Google Places details when configured")


@router.get("/states", response_model=List[str])
def get_all_states(user_id: str = Depends(get_current_user_id)):
    """Returns the list of 35 Indian States & UTs catalogued in the India Industrial Land Bank."""
    return list_all_states()


@router.post("/search")
async def search_locations(
    request: LocationSearchRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Finds best industrial parks from IILB catalogue.
    - If user entered a specific location: Returns matching parks in that region without unsolicited advice.
    - If no location mentioned: Recommends the #1 optimal industrial hub and explains why.
    """
    try:
        return await search_industry_locations(
            query=request.query,
            limit=request.limit,
            enrich=request.enrich,
            state_filter=request.state_filter,
            mode=request.mode
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/recommend")
async def recommend_optimal_location(
    request: LocationRecommendRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Dedicated AI Location Advisor endpoint: Analyzes plant requirements,
    recommends the #1 optimal industrial hub across 5 pillars, and returns the top verified IILB parks.
    """
    try:
        return await search_industry_locations(
            query=request.industry_description,
            limit=request.limit,
            enrich=request.enrich,
            state_filter=request.state_preference,
            mode="recommendation"
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
