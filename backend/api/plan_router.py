import json
from datetime import datetime
from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.auth import get_current_user_id
from models.plan import FactoryPlan

router = APIRouter(prefix="/api/plans", tags=["plans"])


class PlanItemResponse(BaseModel):
    id: str
    query: str
    title: Optional[str] = None
    created_at: str
    plan_data: Any


@router.get("", response_model=List[PlanItemResponse])
def get_user_plans(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Fetch all previous factory plans created by the logged-in user from the database.
    """
    plans = (
        db.query(FactoryPlan)
        .filter(FactoryPlan.user_id == str(user_id))
        .order_by(FactoryPlan.created_at.desc())
        .limit(50)
        .all()
    )
    
    results = []
    for p in plans:
        try:
            parsed = json.loads(p.plan_data) if isinstance(p.plan_data, str) else p.plan_data
        except Exception:
            parsed = {}
            
        results.append(
            PlanItemResponse(
                id=p.id,
                query=p.query,
                title=p.title or p.query[:60],
                created_at=p.created_at.isoformat() if p.created_at else datetime.utcnow().isoformat(),
                plan_data=parsed,
            )
        )
    return results


@router.get("/{plan_id}", response_model=PlanItemResponse)
def get_plan_by_id(
    plan_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Fetch a single factory plan by its ID for the logged-in user.
    """
    p = (
        db.query(FactoryPlan)
        .filter(FactoryPlan.id == plan_id, FactoryPlan.user_id == str(user_id))
        .first()
    )
    if not p:
        raise HTTPException(status_code=404, detail="Factory plan not found")
        
    try:
        parsed = json.loads(p.plan_data) if isinstance(p.plan_data, str) else p.plan_data
    except Exception:
        parsed = {}
        
    return PlanItemResponse(
        id=p.id,
        query=p.query,
        title=p.title or p.query[:60],
        created_at=p.created_at.isoformat() if p.created_at else datetime.utcnow().isoformat(),
        plan_data=parsed,
    )


@router.delete("/{plan_id}")
def delete_plan(
    plan_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Delete a specific plan by ID for the logged-in user.
    """
    p = (
        db.query(FactoryPlan)
        .filter(FactoryPlan.id == plan_id, FactoryPlan.user_id == str(user_id))
        .first()
    )
    if not p:
        raise HTTPException(status_code=404, detail="Factory plan not found")
        
    db.delete(p)
    db.commit()
    return {"status": "success", "message": f"Plan {plan_id} deleted"}


@router.delete("")
def clear_all_plans(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Delete all previous factory plans for the logged-in user.
    """
    count = db.query(FactoryPlan).filter(FactoryPlan.user_id == str(user_id)).delete()
    db.commit()
    return {"status": "success", "message": f"Cleared {count} plans"}
