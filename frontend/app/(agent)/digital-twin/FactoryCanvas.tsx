"use client";

import { useRef, useState, useEffect, type FC } from "react";
import { Canvas, useFrame, type ThreeEvent } from "@react-three/fiber";
import { OrbitControls, Grid, Text, Line } from "@react-three/drei";
import * as THREE from "three";

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
  if (typeof c === "string" && c.length > 0) return c;
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
    const t = Math.sin(state.clock.getElapsedTime() * 3) * 0.5 + 0.5;
    const mat = ref.current.material as THREE.MeshStandardMaterial;
    mat.emissiveIntensity = t * 1.8;
    const s = 1 + t * 0.05;
    ref.current.scale.set(s, s, s);
  });

  return (
    <mesh ref={ref} position={position}>
      <boxGeometry args={[size[0] + 0.3, size[1] + 0.3, size[2] + 0.3]} />
      <meshStandardMaterial
        color="#dc2626"
        emissive="#ff0000"
        emissiveIntensity={1.2}
        transparent
        opacity={0.15}
      />
    </mesh>
  );
};

// ─── Floor glow under zone ────────────────────────────────────────────────────

const ZoneGlow: FC<{ zone: SceneZone }> = ({ zone }) => {
  const pos = safeVec3(zone.position, [0, 0, 0]);
  const size = safeVec3(zone.size, [4, 3, 4]);
  const col = safeColor(zone.is_bottleneck ? "#ff2222" : zone.color, "#3b82f6");
  return (
    <mesh position={[pos[0], 0.02, pos[2]]} rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={[size[0] * 1.4, size[2] * 1.4]} />
      <meshStandardMaterial color={col} emissive={col} emissiveIntensity={0.35} transparent opacity={0.09} />
    </mesh>
  );
};

// ─── Factory Zone ─────────────────────────────────────────────────────────────

const FactoryZone: FC<{ zone: SceneZone; onZoneClick: (z: SceneZone) => void }> = ({
  zone,
  onZoneClick,
}) => {
  const [hovered, setHovered] = useState(false);
  const meshRef = useRef<THREE.Mesh>(null!);

  const pos  = safeVec3(zone.position, [0, 0, 0]);
  const size = safeVec3(zone.size, [4, 3, 4]);
  const col  = safeColor(zone.color, "#3b82f6");
  const emCol = safeColor(zone.is_bottleneck ? "#ff0000" : (zone.emissive_color || zone.color), col);

  useEffect(() => {
    document.body.style.cursor = hovered ? "pointer" : "auto";
    return () => { document.body.style.cursor = "auto"; };
  }, [hovered]);

  useFrame(() => {
    if (!meshRef.current) return;
    const mat = meshRef.current.material as THREE.MeshStandardMaterial;
    const target = hovered ? 0.9 : zone.is_bottleneck ? 0.55 : 0.18;
    mat.emissiveIntensity = THREE.MathUtils.lerp(mat.emissiveIntensity, target, 0.1);
  });

  return (
    <group>
      <ZoneGlow zone={zone} />
      <mesh
        ref={meshRef}
        position={pos}
        onClick={(e: ThreeEvent<MouseEvent>) => { e.stopPropagation(); onZoneClick(zone); }}
        onPointerOver={(e: ThreeEvent<PointerEvent>) => { e.stopPropagation(); setHovered(true); }}
        onPointerOut={() => setHovered(false)}
      >
        <boxGeometry args={size} />
        <meshStandardMaterial
          color={col}
          emissive={emCol}
          emissiveIntensity={zone.is_bottleneck ? 0.55 : 0.18}
          roughness={0.3}
          metalness={0.55}
          transparent
          opacity={hovered ? 0.95 : 0.85}
        />
      </mesh>

      {zone.is_bottleneck && <BottleneckPulse position={pos} size={size} />}

      {hovered && (
        <mesh position={pos}>
          <boxGeometry args={[size[0] + 0.12, size[1] + 0.12, size[2] + 0.12]} />
          <meshStandardMaterial color="#00e5ff" transparent opacity={0.1} wireframe />
        </mesh>
      )}
    </group>
  );
};

// ─── Machine Object ───────────────────────────────────────────────────────────

const MachineObject: FC<{ machine: SceneMachine }> = ({ machine }) => {
  const ref = useRef<THREE.Mesh>(null!);
  const pos  = safeVec3(machine.position, [0, 0, 0]);
  const size = safeVec3(machine.size, [1, 1, 1]);
  const col  = safeColor(machine.color, "#6b7280");

  useFrame((state) => {
    if (ref.current && machine.shape === "cylinder") {
      ref.current.rotation.y = state.clock.getElapsedTime() * 0.3;
    }
  });

  return (
    <mesh ref={ref} position={pos}>
      {machine.shape === "cylinder" ? (
        <cylinderGeometry args={[size[0] / 2, size[0] / 2, size[1], 12]} />
      ) : (
        <boxGeometry args={size} />
      )}
      <meshStandardMaterial
        color={col}
        roughness={0.25}
        metalness={0.8}
        emissive={col}
        emissiveIntensity={0.2}
      />
    </mesh>
  );
};

// ─── Flow Arrow ───────────────────────────────────────────────────────────────

const FlowArrow: FC<{ flow: SceneFlow; zones: SceneZone[] }> = ({ flow, zones }) => {
  const fromZone = zones.find((z) => z.id === flow.from_zone);
  const toZone   = zones.find((z) => z.id === flow.to_zone);
  if (!fromZone || !toZone) return null;

  const fromPos = safeVec3(fromZone.position, [0, 0, 0]);
  const fromSize = safeVec3(fromZone.size, [4, 3, 4]);
  const toPos   = safeVec3(toZone.position, [0, 0, 0]);
  const toSize  = safeVec3(toZone.size, [4, 3, 4]);

  const startX = fromPos[0] + fromSize[0] / 2;
  const endX   = toPos[0]   - toSize[0]  / 2;
  if (!isFinite(startX) || !isFinite(endX) || startX >= endX) return null;

  const y = 4.2;
  const midX = (startX + endX) / 2;

  const points: [number, number, number][] = [
    [startX, y, 0],
    [midX, y + 0.6, 0],
    [endX, y, 0],
  ];

  const color = flow.is_bottleneck_flow ? "#ff3333" : "#00d4ff";

  return (
    <group>
      <Line points={points} color={color} lineWidth={2} />
      <mesh position={[endX + 0.1, y, 0]} rotation={[0, 0, -Math.PI / 2]}>
        <coneGeometry args={[0.2, 0.5, 8]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={1.0} />
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
      color="#d0e8ff"
      anchorX="center"
      anchorY="middle"
      maxWidth={8}
      textAlign="center"
    >
      {String(label.text)}
    </Text>
  );
};

// ─── Dark Factory Ground ──────────────────────────────────────────────────────

const FactoryGround: FC<{ width: number; depth: number }> = ({ width, depth }) => {
  // Cap dimensions to prevent GPU memory exhaustion causing context loss
  const w = Math.min(safeNum(width, 30) * 1.4, 80);
  const d = Math.min(safeNum(depth, 20) * 2, 60);
  return (
    <>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.05, 0]}>
        <planeGeometry args={[w, d]} />
        <meshStandardMaterial color="#0a1628" roughness={0.9} metalness={0.1} />
      </mesh>
      <Grid
        position={[0, 0.01, 0]}
        args={[w, d]}
        cellSize={3}
        cellThickness={0.3}
        cellColor="#0d2240"
        sectionSize={12}
        sectionThickness={0.6}
        sectionColor="#0e3460"
        fadeDistance={60}
        fadeStrength={1}
      />
    </>
  );
};

// ─── Scene ────────────────────────────────────────────────────────────────────

const FactoryScene: FC<{
  scene: SceneDescriptor;
  onZoneClick: (z: SceneZone | null) => void;
}> = ({ scene, onZoneClick }) => {
  const target = safeVec3(scene.camera_target, [0, 0, 0]);
  const camTarget = new THREE.Vector3(...target);

  const zones    = Array.isArray(scene.zones)    ? scene.zones    : [];
  const machines = Array.isArray(scene.machines) ? scene.machines : [];
  const flows    = Array.isArray(scene.flows)    ? scene.flows    : [];
  const labels   = Array.isArray(scene.labels)   ? scene.labels   : [];

  return (
    <>
      {/* Simplified lighting — fewer lights = less GPU pressure */}
      <ambientLight intensity={0.5} color="#2a4a7a" />
      <directionalLight position={[15, 30, 15]} intensity={1.1} color="#d0e8ff" />
      <pointLight position={[-10, 18, -8]} intensity={0.8} color="#00bcd4" distance={60} />

      <FactoryGround width={scene.factory_width} depth={scene.factory_depth} />

      {zones.map((zone) => (
        <FactoryZone key={zone.id} zone={zone} onZoneClick={onZoneClick} />
      ))}

      {machines.map((machine) => (
        <MachineObject key={machine.id} machine={machine} />
      ))}

      {flows.map((flow) => (
        <FlowArrow key={flow.id} flow={flow} zones={zones} />
      ))}

      {labels.map((label) => (
        <ZoneLabel key={label.id} label={label} />
      ))}

      <OrbitControls
        enableDamping
        dampingFactor={0.06}
        minDistance={8}
        maxDistance={160}
        maxPolarAngle={Math.PI / 2.05}
        target={camTarget}
      />
    </>
  );
};

// ─── Main Export ──────────────────────────────────────────────────────────────

const FactoryCanvas: FC<FactoryCanvasProps> = ({ scene, onZoneClick }) => {
  const [mounted, setMounted] = useState(false);
  const [contextKey, setContextKey] = useState(0);          // bump to force re-mount
  const [contextLost, setContextLost] = useState(false);
  const canvasContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMounted(true);

    const orig = console.warn.bind(console);
    console.warn = (...args: unknown[]) => {
      const msg = typeof args[0] === "string" ? args[0] : "";
      if (msg.includes("THREE.Clock") || msg.includes("PCFSoftShadowMap")) return;
      orig(...args);
    };
    return () => { console.warn = orig; };
  }, []);

  // Listen for WebGL context loss on the canvas DOM element
  useEffect(() => {
    const container = canvasContainerRef.current;
    if (!container) return;

    const handleContextLost = (e: Event) => {
      e.preventDefault();
      console.warn("[FactoryCanvas] WebGL context lost — will attempt recovery");
      setContextLost(true);
    };

    const handleContextRestored = () => {
      console.info("[FactoryCanvas] WebGL context restored");
      setContextLost(false);
    };

    // The actual <canvas> is a child of our wrapper div
    const observer = new MutationObserver(() => {
      const canvas = container.querySelector("canvas");
      if (canvas) {
        canvas.addEventListener("webglcontextlost", handleContextLost);
        canvas.addEventListener("webglcontextrestored", handleContextRestored);
        observer.disconnect();
      }
    });

    observer.observe(container, { childList: true, subtree: true });

    // Also check if canvas is already present
    const existing = container.querySelector("canvas");
    if (existing) {
      existing.addEventListener("webglcontextlost", handleContextLost);
      existing.addEventListener("webglcontextrestored", handleContextRestored);
      observer.disconnect();
    }

    return () => {
      observer.disconnect();
      const canvas = container.querySelector("canvas");
      if (canvas) {
        canvas.removeEventListener("webglcontextlost", handleContextLost);
        canvas.removeEventListener("webglcontextrestored", handleContextRestored);
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

  // Context lost — show recovery UI
  if (contextLost) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-4 bg-[#060b16]">
        <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-6 max-w-sm text-center">
          <p className="text-2xl mb-2">⚠️</p>
          <p className="text-sm font-bold text-amber-400 mb-1">WebGL Context Lost</p>
          <p className="text-xs text-slate-400 leading-relaxed">
            The 3D renderer ran out of GPU resources. Click below to reinitialise.
          </p>
          <button
            onClick={() => { setContextLost(false); setContextKey((k) => k + 1); }}
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
    <div ref={canvasContainerRef} style={{ width: "100%", height: "100%" }}>
      <Canvas
        key={contextKey}
        camera={{ position: camPos, fov: 45, near: 0.1, far: 600 }}
        gl={{
          antialias: true,
          alpha: false,
          powerPreference: "default",
          failIfMajorPerformanceCaveat: false,
          preserveDrawingBuffer: true,
        }}
        style={{ background: "#060b16", width: "100%", height: "100%" }}
        onPointerMissed={() => onZoneClick(null)}
      >
        <FactoryScene scene={scene} onZoneClick={onZoneClick} />
      </Canvas>
    </div>
  );
};

export default FactoryCanvas;

