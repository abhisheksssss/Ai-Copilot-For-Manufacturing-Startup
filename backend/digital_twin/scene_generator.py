"""
Scene Generator — Uses the NVIDIA LLM to produce a structured 3D scene descriptor
that the react-three/fiber frontend will use to render an interactive 3D factory.

The LLM generates a SceneDescriptor JSON with:
- Factory zones (3D boxes with positions, sizes, colors)
- Machine objects inside each zone
- Flow arrows between zones
- Floating text labels

The approach uses structured output (Pydantic) to guarantee valid JSON,
NOT raw JavaScript/Three.js code (no eval() risk).
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
    "warehouse":  "#1E40AF",   # deep blue
    "production": "#065F46",   # deep green
    "testing":    "#92400E",   # amber-brown
    "qc":         "#581C87",   # purple
    "packaging":  "#9D174D",   # pink-red
    "dispatch":   "#0F766E",   # teal
    "office":     "#374151",   # slate
    "default":    "#1F2937",   # dark grey
}

BOTTLENECK_COLOR = "#991B1B"       # bright red for bottleneck zone
BOTTLENECK_EMISSIVE = "#7F1D1D"    # emissive glow

MACHINE_COLOR = "#4B5563"          # neutral machine color
MACHINE_BOTTLENECK_COLOR = "#B91C1C"

FLOW_NORMAL = "#6EE7B7"            # green flow line
FLOW_BOTTLENECK = "#F87171"        # red flow before bottleneck


# ─────────────────────────────────────────────────────────────────────────────
# DETERMINISTIC SCENE BUILDER (fallback / primary)
# ─────────────────────────────────────────────────────────────────────────────

def build_scene_deterministically(
    config: FactoryConfig,
    simulation: SimulationResult,
) -> SceneDescriptor:
    """
    Build the 3D scene descriptor using deterministic rules — no LLM needed.
    
    Layout strategy: Linear flow left-to-right.
    
      [Warehouse] → [Process 1] → [Process 2] → ... → [QC] → [Packaging] → [Dispatch]
      
    Each zone is placed along the X axis with consistent spacing.
    The Y axis (height) reflects production volume (taller = more capacity).
    """
    # Always start with warehouse, end with dispatch
    base_zones: list[dict] = []

    # Prepend warehouse
    base_zones.append({
        "id": "zone_warehouse",
        "name": "Raw Material Warehouse",
        "zone_type": "warehouse",
        "area_sqft": config.warehouse_area_sqft,
        "machine_count": 0,
        "workers": 5,
        "capacity_label": f"{int(config.warehouse_area_sqft):,} sq ft",
        "is_bottleneck": False,
    })

    # Process steps in order
    for sc in sorted(simulation.step_capacities, key=lambda s: s.sequence):
        base_zones.append({
            "id": f"zone_{sc.step_name.lower().replace(' ', '_')}",
            "name": sc.step_name,
            "zone_type": _infer_zone_type(sc.step_name),
            "area_sqft": 2500,
            "machine_count": sc.machine_count,
            "workers": sc.workers,
            "capacity_label": f"{int(sc.capacity_per_day):,} units/day",
            "is_bottleneck": sc.is_bottleneck,
        })

    # Append dispatch
    base_zones.append({
        "id": "zone_dispatch",
        "name": "Finished Goods & Dispatch",
        "zone_type": "dispatch",
        "area_sqft": 3000,
        "machine_count": 0,
        "workers": 4,
        "capacity_label": "Outbound Logistics",
        "is_bottleneck": False,
    })

    # Add office to the side
    base_zones.append({
        "id": "zone_office",
        "name": "Office & QC Lab",
        "zone_type": "office",
        "area_sqft": config.office_area_sqft,
        "machine_count": 0,
        "workers": 8,
        "capacity_label": f"{int(config.office_area_sqft):,} sq ft",
        "is_bottleneck": False,
    })

    # ── Assign 3D positions ──────────────────────────────────────────────────
    zones: list[SceneZone] = []
    machines: list[SceneMachine] = []
    flows: list[SceneFlow] = []
    labels: list[SceneLabel] = []

    # Main production line: placed along X axis
    main_zones = [z for z in base_zones if z["zone_type"] != "office"]
    zone_spacing = 12.0      # gap between zone centers
    zone_base_width = 8.0
    zone_base_depth = 6.0

    total_width = len(main_zones) * zone_spacing
    start_x = -(total_width / 2) + zone_spacing / 2

    for i, zd in enumerate(main_zones):
        x = start_x + i * zone_spacing
        z_pos = 0.0
        height = 3.0

        # Bottleneck zones are slightly taller and red
        color = ZONE_COLORS.get(zd["zone_type"], ZONE_COLORS["default"])
        emissive = "#000000"
        if zd["is_bottleneck"]:
            color = BOTTLENECK_COLOR
            emissive = BOTTLENECK_EMISSIVE

        zones.append(SceneZone(
            id=zd["id"],
            name=zd["name"],
            position=[round(x, 2), round(height / 2, 2), round(z_pos, 2)],
            size=[zone_base_width, height, zone_base_depth],
            color=color,
            emissive_color=emissive,
            is_bottleneck=zd["is_bottleneck"],
            zone_type=zd["zone_type"],
            metadata={
                "workers": zd["workers"],
                "machines": zd["machine_count"],
                "capacity": zd["capacity_label"],
                "area_sqft": zd["area_sqft"],
            }
        ))

        # Add machines inside the zone as smaller cylinders
        if zd["machine_count"] > 0:
            mc_color = MACHINE_BOTTLENECK_COLOR if zd["is_bottleneck"] else MACHINE_COLOR
            for m in range(min(zd["machine_count"], 4)):  # show max 4 per zone
                mx = x - 2.5 + (m % 2) * 2.5
                mz = -1.5 + (m // 2) * 3.0
                machines.append(SceneMachine(
                    id=f"machine_{zd['id']}_{m}",
                    name=f"Machine {m + 1}",
                    zone_id=zd["id"],
                    position=[round(mx, 2), 1.0, round(mz, 2)],
                    size=[1.2, 2.0, 1.2],
                    color=mc_color,
                    shape="cylinder",
                    quantity=1,
                    metadata={"zone": zd["name"]},
                ))

        # Flow arrows between consecutive zones
        if i > 0:
            prev_zone_id = main_zones[i - 1]["id"]
            prev_bottleneck = main_zones[i - 1]["is_bottleneck"]
            step_name = zd["name"]

            # Find capacity label for this flow
            sc_match = next(
                (sc for sc in simulation.step_capacities if sc.step_name == step_name),
                None
            )
            flow_label = sc_match.capacity_label if hasattr(sc_match, "capacity_label") else ""
            if sc_match:
                flow_label = f"{int(sc_match.capacity_per_day):,} u/day"

            flows.append(SceneFlow(
                id=f"flow_{i}",
                from_zone=prev_zone_id,
                to_zone=zd["id"],
                label=flow_label,
                is_bottleneck_flow=prev_bottleneck or zd["is_bottleneck"],
            ))

        # Zone name label floating above
        labels.append(SceneLabel(
            id=f"label_{zd['id']}",
            text=zd["name"],
            position=[round(x, 2), height + 1.2, z_pos],
            font_size=0.45,
            color="#E5E7EB",
        ))

    # Office zone: placed offset at the back (z = -10)
    office_zone = next((z for z in base_zones if z["zone_type"] == "office"), None)
    if office_zone:
        ox = 0.0
        oz = -10.0
        zones.append(SceneZone(
            id=office_zone["id"],
            name=office_zone["name"],
            position=[ox, 1.5, oz],
            size=[10, 3, 5],
            color=ZONE_COLORS["office"],
            emissive_color="#000000",
            is_bottleneck=False,
            zone_type="office",
            metadata={
                "workers": office_zone["workers"],
                "area_sqft": office_zone["area_sqft"],
            }
        ))
        labels.append(SceneLabel(
            id="label_office",
            text=office_zone["name"],
            position=[ox, 4.0, oz],
            font_size=0.45,
            color="#E5E7EB",
        ))

    # Camera framing
    camera_x = 0.0
    camera_y = 25.0
    camera_z = total_width * 0.8

    return SceneDescriptor(
        zones=zones,
        machines=machines,
        flows=flows,
        labels=labels,
        factory_width=round(total_width + zone_spacing * 2, 1),
        factory_depth=20.0,
        camera_position=[camera_x, camera_y, camera_z],
        camera_target=[0.0, 0.0, 0.0],
    )


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


# ─────────────────────────────────────────────────────────────────────────────
# LLM-ENHANCED SCENE GENERATOR (optional enrichment)
# ─────────────────────────────────────────────────────────────────────────────

async def generate_scene_with_llm(
    config: FactoryConfig,
    simulation: SimulationResult,
    llm,
) -> SceneDescriptor:
    """
    Use the NVIDIA LLM to enrich the scene with product-specific details,
    then overlay the deterministic layout positions.
    
    The LLM suggests: zone names, machine names, visual style hints.
    The math (positions, sizes) comes from the deterministic builder.
    This hybrid approach is reliable — LLM enriches, math positions.
    """
    # Build the deterministic base first (always correct)
    base_scene = build_scene_deterministically(config, simulation)

    prompt = f"""
You are a factory design expert. Given this factory simulation data, 
provide product-specific names and descriptions for the factory zones 
for a {config.product} manufacturing plant in {config.location}.

Factory details:
- Product: {config.product}
- Monthly target: {config.target_monthly_units:,} units
- Bottleneck: {simulation.bottleneck_step}
- Workers: {simulation.total_workers}

Current zones: {[z.name for z in base_scene.zones]}

Respond with ONLY a JSON object with this structure (do not add markdown):
{{
  "factory_title": "e.g. EV Charger Assembly Plant - Gujarat",
  "zone_descriptions": {{
    "zone_warehouse": "description of what's stored here for {config.product}",
    "zone_dispatch": "description of outbound operations"
  }},
  "summary": "One paragraph describing this specific factory"
}}
"""
    try:
        response = await llm.ainvoke([SystemMessage(content="You are a factory layout expert. Return only valid JSON."), HumanMessage(content=prompt)])
        content = response.content if hasattr(response, "content") else str(response)

        # Extract JSON from the response
        content_stripped = content.strip()
        if "```" in content_stripped:
            # Strip markdown code fences
            content_stripped = content_stripped.split("```")[1]
            if content_stripped.startswith("json"):
                content_stripped = content_stripped[4:]

        enrichment = json.loads(content_stripped)

        # Apply enrichment: update zone metadata with descriptions
        for zone in base_scene.zones:
            desc = enrichment.get("zone_descriptions", {}).get(zone.id, "")
            if desc:
                zone.metadata["description"] = desc

        # Add a title label at the top
        factory_title = enrichment.get("factory_title", f"{config.product} Manufacturing Plant")
        base_scene.labels.append(SceneLabel(
            id="label_factory_title",
            text=factory_title,
            position=[0.0, 8.0, 0.0],
            font_size=0.8,
            color="#F9FAFB",
        ))

    except Exception as e:
        print(f"[SCENE GENERATOR] LLM enrichment failed (using base scene): {e}")
        # Return the deterministic scene — it's always valid
        pass

    return base_scene
