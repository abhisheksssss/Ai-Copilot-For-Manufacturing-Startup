"""
Pydantic data models for the AI Factory Digital Twin.

These models describe:
- The factory configuration extracted from user queries
- Simulation results (capacity, bottlenecks, utilization)
- Financial projections
- 3D scene descriptors for Three.js rendering via react-three/fiber
"""
from pydantic import BaseModel, Field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# 1. FACTORY CONFIGURATION (extracted from user query by LLM)
# ─────────────────────────────────────────────────────────────────────────────

class MachineModel(BaseModel):
    name: str = Field(description="Machine name, e.g. 'PCB Assembly Machine'")
    quantity: int = Field(default=1, description="Number of machines")
    capacity_per_hour: float = Field(description="Units this machine can process per hour")
    processing_time_min: float = Field(description="Minutes to process one unit")
    power_kw: float = Field(default=10.0, description="Power consumption in kW")
    cost_inr: float = Field(default=500000.0, description="Cost per machine in INR")
    machine_type: str = Field(
        default="box",
        description="Visual shape: 'box', 'cylinder', 'conveyor'"
    )
    oee_percent: float = Field(
        default=85.0,
        description="Overall equipment effectiveness after speed/minor stoppage losses"
    )
    downtime_percent: float = Field(
        default=5.0,
        description="Share of planned production time lost to breakdowns and stoppages"
    )
    setup_time_min: float = Field(
        default=20.0,
        description="Changeover/setup time lost per shift in minutes"
    )
    maintenance_hours_per_month: float = Field(
        default=4.0,
        description="Planned maintenance hours per month for this machine type"
    )


class ProcessStep(BaseModel):
    name: str = Field(description="Process step name, e.g. 'PCB Assembly'")
    sequence: int = Field(description="Order in production flow, starting from 1")
    machine: MachineModel = Field(description="Machine used in this step")
    workers_required: int = Field(default=2, description="Total workers needed at this station")
    min_operators_per_shift: int = Field(
        default=1,
        description="Minimum operators required on each active shift"
    )
    zone_type: str = Field(
        default="production",
        description="Zone category: 'warehouse', 'production', 'testing', 'qc', 'packaging', 'dispatch', 'office'"
    )
    area_sqft: float = Field(default=2000.0, description="Floor area required in sq ft")
    yield_percent: float = Field(
        default=98.0,
        description="Good output percentage after this step"
    )
    scrap_percent: float = Field(
        default=2.0,
        description="Expected scrap generated at this step as a percent of processed units"
    )
    buffer_capacity_units: int = Field(
        default=0,
        description="WIP buffer capacity available before/after this step"
    )
    rework_percent: float = Field(
        default=0.0,
        description="Share of units that need rework or retest"
    )
    rework_to_step: Optional[int] = Field(
        default=None,
        description="Optional sequence number to which rework returns"
    )


class FactoryConfig(BaseModel):
    product: str = Field(description="Product being manufactured")
    target_monthly_units: int = Field(description="Target production per month")
    operating_days_per_month: int = Field(default=26)
    shifts_per_day: int = Field(default=2)
    hours_per_shift: float = Field(default=8.0)
    location: str = Field(default="India")
    budget_inr: float = Field(default=10_000_000.0, description="Total budget in INR")
    selling_price_per_unit: float = Field(default=2000.0, description="Selling price in INR")
    raw_material_cost_ratio: float = Field(
        default=0.45,
        description="Raw material cost as a share of selling price"
    )
    labour_cost_per_worker_month_inr: float = Field(
        default=18000.0,
        description="Average monthly cost per worker"
    )
    power_cost_per_kwh_inr: float = Field(
        default=8.0,
        description="Industrial power tariff used for estimation"
    )
    processes: list[ProcessStep] = Field(default_factory=list)
    total_area_sqft: float = Field(default=30000.0)
    warehouse_area_sqft: float = Field(default=8000.0)
    office_area_sqft: float = Field(default=2000.0)

    @property
    def daily_hours(self) -> float:
        return self.shifts_per_day * self.hours_per_shift

    @property
    def target_daily_units(self) -> float:
        return self.target_monthly_units / self.operating_days_per_month


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
    is_bottleneck: bool
    machine_count: int
    workers: int


class SimulationResult(BaseModel):
    effective_throughput_per_day: float = Field(description="Factory good output per day after losses")
    effective_throughput_per_month: float
    target_met: bool = Field(description="Whether target production is achievable")
    production_gap: float = Field(description="Shortfall vs target (negative = surplus)")
    bottleneck_step: str = Field(description="Name of the bottleneck process step")
    bottleneck_capacity_per_day: float
    step_capacities: list[StepCapacity]
    total_workers: int
    total_power_kw: float
    estimated_monthly_power_cost_inr: float
    overall_yield_percent: float = Field(default=100.0)
    monthly_scrap_units: float = Field(default=0.0)
    monthly_input_units_required: float = Field(default=0.0)
    capacity_utilization_percent: float = Field(default=0.0)
    optimization_suggestions: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# 3. FINANCIAL SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

class FinancialSummary(BaseModel):
    total_capex_inr: float
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
    monthly_profit_inr: float
    gross_margin_percent: float
    break_even_months: float
    annual_roi_percent: float
    # Scenario comparison
    conservative: dict
    balanced: dict
    aggressive: dict


# ─────────────────────────────────────────────────────────────────────────────
# 4. THREE.JS SCENE DESCRIPTOR (what gets sent to the frontend for 3D rendering)
# ─────────────────────────────────────────────────────────────────────────────

class SceneZone(BaseModel):
    id: str = Field(description="Unique identifier, e.g. 'zone_warehouse'")
    name: str = Field(description="Human-readable name")
    position: list[float] = Field(description="[x, y, z] center position in 3D space")
    size: list[float] = Field(description="[width, height, depth] of the box")
    color: str = Field(description="Hex color string, e.g. '#3B82F6'")
    emissive_color: str = Field(default="#000000", description="Emissive for bottleneck glow")
    is_bottleneck: bool = Field(default=False)
    zone_type: str = Field(description="'warehouse'|'production'|'testing'|'qc'|'packaging'|'dispatch'|'office'")
    metadata: dict = Field(default_factory=dict, description="Any extra stats to display on click")


class SceneMachine(BaseModel):
    id: str
    name: str
    zone_id: str = Field(description="Which zone this machine belongs to")
    position: list[float]
    size: list[float]
    color: str
    shape: str = Field(default="box", description="'box' or 'cylinder'")
    quantity: int = Field(default=1)
    metadata: dict = Field(default_factory=dict)


class SceneFlow(BaseModel):
    id: str
    from_zone: str = Field(description="Zone ID of source")
    to_zone: str = Field(description="Zone ID of destination")
    label: str = Field(description="e.g. '1000 units/day'")
    is_bottleneck_flow: bool = Field(default=False)


class SceneLabel(BaseModel):
    id: str
    text: str
    position: list[float]
    font_size: float = Field(default=0.5)
    color: str = Field(default="#FFFFFF")


class SceneDescriptor(BaseModel):
    """
    Complete 3D scene description returned to the frontend.
    The react-three/fiber FactoryCanvas component maps this to Three.js objects.
    """
    zones: list[SceneZone]
    machines: list[SceneMachine]
    flows: list[SceneFlow]
    labels: list[SceneLabel] = Field(default_factory=list)
    factory_width: float = Field(description="Total width of factory floor")
    factory_depth: float = Field(description="Total depth of factory floor")
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
    summary_text: str = Field(description="Natural language summary of the twin results")
