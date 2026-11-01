import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime
from core.database import Base


class FactoryPlan(Base):
    __tablename__ = "factory_plans"

    id = Column(
        String(64),
        primary_key=True,
        index=True,
        default=lambda: f"plan_{uuid.uuid4().hex[:12]}"
    )
    user_id = Column(String(64), index=True, nullable=False)
    query = Column(Text, nullable=False)
    title = Column(String(255), nullable=True)
    plan_data = Column(Text, nullable=False)  # Stores JSON serialized string
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
