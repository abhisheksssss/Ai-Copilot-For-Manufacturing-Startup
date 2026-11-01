from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class AIComplianceQueryRequest(BaseModel):
    query: str = Field(
        ...,
        description="Natural language query describing the factory (e.g. '500 units/day EV battery plant in Pune with 25 workers')"
    )


class ComplianceAssessmentRequest(BaseModel):
    industry_slug: Optional[str] = Field(
        None,
        description="Selected CPCB sector slug from master list (e.g., 'manufacturing-of-automobiles-integrated-facilities')"
    )
    custom_industry_text: Optional[str] = Field(
        None,
        description="User free-form query or novel product name if not in list"
    )
    state: str = Field(default="Maharashtra", description="State in India where plant is located")
    monthly_power_kwh: float = Field(default=8500.0, description="Monthly grid electricity usage in kWh")
    monthly_diesel_liters: float = Field(default=250.0, description="Monthly diesel consumption for backup DG sets (Liters)")
    workforce_count: int = Field(default=25, description="Total expected employees / factory workers")
    built_up_area_sqft: float = Field(default=15000.0, description="Factory shed built-up area in sq. ft")
    monthly_production_units: int = Field(default=1000, description="Finished product units manufactured per month")
    has_chemical_treatment: bool = Field(default=False, description="Whether process involves acids, plating, or hazardous chemicals")
    has_effluent_discharge: bool = Field(default=False, description="Whether process generates industrial trade effluent")
    has_steam_boiler: bool = Field(default=False, description="Whether high-pressure steam boiler is used")


class PermitItem(BaseModel):
    id: str
    name: str
    authority: str
    category: str  # "Mandatory Pre-Construction", "Pre-Commissioning", "Operational", "Safety"
    mandatory: bool
    lead_time_days: int
    estimated_fee_inr: float
    description: str
    documents_required: List[str]


class CarbonMetrics(BaseModel):
    scope_1_kg_co2_monthly: float
    scope_2_kg_co2_monthly: float
    total_carbon_tons_annual: float
    emissions_per_unit_kg: float
    scope_1_breakdown: str
    scope_2_breakdown: str


class SolarProjection(BaseModel):
    recommended_capacity_kwp: float
    estimated_capex_inr: float
    annual_generation_kwh: float
    annual_savings_inr: float
    payback_period_years: float
    annual_carbon_offset_tons: float
    lifetime_25yr_savings_inr: float
    usable_roof_area_sqft: float


class SectorSummary(BaseModel):
    slug: str
    title: str
    category: str
    pollution_index_score: float
    pollution_index_range: str
    cpcb_serial_no: str
    requires_cte: bool
    requires_cto: bool
    validity_period: str
    etp_apcd_mandatory: bool
    tags: List[str]


class ComplianceAssessmentResponse(BaseModel):
    matched_sector: SectorSummary
    spcb_category: str  # "Red" | "Orange" | "Green" | "White" | "Blue"
    pollution_index_score: float
    category_rationale: str
    star_rating_eligible: bool
    required_permits: List[PermitItem]
    carbon_metrics: CarbonMetrics
    solar_projection: SolarProjection
    compliance_roadmap: List[str]
    sector_guidelines_markdown: Optional[str] = None
