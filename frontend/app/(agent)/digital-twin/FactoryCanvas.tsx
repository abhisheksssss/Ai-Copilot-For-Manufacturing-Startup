"use client";

import { useRef, useState, useEffect, useMemo, type FC } from "react";
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { OrbitControls, Grid, Text, Line, Edges } from "@react-three/drei";
import * as THREE from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface SceneZone {
  id: string;
  name: string;
  position: [number, number, number];
  size: [number, number, number];
  color: string;
  emissive_color: string;
  is_bottleneck: boolean;
  zone_type: string;
  metadata: Record<string, unknown>;
}

export interface SceneMachine {
  id: string;
  name: string;
  zone_id: string;
  position: [number, number, number];
  size: [number, number, number];
  color: string;
  shape: string;
  quantity: number;
  metadata: Record<string, unknown>;
}

export interface SceneFlow {
  id: string;
  from_zone: string;
  to_zone: string;
  label: string;
  is_bottleneck_flow: boolean;
}

export interface SceneLabel {
  id: string;
  text: string;
  position: [number, number, number];
  font_size: number;
  color: string;
}

export interface SceneDescriptor {
  zones: SceneZone[];
  machines: SceneMachine[];
  flows: SceneFlow[];
  labels: SceneLabel[];
  factory_width: number;
  factory_depth: number;
  camera_position: [number, number, number];
  camera_target: [number, number, number];
}

export interface FactoryCanvasProps {
  scene: SceneDescriptor;
  selectedZoneId?: string | null;
  onZoneClick: (zone: SceneZone | null) => void;
}

// ─── Safe data normaliser ─────────────────────────────────────────────────────

function safeVec3(v: unknown, fallback: [number, number, number]): [number, number, number] {
  if (Array.isArray(v) && v.length >= 3 && v.every((x) => typeof x === "number" && isFinite(x))) {
    return [v[0], v[1], v[2]];
  }
  return fallback;
}

function safeColor(c: unknown, fallback = "#3b82f6"): string {
  if (typeof c === "string" && c.trim().length > 0) return c.trim();
  return fallback;
}

function safeNum(n: unknown, fallback: number): number {
  const v = Number(n);
  return isFinite(v) && v > 0 ? v : fallback;
}

// ─── Bottleneck Pulse ─────────────────────────────────────────────────────────

const BottleneckPulse: FC<{
  position: [number, number, number];
  size: [number, number, number];
}> = ({ position, size }) => {
  const ref = useRef<THREE.Mesh>(null!);

  useFrame((state) => {
    if (!ref.current) return;
    const t = Math.sin(state.clock.getElapsedTime() * 3.2) * 0.5 + 0.5;
    const mat = ref.current.material as THREE.MeshStandardMaterial;
    mat.emissiveIntensity = 0.6 + t * 1.4;
    mat.opacity = 0.08 + t * 0.14;
    const s = 1 + t * 0.04;
    ref.current.scale.set(s, s, s);
  });

  return (
    <mesh ref={ref} position={position}>
      <boxGeometry args={[size[0] + 0.35, size[1] + 0.35, size[2] + 0.35]} />
      <meshStandardMaterial
        color="#dc2626"
        emissive="#ff1111"
        emissiveIntensity={1.2}
        transparent
        opacity={0.15}
        depthWrite={false}
      />
    </mesh>
  );
};

// ─── Floor glow under zone ────────────────────────────────────────────────────

const ZoneGlow: FC<{ zone: SceneZone; isSelected: boolean }> = ({ zone, isSelected }) => {
  const pos = safeVec3(zone.position, [0, 0, 0]);
  const size = safeVec3(zone.size, [4, 3, 4]);
  const col = safeColor(
    isSelected ? "#00e5ff" : zone.is_bottleneck ? "#ff2222" : zone.color,
    "#3b82f6"
  );

  return (
    <mesh position={[pos[0], 0.02, pos[2]]} rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={[size[0] * 1.35, size[2] * 1.35]} />
      <meshStandardMaterial
        color={col}
        emissive={col}
        emissiveIntensity={isSelected ? 0.8 : 0.35}
        transparent
        opacity={isSelected ? 0.22 : 0.1}
        depthWrite={false}
      />
    </mesh>
  );
};

// ─── Factory Zone ─────────────────────────────────────────────────────────────

const FactoryZone: FC<{
  zone: SceneZone;
  isSelected: boolean;
  onZoneClick: (z: SceneZone) => void;
}> = ({ zone, isSelected, onZoneClick }) => {
  const [hovered, setHovered] = useState(false);
  const meshRef = useRef<THREE.Mesh>(null!);

  const pos = safeVec3(zone.position, [0, 0, 0]);
  const size = safeVec3(zone.size, [4, 3, 4]);
  const col = safeColor(zone.color, "#3b82f6");
  const emCol = safeColor(
    zone.is_bottleneck ? "#ff1111" : zone.emissive_color || zone.color,
    col
  );

  useEffect(() => {
    if (hovered) {
      document.body.style.cursor = "pointer";
      return () => {
        document.body.style.cursor = "auto";
      };
    }
  }, [hovered]);

  useFrame(() => {
    if (!meshRef.current) return;
    const mat = meshRef.current.material as THREE.MeshStandardMaterial;
    const target = isSelected ? 0.95 : hovered ? 0.75 : zone.is_bottleneck ? 0.55 : 0.2;
    mat.emissiveIntensity = THREE.MathUtils.lerp(mat.emissiveIntensity, target, 0.12);
  });

  return (
    <group>
      <ZoneGlow zone={zone} isSelected={isSelected} />
      <mesh
        ref={meshRef}
        position={pos}
        onClick={(e: ThreeEvent<MouseEvent>) => {
          e.stopPropagation();
          onZoneClick(zone);
        }}
        onPointerOver={(e: ThreeEvent<PointerEvent>) => {
          e.stopPropagation();
          setHovered(true);
        }}
        onPointerOut={() => setHovered(false)}
      >
        <boxGeometry args={size} />
        <meshStandardMaterial
          color={col}
          emissive={emCol}
          emissiveIntensity={zone.is_bottleneck ? 0.55 : 0.2}
          roughness={0.28}
          metalness={0.55}
          transparent
          opacity={hovered || isSelected ? 0.92 : 0.78}
        />
        <Edges
          threshold={15}
          color={isSelected ? "#00f0ff" : zone.is_bottleneck ? "#ff4444" : "#ffffff"}
          scale={1.002}
        />
      </mesh>

      {zone.is_bottleneck && <BottleneckPulse position={pos} size={size} />}

      {(hovered || isSelected) && (
        <mesh position={pos}>
          <boxGeometry args={[size[0] + 0.18, size[1] + 0.18, size[2] + 0.18]} />
          <meshStandardMaterial
            color={isSelected ? "#00f0ff" : "#38bdf8"}
            emissive={isSelected ? "#00f0ff" : "#38bdf8"}
            emissiveIntensity={0.6}
            transparent
            opacity={isSelected ? 0.22 : 0.12}
            wireframe
          />
        </mesh>
      )}
    </group>
  );
};

// ─── Machine Object ───────────────────────────────────────────────────────────

const MachineObject: FC<{ machine: SceneMachine }> = ({ machine }) => {
  const ref = useRef<THREE.Mesh>(null!);
  const pos = safeVec3(machine.position, [0, 0, 0]);
  const size = safeVec3(machine.size, [1, 1, 1]);
  const col = safeColor(machine.color, "#6b7280");

  useFrame((state) => {
    if (ref.current && machine.shape === "cylinder") {
      ref.current.rotation.y = state.clock.getElapsedTime() * 0.4;
    }
  });

  return (
    <mesh ref={ref} position={pos}>
      {machine.shape === "cylinder" ? (
        <cylinderGeometry args={[size[0] / 2, size[0] / 2, size[1], 16]} />
      ) : (
        <boxGeometry args={size} />
      )}
      <meshStandardMaterial
        color={col}
        roughness={0.25}
        metalness={0.8}
        emissive={col}
        emissiveIntensity={0.22}
      />
    </mesh>
  );
};

// ─── 3D Flow Arrow (Full 3D Bezier + Animated Pulse Particle) ─────────────────

const FlowArrow: FC<{ flow: SceneFlow; zones: SceneZone[] }> = ({ flow, zones }) => {
  const particleRef = useRef<THREE.Mesh>(null!);

  const flowGeometry = useMemo(() => {
    const fromZone = zones.find((z) => z.id === flow.from_zone);
    const toZone = zones.find((z) => z.id === flow.to_zone);
    if (!fromZone || !toZone) return null;

    const fromPos = safeVec3(fromZone.position, [0, 0, 0]);
    const fromSize = safeVec3(fromZone.size, [4, 3, 4]);
    const toPos = safeVec3(toZone.position, [0, 0, 0]);
    const toSize = safeVec3(toZone.size, [4, 3, 4]);

    const startVec = new THREE.Vector3(
      fromPos[0],
      fromPos[1] + fromSize[1] / 2 + 0.35,
      fromPos[2]
    );
    const endVec = new THREE.Vector3(
      toPos[0],
      toPos[1] + toSize[1] / 2 + 0.35,
      toPos[2]
    );

    const dist = startVec.distanceTo(endVec);
    if (!isFinite(dist) || dist < 0.5) return null;

    const arcHeight = Math.min(Math.max(dist * 0.18, 1.2), 4.0);
    const midVec = new THREE.Vector3()
      .addVectors(startVec, endVec)
      .multiplyScalar(0.5);
    midVec.y = Math.max(startVec.y, endVec.y) + arcHeight;

    const curve = new THREE.QuadraticBezierCurve3(startVec, midVec, endVec);
    const curvePoints = curve.getPoints(24).map((p) => [p.x, p.y, p.z] as [number, number, number]);

    // Calculate tangent near end for cone orientation
    const tangent = curve.getTangent(0.96).normalize();
    const coneQuat = new THREE.Quaternion().setFromUnitVectors(
      new THREE.Vector3(0, 1, 0),
      tangent
    );

    return {
      curve,
      curvePoints,
      endVec,
      coneQuat,
    };
  }, [flow.from_zone, flow.to_zone, zones]);

  useFrame((state) => {
    if (!particleRef.current || !flowGeometry) return;
    const speed = flow.is_bottleneck_flow ? 0.35 : 0.65;
    const t = (state.clock.getElapsedTime() * speed) % 1;
    const pt = flowGeometry.curve.getPoint(t);
    particleRef.current.position.copy(pt);
  });

  if (!flowGeometry) return null;

  const color = flow.is_bottleneck_flow ? "#ff3b3b" : "#00e5ff";

  return (
    <group>
      <Line
        points={flowGeometry.curvePoints}
        color={color}
        lineWidth={2.2}
        transparent
        opacity={0.85}
      />
      {/* Animated Moving Flow Particle */}
      <mesh ref={particleRef}>
        <sphereGeometry args={[0.18, 10, 10]} />
        <meshStandardMaterial color="#ffffff" emissive={color} emissiveIntensity={2} />
      </mesh>
      {/* Arrowhead Cone */}
      <mesh position={flowGeometry.endVec} quaternion={flowGeometry.coneQuat}>
        <coneGeometry args={[0.24, 0.55, 10]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={1.1} />
      </mesh>
    </group>
  );
};

// ─── Zone Label ───────────────────────────────────────────────────────────────

const ZoneLabel: FC<{ label: SceneLabel }> = ({ label }) => {
  const pos = safeVec3(label.position, [0, 5, 0]);
  const size = safeNum(label.font_size, 0.5);
  if (!label.text) return null;

  return (
    <Text
      position={pos}
      fontSize={size}
      color="#e2f1ff"
      anchorX="center"
      anchorY="middle"
      maxWidth={8}
      textAlign="center"
      outlineWidth={0.04}
      outlineColor="#040814"
    >
      {String(label.text)}
    </Text>
  );
};

// ─── Dark Factory Ground ──────────────────────────────────────────────────────

const FactoryGround: FC<{
  width: number;
  depth: number;
  center: [number, number, number];
}> = ({ width, depth, center }) => {
  const w = Math.min(Math.max(safeNum(width, 30) * 1.5, 45), 110);
  const d = Math.min(Math.max(safeNum(depth, 20) * 1.8, 35), 90);

  return (
    <group position={[center[0], 0, center[2]]}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.05, 0]}>
        <planeGeometry args={[w, d]} />
        <meshStandardMaterial color="#071020" roughness={0.92} metalness={0.12} />
      </mesh>
      <Grid
        position={[0, 0.01, 0]}
        args={[w, d]}
        cellSize={2.5}
        cellThickness={0.4}
        cellColor="#0f2547"
        sectionSize={10}
        sectionThickness={0.8}
        sectionColor="#163e73"
        fadeDistance={75}
        fadeStrength={1.2}
      />
    </group>
  );
};

// ─── Camera Rig Controller ────────────────────────────────────────────────────

const CameraController: FC<{
  cameraPos: [number, number, number];
  cameraTarget: [number, number, number];
  viewPreset: "iso" | "top";
  resetSignal: number;
}> = ({ cameraPos, cameraTarget, viewPreset, resetSignal }) => {
  const controlsRef = useRef<OrbitControlsImpl>(null);
  const { camera } = useThree();

  // Memoize initial target vector so OrbitControls doesn't reset on every render
  const initialTarget = useMemo(
    () => new THREE.Vector3(cameraTarget[0], cameraTarget[1], cameraTarget[2]),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [cameraTarget[0], cameraTarget[1], cameraTarget[2]]
  );

  useEffect(() => {
    if (!controlsRef.current) return;
    if (viewPreset === "top") {
      camera.position.set(cameraTarget[0], 45, cameraTarget[2] + 0.01);
    } else {
      camera.position.set(cameraPos[0], cameraPos[1], cameraPos[2]);
    }
    controlsRef.current.target.set(cameraTarget[0], cameraTarget[1], cameraTarget[2]);
    controlsRef.current.update();
  }, [viewPreset, resetSignal, camera, cameraPos, cameraTarget]);

  return (
    <OrbitControls
      ref={controlsRef}
      enableDamping
      dampingFactor={0.07}
      minDistance={6}
      maxDistance={150}
      maxPolarAngle={Math.PI / 2.04}
      target={initialTarget}
    />
  );
};

// ─── Scene ────────────────────────────────────────────────────────────────────

const FactoryScene: FC<{
  scene: SceneDescriptor;
  selectedZoneId?: string | null;
  onZoneClick: (z: SceneZone | null) => void;
  showFlows: boolean;
  showLabels: boolean;
  viewPreset: "iso" | "top";
  resetSignal: number;
}> = ({
  scene,
  selectedZoneId,
  onZoneClick,
  showFlows,
  showLabels,
  viewPreset,
  resetSignal,
}) => {
  const camPos = safeVec3(scene.camera_position, [30, 25, 30]);
  const camTarget = safeVec3(scene.camera_target, [0, 0, 0]);

  const zones = Array.isArray(scene.zones) ? scene.zones : [];
  const machines = Array.isArray(scene.machines) ? scene.machines : [];
  const flows = Array.isArray(scene.flows) ? scene.flows : [];
  const labels = Array.isArray(scene.labels) ? scene.labels : [];

  return (
    <>
      <ambientLight intensity={0.6} color="#385d96" />
      <directionalLight position={[20, 35, 20]} intensity={1.25} color="#e0f2fe" />
      <pointLight position={[-12, 20, -10]} intensity={0.9} color="#00e5ff" distance={70} />

      <FactoryGround
        width={scene.factory_width}
        depth={scene.factory_depth}
        center={camTarget}
      />

      {zones.map((zone) => (
        <FactoryZone
          key={zone.id}
          zone={zone}
          isSelected={selectedZoneId === zone.id}
          onZoneClick={onZoneClick}
        />
      ))}

      {machines.map((machine) => (
        <MachineObject key={machine.id} machine={machine} />
      ))}

      {showFlows &&
        flows.map((flow) => (
          <FlowArrow key={flow.id} flow={flow} zones={zones} />
        ))}

      {showLabels &&
        labels.map((label) => <ZoneLabel key={label.id} label={label} />)}

      <CameraController
        cameraPos={camPos}
        cameraTarget={camTarget}
        viewPreset={viewPreset}
        resetSignal={resetSignal}
      />
    </>
  );
};

// ─── Main Export ──────────────────────────────────────────────────────────────

const FactoryCanvas: FC<FactoryCanvasProps> = ({
  scene,
  selectedZoneId,
  onZoneClick,
}) => {
  const [mounted, setMounted] = useState(false);
  const [contextKey, setContextKey] = useState(0);
  const [contextLost, setContextLost] = useState(false);
  const [showFlows, setShowFlows] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [viewPreset, setViewPreset] = useState<"iso" | "top">("iso");
  const [resetSignal, setResetSignal] = useState(0);

  const canvasContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    const container = canvasContainerRef.current;
    if (!container) return;

    const handleContextLost = (e: Event) => {
      e.preventDefault();
      console.warn("[FactoryCanvas] WebGL context lost — showing recovery UI");
      setContextLost(true);
    };

    const handleContextRestored = () => {
      setContextLost(false);
    };

    const attachListeners = (canvas: HTMLCanvasElement) => {
      canvas.addEventListener("webglcontextlost", handleContextLost);
      canvas.addEventListener("webglcontextrestored", handleContextRestored);
    };

    const existing = container.querySelector("canvas");
    if (existing) attachListeners(existing);

    const observer = new MutationObserver(() => {
      const c = container.querySelector("canvas");
      if (c) {
        attachListeners(c);
        observer.disconnect();
      }
    });

    observer.observe(container, { childList: true, subtree: true });

    return () => {
      observer.disconnect();
      const c = container.querySelector("canvas");
      if (c) {
        c.removeEventListener("webglcontextlost", handleContextLost);
        c.removeEventListener("webglcontextrestored", handleContextRestored);
      }
    };
  }, [mounted, contextKey]);

  if (!mounted) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-[#060b16]">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan-500 border-t-transparent" />
      </div>
    );
  }

  if (!scene || typeof scene !== "object") {
    return (
      <div className="flex h-full w-full items-center justify-center bg-[#060b16]">
        <p className="text-slate-400 text-sm">Scene data unavailable</p>
      </div>
    );
  }

  if (contextLost) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-4 bg-[#060b16]">
        <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-6 max-w-sm text-center backdrop-blur-md">
          <p className="text-2xl mb-2">⚠️</p>
          <p className="text-sm font-bold text-amber-400 mb-1">WebGL Context Lost</p>
          <p className="text-xs text-slate-400 leading-relaxed">
            The 3D renderer ran out of GPU resources. Click below to reinitialize.
          </p>
          <button
            onClick={() => {
              setContextLost(false);
              setContextKey((k) => k + 1);
            }}
            className="mt-4 rounded-lg bg-cyan-500/20 border border-cyan-500/30 px-5 py-2 text-xs font-bold text-cyan-300 hover:bg-cyan-500/30 transition-colors"
          >
            Restart 3D View
          </button>
        </div>
      </div>
    );
  }

  const camPos = safeVec3(scene.camera_position, [30, 25, 30]);

  return (
    <div ref={canvasContainerRef} className="relative h-full w-full select-none">
      {/* Floating 3D Viewport Toolbar */}
      <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1.5 rounded-xl border border-white/10 bg-slate-950/75 p-1.5 shadow-2xl backdrop-blur-md">
        <button
          type="button"
          onClick={() => {
            setViewPreset("iso");
            setResetSignal((s) => s + 1);
          }}
          className={`rounded-lg px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider transition-all ${
            viewPreset === "iso"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
              : "text-slate-400 hover:text-white"
          }`}
        >
          3D Orbit
        </button>
        <button
          type="button"
          onClick={() => setViewPreset("top")}
          className={`rounded-lg px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider transition-all ${
            viewPreset === "top"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
              : "text-slate-400 hover:text-white"
          }`}
        >
          2D Top-Down
        </button>
        <div className="h-3.5 w-[1px] bg-white/10 mx-0.5" />
        <button
          type="button"
          onClick={() => setShowFlows((f) => !f)}
          className={`rounded-lg px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider transition-all ${
            showFlows
              ? "bg-white/10 text-white"
              : "text-slate-500 hover:text-slate-300"
          }`}
        >
          Flows
        </button>
        <button
          type="button"
          onClick={() => setShowLabels((l) => !l)}
          className={`rounded-lg px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider transition-all ${
            showLabels
              ? "bg-white/10 text-white"
              : "text-slate-500 hover:text-slate-300"
          }`}
        >
          Labels
        </button>
      </div>

      <Canvas
        key={contextKey}
        dpr={[1, 1.5]}
        camera={{ position: camPos, fov: 45, near: 0.1, far: 600 }}
        gl={{
          antialias: true,
          alpha: false,
          powerPreference: "high-performance",
          failIfMajorPerformanceCaveat: false,
          preserveDrawingBuffer: false,
        }}
        style={{ background: "#060b16", width: "100%", height: "100%" }}
        onPointerMissed={() => onZoneClick(null)}
      >
        <FactoryScene
          scene={scene}
          selectedZoneId={selectedZoneId}
          onZoneClick={onZoneClick}
          showFlows={showFlows}
          showLabels={showLabels}
          viewPreset={viewPreset}
          resetSignal={resetSignal}
        />
      </Canvas>
    </div>
  );
};

export default FactoryCanvas;