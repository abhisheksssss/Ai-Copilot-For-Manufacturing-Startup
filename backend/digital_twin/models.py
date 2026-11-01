"""
Pydantic data models for the AI Factory Digital Twin.
"""
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────────────────────────────────────
# 1. FACTORY CONFIGURATION (extracted from user query by LLM)
# ─────────────────────────────────────────────────────────────────────────────

class MachineModel(BaseModel):
    name: str = Field(description="Machine name, e.g. 'PCB Pick & Place Machine'")
    quantity: int = Field(default=1, ge=1, description="Number of machines in parallel")
    capacity_per_hour: float = Field(default=50.0, gt=0, description="Nominal units per hour per machine")
    processing_time_min: float = Field(default=1.2, gt=0, description="Cycle time in minutes per unit")
    power_kw: float = Field(default=10.0, ge=0, description="Rated power consumption per machine in kW")
    cost_inr: float = Field(default=500000.0, ge=0, description="Cost per machine in INR")
    machine_type: str = Field(
        default="box",
        description="Visual shape: 'box', 'cylinder', 'conveyor'"
    )
    oee_percent: float = Field(default=85.0, ge=10.0, le=100.0)
    downtime_percent: float = Field(default=5.0, ge=0.0, le=80.0)
    setup_time_min: float = Field(default=20.0, ge=0.0, le=240.0)
    maintenance_hours_per_month: float = Field(default=4.0, ge=0.0)


class ProcessStep(BaseModel):
    name: str = Field(description="Process step name, e.g. 'SMT Soldering'")
    sequence: int = Field(description="Order in production flow, starting from 1")
    machine: MachineModel = Field(description="Machine used in this step")
    workers_required: int = Field(default=2, ge=1, description="Total workers needed at this station")
    min_operators_per_shift: int = Field(default=1, ge=1)
    zone_type: str = Field(
        default="production",
        description="'warehouse', 'production', 'testing', 'qc', 'packaging', 'dispatch', 'office'"
    )
    area_sqft: float = Field(default=2000.0, ge=200.0)
    yield_percent: float = Field(default=98.0, ge=50.0, le=100.0)
    scrap_percent: float = Field(default=2.0, ge=0.0, le=50.0)
    buffer_capacity_units: int = Field(default=500, ge=0)
    rework_percent: float = Field(default=0.0, ge=0.0, le=40.0)
    rework_to_step: Optional[int] = Field(default=None)

    @field_validator("scrap_percent", mode="after")
    @classmethod
    def sync_scrap_with_yield(cls, v: float, info) -> float:
        yield_val = info.data.get("yield_percent", 98.0)
        implied_loss = max(0.0, round(100.0 - yield_val, 2))
        return implied_loss if abs(v - implied_loss) > 0.5 else v


class FactoryConfig(BaseModel):
    product: str = Field(description="Product being manufactured")
    target_monthly_units: int = Field(default=50000, gt=0)
    operating_days_per_month: int = Field(default=26, ge=1, le=31)
    shifts_per_day: int = Field(default=2, ge=1, le=3)
    hours_per_shift: float = Field(default=8.0, gt=0, le=12.0)
    location: str = Field(default="India")
    budget_inr: float = Field(default=10_000_000.0, gt=0)
    selling_price_per_unit: float = Field(default=2000.0, gt=0)
    raw_material_cost_ratio: float = Field(default=0.45, gt=0.05, lt=0.95)
    labour_cost_per_worker_month_inr: float = Field(default=18000.0, gt=0)
    power_cost_per_kwh_inr: float = Field(default=8.0, gt=0)
    processes: list[ProcessStep] = Field(default_factory=list)
    total_area_sqft: float = Field(default=30000.0, gt=0)
    warehouse_area_sqft: float = Field(default=8000.0, ge=0)
    office_area_sqft: float = Field(default=2000.0, ge=0)

    @property
    def daily_hours(self) -> float:
        return self.shifts_per_day * self.hours_per_shift

    @property
    def target_daily_units(self) -> float:
        return self.target_monthly_units / max(self.operating_days_per_month, 1)


# ─────────────────────────────────────────────────────────────────────────────
# 2. SIMULATION RESULT
# ─────────────────────────────────────────────────────────────────────────────

class StepCapacity(BaseModel):
    step_name: str
    sequence: int
    capacity_per_hour: float
    theoretical_capacity_per_day: float
    effective_runtime_hours_per_day: float
    actual_units_processed_per_day: float
    actual_good_output_per_day: float
    quality_adjusted_output_per_day: float
    capacity_per_day: float
    capacity_per_month: float
    utilization_percent: float
    yield_percent: float
    downtime_percent: float
    oee_percent: float
    takt_time_sec: float = Field(default=0.0, description="Required seconds per unit to meet target")
    cycle_time_sec: float = Field(default=0.0, description="Effective station cycle time in seconds")
    line_state: str = Field(default="balanced", description="'bottleneck', 'starved', 'constrained', or 'balanced'")
    is_bottleneck: bool
    machine_count: int
    workers: int


class SimulationResult(BaseModel):
    effective_throughput_per_day: float
    effective_throughput_per_month: float
    target_met: bool
    production_gap: float
    bottleneck_step: str
    bottleneck_capacity_per_day: float
    step_capacities: list[StepCapacity]
    total_workers: int
    total_power_kw: float
    estimated_monthly_power_cost_inr: float
    overall_yield_percent: float = Field(default=100.0)
    first_pass_yield_percent: float = Field(default=100.0)
    monthly_scrap_units: float = Field(default=0.0)
    monthly_rework_units: float = Field(default=0.0)
    monthly_input_units_required: float = Field(default=0.0)
    capacity_utilization_percent: float = Field(default=0.0)
    plant_takt_time_sec: float = Field(default=0.0)
    line_balance_efficiency_percent: float = Field(default=0.0)
    optimization_suggestions: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# 3. FINANCIAL SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

class FinancialSummary(BaseModel):
    total_capex_inr: float
    budget_variance_inr: float = Field(default=0.0, description="Positive = under budget, Negative = over budget")
    within_budget: bool = Field(default=True)
    machine_cost_inr: float
    civil_construction_inr: float
    misc_infra_inr: float
    working_capital_inr: float
    monthly_opex_inr: float
    labour_cost_monthly_inr: float
    power_cost_monthly_inr: float
    raw_material_cost_monthly_inr: float
    maintenance_cost_monthly_inr: float
    inventory_carrying_cost_monthly_inr: float
    qc_and_scrap_cost_monthly_inr: float
    depreciation_monthly_inr: float
    monthly_revenue_inr: float
    monthly_ebitda_inr: float = Field(default=0.0)
    monthly_profit_inr: float
    gross_margin_percent: float
    ebitda_margin_percent: float = Field(default=0.0)
    net_margin_percent: float = Field(default=0.0)
    unit_cost_inr: float = Field(default=0.0)
    unit_profit_inr: float = Field(default=0.0)
    break_even_months: float
    annual_roi_percent: float
    conservative: dict
    balanced: dict
    aggressive: dict


# ─────────────────────────────────────────────────────────────────────────────
# 4. THREE.JS SCENE DESCRIPTOR
# ─────────────────────────────────────────────────────────────────────────────

class SceneZone(BaseModel):
    id: str
    name: str
    position: list[float]
    size: list[float]
    color: str
    emissive_color: str = Field(default="#000000")
    is_bottleneck: bool = Field(default=False)
    zone_type: str
    metadata: dict = Field(default_factory=dict)


class SceneMachine(BaseModel):
    id: str
    name: str
    zone_id: str
    position: list[float]
    size: list[float]
    color: str
    shape: str = Field(default="box", description="'box', 'cylinder', or 'conveyor'")
    quantity: int = Field(default=1)
    metadata: dict = Field(default_factory=dict)


class SceneFlow(BaseModel):
    id: str
    from_zone: str
    to_zone: str
    label: str
    is_bottleneck_flow: bool = Field(default=False)
    flow_type: str = Field(default="normal", description="'normal', 'bottleneck', or 'rework'")


class SceneLabel(BaseModel):
    id: str
    text: str
    position: list[float]
    font_size: float = Field(default=0.5)
    color: str = Field(default="#FFFFFF")


class SceneDescriptor(BaseModel):
    zones: list[SceneZone]
    machines: list[SceneMachine]
    flows: list[SceneFlow]
    labels: list[SceneLabel] = Field(default_factory=list)
    factory_width: float
    factory_depth: float
    camera_position: list[float] = Field(default=[30, 25, 40])
    camera_target: list[float] = Field(default=[0, 0, 0])


# ─────────────────────────────────────────────────────────────────────────────
# 5. COMPLETE DIGITAL TWIN RESPONSE
# ─────────────────────────────────────────────────────────────────────────────

class DigitalTwinResponse(BaseModel):
    query: str
    config: FactoryConfig
    simulation: SimulationResult
    financials: FinancialSummary
    scene: SceneDescriptor
    summary_text: str