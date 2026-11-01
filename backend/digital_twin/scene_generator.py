"""
Scene Generator — Builds an industrial 3D Digital Twin layout.

Enhancements:
- Preserves 'conveyor', 'cylinder', and 'box' machine shapes
- Visualizes rework loops (amber return arcs) when rework_to_step is configured
- Exposes Takt Time, Cycle Time, OEE, and Line State in zone metadata
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


ZONE_COLORS = {
    "warehouse":  "#1E40AF",
    "production": "#065F46",
    "testing":    "#B45309",
    "qc":         "#6B21A8",
    "packaging":  "#9D174D",
    "dispatch":   "#0F766E",
    "office":     "#334155",
    "default":    "#1F2937",
}

BOTTLENECK_COLOR = "#991B1B"
BOTTLENECK_EMISSIVE = "#7F1D1D"

MACHINE_COLOR = "#64748B"
MACHINE_BOTTLENECK_COLOR = "#DC2626"


def _slug(value: str) -> str:
    return (
        value.lower()
        .replace("&", "and")
        .replace("/", "_")
        .replace("-", "_")
        .replace(" ", "_")
    )


def _infer_zone_type(step_name: str) -> str:
    name_lower = step_name.lower()
    if any(w in name_lower for w in ["test", "burn", "calibration"]):
        return "testing"
    if any(w in name_lower for w in ["quality", "qc", "inspection", "aoi"]):
        return "qc"
    if any(w in name_lower for w in ["pack", "label", "carton", "pallet"]):
        return "packaging"
    if any(w in name_lower for w in ["dispatch", "ship", "logistics", "outbound"]):
        return "dispatch"
    return "production"


def _zone_dimensions(area_sqft: float) -> tuple[float, float]:
    area_sqft = max(area_sqft, 600.0)
    area_scaled = area_sqft / 180.0
    width = max(6.5, min(16.0, round(area_scaled ** 0.5 * 2.1, 1)))
    depth = max(5.5, min(13.0, round(area_scaled ** 0.5 * 1.75, 1)))
    return width, depth


def _zone_height_from_capacity(capacity_per_day: float) -> float:
    if capacity_per_day <= 0:
        return 3.2
    return max(3.2, min(7.0, round(2.6 + (capacity_per_day ** 0.5) / 14.0, 1)))


def _machine_shape(machine_type: str) -> str:
    mt = (machine_type or "box").lower()
    if mt in ("cylinder", "conveyor"):
        return mt
    return "box"


def build_scene_deterministically(
    config: FactoryConfig,
    simulation: SimulationResult,
) -> SceneDescriptor:
    base_zones: list[dict] = []

    base_zones.append({
        "id": "zone_warehouse",
        "name": "Raw Material Inbound",
        "zone_type": "warehouse",
        "sequence": 0,
        "area_sqft": config.warehouse_area_sqft,
        "machine_count": 2,
        "workers": 5,
        "capacity_label": f"{int(simulation.monthly_input_units_required / max(config.operating_days_per_month, 1)):,} raw units/day",
        "is_bottleneck": False,
        "throughput_per_day": simulation.effective_throughput_per_day,
        "utilization_percent": 75.0,
        "yield_percent": 100.0,
        "oee_percent": 95.0,
        "cycle_time_sec": 0.0,
        "line_state": "balanced",
        "runtime_hours": config.daily_hours,
        "machine_name": "Heavy Duty Pallet Rack",
        "machine_type": "box",
        "rework_to_step": None,
        "rework_percent": 0.0,
    })

    ordered_steps = sorted(config.processes, key=lambda s: s.sequence)
    step_capacity_map = {sc.step_name: sc for sc in simulation.step_capacities}
    seq_to_zone_id: dict[int, str] = {}

    for step in ordered_steps:
        sc = step_capacity_map.get(step.name)
        throughput = sc.actual_good_output_per_day if sc else 0.0
        zid = f"zone_{step.sequence}_{_slug(step.name)}"
        seq_to_zone_id[step.sequence] = zid

        base_zones.append({
            "id": zid,
            "name": step.name,
            "zone_type": step.zone_type or _infer_zone_type(step.name),
            "sequence": step.sequence,
            "area_sqft": step.area_sqft,
            "machine_count": step.machine.quantity,
            "workers": step.workers_required,
            "capacity_label": f"{int(throughput):,} good units/day" if throughput else "Pending",
            "is_bottleneck": sc.is_bottleneck if sc else False,
            "throughput_per_day": throughput,
            "utilization_percent": sc.utilization_percent if sc else 0.0,
            "yield_percent": sc.yield_percent if sc else step.yield_percent,
            "oee_percent": sc.oee_percent if sc else step.machine.oee_percent,
            "cycle_time_sec": sc.cycle_time_sec if sc else 0.0,
            "line_state": sc.line_state if sc else "balanced",
            "runtime_hours": sc.effective_runtime_hours_per_day if sc else config.daily_hours,
            "machine_name": step.machine.name,
            "machine_type": step.machine.machine_type,
            "rework_to_step": step.rework_to_step,
            "rework_percent": step.rework_percent,
        })

    base_zones.append({
        "id": "zone_dispatch",
        "name": "Finished Goods & Dispatch",
        "zone_type": "dispatch",
        "sequence": 999,
        "area_sqft": max(2500.0, config.total_area_sqft * 0.08),
        "machine_count": 2,
        "workers": 4,
        "capacity_label": f"{int(simulation.effective_throughput_per_day):,} units/day outbound",
        "is_bottleneck": False,
        "throughput_per_day": simulation.effective_throughput_per_day,
        "utilization_percent": 82.0,
        "yield_percent": 100.0,
        "oee_percent": 95.0,
        "cycle_time_sec": 0.0,
        "line_state": "balanced",
        "runtime_hours": config.daily_hours,
        "machine_name": "Outbound Conveyor Dock",
        "machine_type": "conveyor",
        "rework_to_step": None,
        "rework_percent": 0.0,
    })

    base_zones.append({
        "id": "zone_office",
        "name": "MES Control & QA Lab",
        "zone_type": "office",
        "sequence": 1000,
        "area_sqft": config.office_area_sqft,
        "machine_count": 0,
        "workers": 8,
        "capacity_label": f"{int(config.office_area_sqft):,} sq ft",
        "is_bottleneck": False,
        "throughput_per_day": 0.0,
        "utilization_percent": 0.0,
        "yield_percent": 100.0,
        "oee_percent": 100.0,
        "cycle_time_sec": 0.0,
        "line_state": "office",
        "runtime_hours": config.daily_hours,
        "machine_name": "SCADA / MES Consoles",
        "machine_type": "box",
        "rework_to_step": None,
        "rework_percent": 0.0,
    })

    zones: list[SceneZone] = []
    machines: list[SceneMachine] = []
    flows: list[SceneFlow] = []
    labels: list[SceneLabel] = []

    main_zones = [z for z in base_zones if z["zone_type"] != "office"]
    x_cursor = 0.0
    zone_gap = 4.5
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

        meta = {
            "line_state": str(zd["line_state"]).upper(),
            "output": zd["capacity_label"],
            "utilization": f"{round(zd['utilization_percent'], 1)}%",
            "yield": f"{round(zd['yield_percent'], 1)}%",
            "oee": f"{round(zd['oee_percent'], 1)}%",
            "machines": f"{zd['machine_count']}x {zd['machine_name']}",
            "operators": f"{zd['workers']} staff",
            "floor_area": f"{int(zd['area_sqft']):,} sq ft",
        }
        if zd["cycle_time_sec"] > 0:
            meta["cycle_vs_takt"] = f"{zd['cycle_time_sec']:.1f}s / {simulation.plant_takt_time_sec:.1f}s"

        zones.append(SceneZone(
            id=zd["id"],
            name=zd["name"],
            position=[x, round(height / 2, 2), 0.0],
            size=[width, height, depth],
            color=color,
            emissive_color=emissive,
            is_bottleneck=zd["is_bottleneck"],
            zone_type=zd["zone_type"],
            metadata=meta,
        ))

        if zd["machine_count"] > 0:
            max_show = min(zd["machine_count"], 8)
            cols = min(4, max_show)
            rows = (max_show + cols - 1) // cols
            step_x = width / (cols + 1)
            step_z = depth / (rows + 1)
            mc_color = MACHINE_BOTTLENECK_COLOR if zd["is_bottleneck"] else MACHINE_COLOR
            m_shape = _machine_shape(zd["machine_type"])
            m_size = [2.2, 0.9, 0.9] if m_shape == "conveyor" else [1.3, 1.9, 1.2]

            for idx in range(max_show):
                col = idx % cols
                row = idx // cols
                mx = x - (width / 2) + step_x * (col + 1)
                mz = -depth / 2 + step_z * (row + 1)
                machines.append(SceneMachine(
                    id=f"machine_{zd['id']}_{idx + 1}",
                    name=f"{zd['machine_name']} #{idx + 1}",
                    zone_id=zd["id"],
                    position=[round(mx, 2), round(m_size[1] / 2, 2), round(mz, 2)],
                    size=m_size,
                    color=mc_color,
                    shape=m_shape,
                    quantity=1,
                    metadata={
                        "zone": zd["name"],
                        "machine_type": m_shape,
                    },
                ))

        labels.append(SceneLabel(
            id=f"label_{zd['id']}",
            text=f"{zd['name']}\n({round(zd['utilization_percent'], 0):.0f}% util)",
            position=[x, height + 1.25, 0.0],
            font_size=0.42,
            color="#E5E7EB",
        ))

    # Forward production flows
    for i in range(1, len(main_zones)):
        prev_zone = main_zones[i - 1]
        current_zone = main_zones[i]
        is_bn_flow = prev_zone["is_bottleneck"] or current_zone["is_bottleneck"]
        flows.append(SceneFlow(
            id=f"flow_{i}",
            from_zone=prev_zone["id"],
            to_zone=current_zone["id"],
            label=current_zone["capacity_label"],
            is_bottleneck_flow=is_bn_flow,
            flow_type="bottleneck" if is_bn_flow else "normal",
        ))

    # Rework feedback flows
    for zd in main_zones:
        target_seq = zd.get("rework_to_step")
        if target_seq and zd.get("rework_percent", 0) > 0 and target_seq in seq_to_zone_id:
            target_zone_id = seq_to_zone_id[target_seq]
            if target_zone_id != zd["id"]:
                flows.append(SceneFlow(
                    id=f"flow_rework_{zd['id']}_to_{target_zone_id}",
                    from_zone=zd["id"],
                    to_zone=target_zone_id,
                    label=f"Rework ({zd['rework_percent']:.1f}%)",
                    is_bottleneck_flow=False,
                    flow_type="rework",
                ))

    office_zone = next((z for z in base_zones if z["zone_type"] == "office"), None)
    total_width = max(zone_centers.values()) + 12.0 if zone_centers else 40.0
    center_x = round((min(zone_centers.values()) + max(zone_centers.values())) / 2.0, 2) if zone_centers else 20.0

    if office_zone:
        ox = center_x
        oz = -12.5
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
                "staff": f"{office_zone['workers']} engineers",
                "floor_area": f"{int(office_zone['area_sqft']):,} sq ft",
                "systems": "SCADA, MES, Quality Lab & Production Planning",
            },
        ))
        labels.append(SceneLabel(
            id="label_office",
            text=office_zone["name"],
            position=[round(ox, 2), 4.6, round(oz, 2)],
            font_size=0.42,
            color="#94A3B8",
        ))

    labels.append(SceneLabel(
        id="label_factory_kpi",
        text=(
            f"Output: {int(simulation.effective_throughput_per_month):,}/mo | "
            f"FPY: {simulation.first_pass_yield_percent:.1f}% | "
            f"Line Efficiency: {simulation.line_balance_efficiency_percent:.0f}%"
        ),
        position=[center_x, 8.2, 0.0],
        font_size=0.48,
        color="#38BDF8",
    ))

    return SceneDescriptor(
        zones=zones,
        machines=machines,
        flows=flows,
        labels=labels,
        factory_width=round(total_width + 10.0, 1),
        factory_depth=32.0,
        camera_position=[center_x, 28.0, round(max(total_width * 0.52, 32.0), 2)],
        camera_target=[center_x, 1.5, -2.0],
    )


async def generate_scene_with_llm(
    config: FactoryConfig,
    simulation: SimulationResult,
    llm,
) -> SceneDescriptor:
    base_scene = build_scene_deterministically(config, simulation)

    prompt = f"""
You are a factory layout engineer. Given this factory simulation data,
provide brief, technical descriptions for each zone in a {config.product} manufacturing plant in {config.location}.

Factory details:
- Product: {config.product}
- Monthly target: {config.target_monthly_units:,} units
- Actual monthly output: {int(simulation.effective_throughput_per_month):,} units
- Bottleneck: {simulation.bottleneck_step}
- Zone IDs: {[z.id for z in base_scene.zones]}

Respond with ONLY valid JSON:
{{
  "factory_title": "{config.product} Smart Factory — {config.location}",
  "zone_descriptions": {{
    "zone_id_here": "1-sentence technical description of equipment and material handling"
  }}
}}
"""
    try:
        response = await llm.ainvoke([
            SystemMessage(content="You are a manufacturing systems architect. Return valid JSON only."),
            HumanMessage(content=prompt),
        ])
        content = response.content if hasattr(response, "content") else str(response)
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            enrichment = json.loads(content[start:end])
            zone_descs = enrichment.get("zone_descriptions", {})
            for zone in base_scene.zones:
                desc = zone_descs.get(zone.id)
                if desc:
                    zone.metadata["description"] = desc

            factory_title = enrichment.get("factory_title", f"{config.product} Smart Factory — {config.location}")
            base_scene.labels.append(SceneLabel(
                id="label_factory_title",
                text=factory_title,
                position=[base_scene.camera_target[0], 9.6, 0.0],
                font_size=0.72,
                color="#F8FAFC",
            ))
    except Exception as e:
        print(f"[SCENE GENERATOR] LLM enrichment skipped (using deterministic scene): {e}")

    return base_scene