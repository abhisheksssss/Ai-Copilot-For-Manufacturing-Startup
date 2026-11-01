from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.auth import get_current_user_id
from services.industry_location_service import search_industry_locations


router = APIRouter(prefix="/api/locations", tags=["Industrial locations"])


class LocationSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300, description="Natural-language industry location request")
    limit: int = Field(default=5, ge=1, le=10)
    enrich: bool = Field(default=True, description="Add live Google Places details when configured")


@router.post("/search")
async def search_locations(
    request: LocationSearchRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Find the best saved industrial parks and optionally enrich them with Google Places."""
    try:
        return await search_industry_locations(request.query, request.limit, request.enrich)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
