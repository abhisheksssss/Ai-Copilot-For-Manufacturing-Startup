from langchain_core.tools import tool
from pydantic import BaseModel, Field
from typing import Optional

from models.compliance import ComplianceAssessmentRequest
from services.compliance_service import run_compliance_assessment


class ComplianceCheckInput(BaseModel):
    industry_type: str = Field(
        ...,
        description="Type of manufacturing or product (e.g., 'EV battery assembly', 'Electroplating', 'Food processing', 'Bakery')"
    )
    state: str = Field(
        default="Maharashtra",
        description="Indian state where factory will be set up (e.g. 'Gujarat', 'Tamil Nadu', 'Maharashtra', 'Karnataka')"
    )
    monthly_power_kwh: Optional[float] = Field(
        default=8000.0,
        description="Estimated electricity usage in kWh/month"
    )
    workforce_count: Optional[int] = Field(
        default=25,
        description="Expected number of factory employees / workers"
    )
    built_up_area_sqft: Optional[float] = Field(
        default=15000.0,
        description="Factory shed built-up floor area in sq. ft"
    )
    has_chemical_treatment: Optional[bool] = Field(
        default=False,
        description="True if process involves electroplating, pickling, acids, or toxic chemical washes"
    )


@tool(args_schema=ComplianceCheckInput)
def check_factory_environmental_compliance(
    industry_type: str,
    state: str = "Maharashtra",
    monthly_power_kwh: float = 8000.0,
    workforce_count: int = 25,
    built_up_area_sqft: float = 15000.0,
    has_chemical_treatment: bool = False
) -> str:
    """
    Evaluates statutory government environmental clearances (SPCB CTE/CTO, DISH Factory License, Fire NOC),
    detects CPCB Pollution Category (Red, Orange, Green, White), and calculates Scope 1/2 carbon footprint
    along with Rooftop Solar payback ROI.
    """
    req = ComplianceAssessmentRequest(
        custom_industry_text=industry_type,
        state=state,
        monthly_power_kwh=monthly_power_kwh,
        workforce_count=workforce_count,
        built_up_area_sqft=built_up_area_sqft,
        has_chemical_treatment=has_chemical_treatment
    )

    res = run_compliance_assessment(req)

    permits_summary = "\n".join(
        [f"  - {p.name} [{p.category}] | Fee: ~₹{p.estimated_fee_inr:,.0f} | Lead Time: {p.lead_time_days} days\n    Req: {', '.join(p.documents_required[:3])}" for p in res.required_permits]
    )

    return f"""### Environmental & Statutory Compliance Report for {res.matched_sector.title}
- **Location:** {state}
- **CPCB Classification:** {res.spcb_category} Category (Pollution Index: {res.pollution_index_score}/100)
- **Rationale:** {res.category_rationale}
- **Consent Validity:** {res.matched_sector.validity_period}
- **ETP/APCD Mandatory:** {'Yes' if res.matched_sector.etp_apcd_mandatory else 'No (Standard safeguards only)'}

#### Required Statutory Permits & Clearances:
{permits_summary}

#### Carbon Footprint & Energy Optimization:
- **Monthly Carbon Footprint:** {res.carbon_metrics.scope_1_kg_co2_monthly + res.carbon_metrics.scope_2_kg_co2_monthly:,.1f} kg CO2e
- **Annual GHG Emissions:** {res.carbon_metrics.total_carbon_tons_annual} Metric Tons CO2e
- **Rooftop Solar Recommendation:** {res.solar_projection.recommended_capacity_kwp} kWp on {res.solar_projection.usable_roof_area_sqft:,.0f} sq.ft roof
- **Estimated Solar CAPEX:** ₹{res.solar_projection.estimated_capex_inr:,.0f}
- **Annual Electricity Bill Savings:** ₹{res.solar_projection.annual_savings_inr:,.0f} / year
- **Simple Payback Period:** {res.solar_projection.payback_period_years} Years (Lifetime 25-yr net savings: ₹{res.solar_projection.lifetime_25yr_savings_inr:,.0f})
"""
