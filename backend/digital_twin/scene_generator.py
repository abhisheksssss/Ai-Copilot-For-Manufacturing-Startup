"""
Scene Generator — Builds a structured 3D scene descriptor for the frontend.

Enhancements in this version:
- uses true process zone_type from config instead of re-inferring blindly
- scales zone footprint from actual area_sqft
- preserves real machine names and machine_type in the scene
- exposes richer metadata for utilization, runtime, yield, and bottlenecks
"""
import json
from langchain_core.messages import SystemMessage, HumanMessage

from .models import (
    FactoryConfig,
    SimulationResult,
    SceneDescriptor,
    SceneZone,
    SceneMachine,
    SceneFlow,
    SceneLabel,
)


# ─────────────────────────────────────────────────────────────────────────────
# ZONE COLOR PALETTE
# ─────────────────────────────────────────────────────────────────────────────

ZONE_COLORS = {
    "warehouse":  "#1E40AF",
    "production": "#065F46",
    "testing":    "#92400E",
    "qc":         "#581C87",
    "packaging":  "#9D174D",
    "dispatch":   "#0F766E",
    "office":     "#374151",
    "default":    "#1F2937",
}

BOTTLENECK_COLOR = "#991B1B"
BOTTLENECK_EMISSIVE = "#7F1D1D"

MACHINE_COLOR = "#4B5563"
MACHINE_BOTTLENECK_COLOR = "#B91C1C"


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _slug(value: str) -> str:
    return value.lower().replace("&", "and").replace("/", "_").replace(" ", "_")


def _infer_zone_type(step_name: str) -> str:
    name_lower = step_name.lower()
    if any(w in name_lower for w in ["test", "check"]):
        return "testing"
    if any(w in name_lower for w in ["quality", "qc", "inspection"]):
        return "qc"
    if any(w in name_lower for w in ["pack", "label", "seal"]):
        return "packaging"
    if any(w in name_lower for w in ["dispatch", "ship", "logistics", "outbound"]):
        return "dispatch"
    return "production"


def _zone_dimensions(area_sqft: float) -> tuple[float, float]:
    """Map 2D area to a simple width/depth footprint for visualization."""
    area_sqft = max(area_sqft, 600.0)
    area_scaled = area_sqft / 180.0
    width = max(6.0, min(18.0, round(area_scaled ** 0.5 * 2.2, 1)))
    depth = max(5.0, min(14.0, round(area_scaled ** 0.5 * 1.8, 1)))
    return width, depth


def _zone_height_from_capacity(capacity_per_day: float) -> float:
    if capacity_per_day <= 0:
        return 3.0
    return max(3.0, min(7.5, round(2.5 + (capacity_per_day ** 0.5) / 12.0, 1)))


def _machine_shape(machine_type: str) -> str:
    if machine_type == "cylinder":
        return "cylinder"
    return "box"


# ─────────────────────────────────────────────────────────────────────────────
# DETERMINISTIC SCENE BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_scene_deterministically(
    config: FactoryConfig,
    simulation: SimulationResult,
) -> SceneDescriptor:
    """
    Build the 3D scene descriptor using deterministic rules.

    Layout strategy: left-to-right material flow with richer per-zone geometry.
    """
    base_zones: list[dict] = []

    base_zones.append({
        "id": "zone_warehouse",
        "name": "Raw Material Warehouse",
        "zone_type": "warehouse",
        "area_sqft": config.warehouse_area_sqft,
        "machine_count": 0,
        "workers": 5,
        "capacity_label": f"{int(config.warehouse_area_sqft):,} sq ft",
        "is_bottleneck": False,
        "throughput_per_day": 0.0,
        "utilization_percent": 0.0,
        "yield_percent": 100.0,
        "runtime_hours": config.daily_hours,
        "machine_name": "Storage Racks",
        "machine_type": "box",
    })

    ordered_steps = sorted(config.processes, key=lambda s: s.sequence)
    step_capacity_map = {sc.step_name: sc for sc in simulation.step_capacities}

    for step in ordered_steps:
        sc = step_capacity_map.get(step.name)
        throughput = sc.capacity_per_day if sc else 0.0
        base_zones.append({
            "id": f"zone_{_slug(step.name)}",
            "name": step.name,
            "zone_type": step.zone_type or _infer_zone_type(step.name),
            "area_sqft": step.area_sqft,
            "machine_count": step.machine.quantity,
            "workers": step.workers_required,
            "capacity_label": f"{int(throughput):,} good units/day" if throughput else "Pending analysis",
            "is_bottleneck": sc.is_bottleneck if sc else False,
            "throughput_per_day": throughput,
            "utilization_percent": sc.utilization_percent if sc else 0.0,
            "yield_percent": sc.yield_percent if sc else step.yield_percent,
            "runtime_hours": sc.effective_runtime_hours_per_day if sc else config.daily_hours,
            "machine_name": step.machine.name,
            "machine_type": step.machine.machine_type,
        })

    base_zones.append({
        "id": "zone_dispatch",
        "name": "Finished Goods & Dispatch",
        "zone_type": "dispatch",
        "area_sqft": max(2500.0, config.total_area_sqft * 0.08),
        "machine_count": 0,
        "workers": 4,
        "capacity_label": f"{int(simulation.effective_throughput_per_day):,} units/day outbound",
        "is_bottleneck": False,
        "throughput_per_day": simulation.effective_throughput_per_day,
        "utilization_percent": 0.0,
        "yield_percent": 100.0,
        "runtime_hours": config.daily_hours,
        "machine_name": "Loading Bay",
        "machine_type": "box",
    })

    base_zones.append({
        "id": "zone_office",
        "name": "Office & Control Room",
        "zone_type": "office",
        "area_sqft": config.office_area_sqft,
        "machine_count": 0,
        "workers": 8,
        "capacity_label": f"{int(config.office_area_sqft):,} sq ft",
        "is_bottleneck": False,
        "throughput_per_day": 0.0,
        "utilization_percent": 0.0,
        "yield_percent": 100.0,
        "runtime_hours": config.daily_hours,
        "machine_name": "Control Systems",
        "machine_type": "box",
    })

    zones: list[SceneZone] = []
    machines: list[SceneMachine] = []
    flows: list[SceneFlow] = []
    labels: list[SceneLabel] = []

    main_zones = [z for z in base_zones if z["zone_type"] != "office"]
    x_cursor = 0.0
    zone_gap = 5.0
    zone_centers: dict[str, float] = {}

    for zd in main_zones:
        width, depth = _zone_dimensions(zd["area_sqft"])
        height = _zone_height_from_capacity(zd["throughput_per_day"])
        x_cursor += width / 2
        x = round(x_cursor, 2)
        zone_centers[zd["id"]] = x
        x_cursor += width / 2 + zone_gap

        color = ZONE_COLORS.get(zd["zone_type"], ZONE_COLORS["default"])
        emissive = "#000000"
        if zd["is_bottleneck"]:
            color = BOTTLENECK_COLOR
            emissive = BOTTLENECK_EMISSIVE

        zones.append(SceneZone(
            id=zd["id"],
            name=zd["name"],
            position=[x, round(height / 2, 2), 0.0],
            size=[width, height, depth],
            color=color,
            emissive_color=emissive,
            is_bottleneck=zd["is_bottleneck"],
            zone_type=zd["zone_type"],
            metadata={
                "workers": zd["workers"],
                "machines": zd["machine_count"],
                "capacity": zd["capacity_label"],
                "area_sqft": zd["area_sqft"],
                "utilization_percent": round(zd["utilization_percent"], 1),
                "yield_percent": round(zd["yield_percent"], 1),
                "runtime_hours_per_day": round(zd["runtime_hours"], 2),
                "machine_name": zd["machine_name"],
            }
        ))

        if zd["machine_count"] > 0:
            max_show = min(zd["machine_count"], 6)
            cols = min(3, max_show)
            rows = (max_show + cols - 1) // cols
            step_x = width / (cols + 1)
            step_z = depth / (rows + 1)
            mc_color = MACHINE_BOTTLENECK_COLOR if zd["is_bottleneck"] else MACHINE_COLOR

            for idx in range(max_show):
                col = idx % cols
                row = idx // cols
                mx = x - (width / 2) + step_x * (col + 1)
                mz = -depth / 2 + step_z * (row + 1)
                machines.append(SceneMachine(
                    id=f"machine_{zd['id']}_{idx + 1}",
                    name=f"{zd['machine_name']} {idx + 1}",
                    zone_id=zd["id"],
                    position=[round(mx, 2), 1.0, round(mz, 2)],
                    size=[1.4, 2.0, 1.2],
                    color=mc_color,
                    shape=_machine_shape(zd["machine_type"]),
                    quantity=1,
                    metadata={
                        "zone": zd["name"],
                        "machine_type": zd["machine_type"],
                    },
                ))

        labels.append(SceneLabel(
            id=f"label_{zd['id']}",
            text=zd["name"],
            position=[x, height + 1.1, 0.0],
            font_size=0.45,
            color="#E5E7EB",
        ))

    for i in range(1, len(main_zones)):
        prev_zone = main_zones[i - 1]
        current_zone = main_zones[i]
        flow_label = current_zone["capacity_label"] if current_zone["throughput_per_day"] else "Material flow"
        flows.append(SceneFlow(
            id=f"flow_{i}",
            from_zone=prev_zone["id"],
            to_zone=current_zone["id"],
            label=flow_label,
            is_bottleneck_flow=prev_zone["is_bottleneck"] or current_zone["is_bottleneck"],
        ))

    office_zone = next((z for z in base_zones if z["zone_type"] == "office"), None)
    total_width = max(zone_centers.values()) + 12.0 if zone_centers else 40.0
    if office_zone:
        ox = total_width / 2 - 10.0
        oz = -11.0
        ow, od = _zone_dimensions(office_zone["area_sqft"])
        zones.append(SceneZone(
            id=office_zone["id"],
            name=office_zone["name"],
            position=[round(ox, 2), 1.7, round(oz, 2)],
            size=[ow, 3.4, od],
            color=ZONE_COLORS["office"],
            emissive_color="#000000",
            is_bottleneck=False,
            zone_type="office",
            metadata={
                "workers": office_zone["workers"],
                "area_sqft": office_zone["area_sqft"],
                "role": "Operations control, planning, admin, and QC review",
            },
        ))
        labels.append(SceneLabel(
            id="label_office",
            text=office_zone["name"],
            position=[round(ox, 2), 4.8, round(oz, 2)],
            font_size=0.45,
            color="#E5E7EB",
        ))

    labels.append(SceneLabel(
        id="label_factory_kpi",
        text=f"Output {int(simulation.effective_throughput_per_month):,}/month | Yield {simulation.overall_yield_percent:.1f}%",
        position=[round(total_width / 2 - 12.0, 2), 8.0, 0.0],
        font_size=0.5,
        color="#F9FAFB",
    ))

    return SceneDescriptor(
        zones=zones,
        machines=machines,
        flows=flows,
        labels=labels,
        factory_width=round(total_width + 8.0, 1),
        factory_depth=26.0,
        camera_position=[round(total_width / 2 - 8.0, 2), 28.0, round(total_width * 0.55, 2)],
        camera_target=[round(total_width / 2 - 8.0, 2), 0.0, 0.0],
    )


# ─────────────────────────────────────────────────────────────────────────────
# LLM-ENHANCED SCENE GENERATOR (optional enrichment)
# ─────────────────────────────────────────────────────────────────────────────

async def generate_scene_with_llm(
    config: FactoryConfig,
    simulation: SimulationResult,
    llm,
) -> SceneDescriptor:
    """
    Use the LLM to enrich the scene with product-specific descriptions while
    keeping the deterministic geometry authoritative.
    """
    base_scene = build_scene_deterministically(config, simulation)

    prompt = f"""
You are a factory design expert. Given this factory simulation data,
provide product-specific names and descriptions for the factory zones
for a {config.product} manufacturing plant in {config.location}.

Factory details:
- Product: {config.product}
- Monthly target: {config.target_monthly_units:,} units
- Actual monthly output: {int(simulation.effective_throughput_per_month):,} units
- Bottleneck: {simulation.bottleneck_step}
- Workers: {simulation.total_workers}
- Overall yield: {simulation.overall_yield_percent:.1f}%

Current zones: {[z.name for z in base_scene.zones]}

Respond with ONLY a JSON object with this structure:
{{
  "factory_title": "e.g. EV Charger Assembly Plant - Gujarat",
  "zone_descriptions": {{
    "zone_warehouse": "description of what's stored here",
    "zone_dispatch": "description of outbound operations"
  }},
  "summary": "One paragraph describing this specific factory"
}}
"""
    try:
        response = await llm.ainvoke([
            SystemMessage(content="You are a factory layout expert. Return only valid JSON."),
            HumanMessage(content=prompt),
        ])
        content = response.content if hasattr(response, "content") else str(response)
        content_stripped = content.strip()
        if "```" in content_stripped:
            content_stripped = content_stripped.split("```")[1]
            if content_stripped.startswith("json"):
                content_stripped = content_stripped[4:]

        enrichment = json.loads(content_stripped)

        for zone in base_scene.zones:
            desc = enrichment.get("zone_descriptions", {}).get(zone.id, "")
            if desc:
                zone.metadata["description"] = desc

        factory_title = enrichment.get("factory_title", f"{config.product} Manufacturing Plant")
        base_scene.labels.append(SceneLabel(
            id="label_factory_title",
            text=factory_title,
            position=[base_scene.camera_target[0], 9.5, 0.0],
            font_size=0.8,
            color="#F9FAFB",
        ))

    except Exception as e:
        print(f"[SCENE GENERATOR] LLM enrichment failed (using base scene): {e}")

    return base_scene
