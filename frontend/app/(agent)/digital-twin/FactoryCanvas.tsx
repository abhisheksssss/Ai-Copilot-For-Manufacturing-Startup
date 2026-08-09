"use client";

import { useRef, useState, useEffect, type FC } from "react";
import { Canvas, useFrame, type ThreeEvent } from "@react-three/fiber";
import { OrbitControls, Grid, Environment, Float, Text, Line } from "@react-three/drei";
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

// ─── Bottleneck Pulse ─────────────────────────────────────────────────────────

const BottleneckPulse: FC<{ position: [number, number, number]; size: [number, number, number] }> = ({
  position,
  size,
}) => {
  const ref = useRef<THREE.Mesh>(null!);

  useFrame((state) => {
    if (!ref.current) return;
    const t = Math.sin(state.clock.elapsedTime * 3) * 0.5 + 0.5;
    (ref.current.material as THREE.MeshStandardMaterial).emissiveIntensity = t * 1.5;
    const s = 1 + t * 0.04;
    ref.current.scale.set(s, s, s);
  });

  return (
    <mesh ref={ref} position={position}>
      <boxGeometry args={[size[0] + 0.2, size[1] + 0.2, size[2] + 0.2]} />
      <meshStandardMaterial
        color="#dc2626"
        emissive="#ef4444"
        emissiveIntensity={1.0}
        transparent
        opacity={0.2}
      />
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

  useEffect(() => {
    document.body.style.cursor = hovered ? "pointer" : "auto";
    return () => { document.body.style.cursor = "auto"; };
  }, [hovered]);

  useFrame(() => {
    if (!meshRef.current) return;
    const mat = meshRef.current.material as THREE.MeshStandardMaterial;
    mat.emissiveIntensity = THREE.MathUtils.lerp(
      mat.emissiveIntensity,
      hovered ? 0.8 : zone.is_bottleneck ? 0.4 : 0.1,
      0.1
    );
  });

  return (
    <group>
      <mesh
        ref={meshRef}
        position={zone.position}
        onClick={(e: ThreeEvent<MouseEvent>) => { e.stopPropagation(); onZoneClick(zone); }}
        onPointerOver={(e: ThreeEvent<PointerEvent>) => { e.stopPropagation(); setHovered(true); }}
        onPointerOut={() => setHovered(false)}
      >
        <boxGeometry args={zone.size} />
        <meshStandardMaterial
          color={zone.color}
          emissive={zone.is_bottleneck ? "#991b1b" : zone.color}
          emissiveIntensity={zone.is_bottleneck ? 0.4 : 0.1}
          roughness={0.4}
          metalness={0.2}
          transparent
          opacity={hovered ? 0.95 : 0.88}
        />
      </mesh>

      {zone.is_bottleneck && <BottleneckPulse position={zone.position} size={zone.size} />}

      {hovered && (
        <mesh position={zone.position}>
          <boxGeometry args={[zone.size[0] + 0.08, zone.size[1] + 0.08, zone.size[2] + 0.08]} />
          <meshStandardMaterial color="#0f172a" transparent opacity={0.15} wireframe />
        </mesh>
      )}
    </group>
  );
};

// ─── Machine Object ───────────────────────────────────────────────────────────

const MachineObject: FC<{ machine: SceneMachine }> = ({ machine }) => {
  const ref = useRef<THREE.Mesh>(null!);

  useFrame((state) => {
    if (ref.current && machine.shape === "cylinder") {
      ref.current.rotation.y = state.clock.elapsedTime * 0.3;
    }
  });

  return (
    <mesh ref={ref} position={machine.position}>
      {machine.shape === "cylinder" ? (
        <cylinderGeometry args={[machine.size[0] / 2, machine.size[0] / 2, machine.size[1], 12]} />
      ) : (
        <boxGeometry args={machine.size} />
      )}
      <meshStandardMaterial
        color={machine.color}
        roughness={0.4}
        metalness={0.6}
        emissive={machine.color}
        emissiveIntensity={0.15}
      />
    </mesh>
  );
};

// ─── Flow Arrow ───────────────────────────────────────────────────────────────

const FlowArrow: FC<{ flow: SceneFlow; zones: SceneZone[] }> = ({ flow, zones }) => {
  const fromZone = zones.find((z) => z.id === flow.from_zone);
  const toZone = zones.find((z) => z.id === flow.to_zone);
  if (!fromZone || !toZone) return null;

  const startX = fromZone.position[0] + fromZone.size[0] / 2;
  const endX = toZone.position[0] - toZone.size[0] / 2;
  const y = 3.8;

  const points: [number, number, number][] = [
    [startX, y, 0],
    [(startX + endX) / 2, y + 0.5, 0],
    [endX, y, 0],
  ];

  const color = flow.is_bottleneck_flow ? "#dc2626" : "#059669";

  return (
    <group>
      <Line points={points} color={color} lineWidth={2.5} />
      <mesh position={[endX + 0.1, y, 0]} rotation={[0, 0, -Math.PI / 2]}>
        <coneGeometry args={[0.2, 0.5, 8]} />
        <meshStandardMaterial color={color} />
      </mesh>
    </group>
  );
};

// ─── Zone Label ───────────────────────────────────────────────────────────────

const ZoneLabel: FC<{ label: SceneLabel }> = ({ label }) => {
  // Ensure label text has strong contrast on light ground
  const labelColor = label.color === "#ffffff" || label.color === "#f8fafc" ? "#1e293b" : label.color;

  return (
    <Float speed={1.5} rotationIntensity={0} floatIntensity={0.2}>
      <Text
        position={label.position}
        fontSize={label.font_size}
        color={labelColor}
        anchorX="center"
        anchorY="middle"
        maxWidth={8}
        textAlign="center"
      >
        {label.text}
      </Text>
    </Float>
  );
};

// ─── Ground ───────────────────────────────────────────────────────────────────

const FactoryGround: FC<{ width: number; depth: number }> = ({ width, depth }) => (
  <>
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.05, 0]}>
      <planeGeometry args={[width * 1.5, depth * 2.5]} />
      <meshStandardMaterial color="#f1f5f9" roughness={0.8} metalness={0.1} />
    </mesh>
    <Grid
      position={[0, 0, 0]}
      args={[width * 1.5, depth * 2.5]}
      cellSize={2}
      cellThickness={0.5}
      cellColor="#cbd5e1"
      sectionSize={10}
      sectionThickness={1.2}
      sectionColor="#94a3b8"
      fadeDistance={90}
      fadeStrength={1}
    />
  </>
);

// ─── Scene ────────────────────────────────────────────────────────────────────

const FactoryScene: FC<{ scene: SceneDescriptor; onZoneClick: (z: SceneZone | null) => void }> = ({
  scene,
  onZoneClick,
}) => {
  const camTarget = new THREE.Vector3(...scene.camera_target);

  return (
    <>
      <ambientLight intensity={0.7} />
      <directionalLight position={[20, 30, 20]} intensity={1.4} castShadow />
      <pointLight position={[-20, 20, -10]} intensity={0.5} color="#0284c7" />
      <pointLight position={[20, 10, 20]} intensity={0.4} color="#059669" />

      <Environment preset="studio" />

      <FactoryGround width={scene.factory_width} depth={scene.factory_depth} />

      {scene.zones.map((zone) => (
        <FactoryZone key={zone.id} zone={zone} onZoneClick={onZoneClick} />
      ))}

      {scene.machines.map((machine) => (
        <MachineObject key={machine.id} machine={machine} />
      ))}

      {scene.flows.map((flow) => (
        <FlowArrow key={flow.id} flow={flow} zones={scene.zones} />
      ))}

      {scene.labels.map((label) => (
        <ZoneLabel key={label.id} label={label} />
      ))}

      <OrbitControls
        enableDamping
        dampingFactor={0.05}
        minDistance={10}
        maxDistance={120}
        maxPolarAngle={Math.PI / 2.05}
        target={camTarget}
      />
    </>
  );
};

// ─── Main Export ──────────────────────────────────────────────────────────────

const FactoryCanvas: FC<FactoryCanvasProps> = ({ scene, onZoneClick }) => {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-slate-50">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan-600 border-t-transparent" />
      </div>
    );
  }

  return (
    <Canvas
      shadows
      camera={{ position: scene.camera_position, fov: 45, near: 0.1, far: 500 }}
      gl={{ antialias: true, alpha: false }}
      style={{ background: "#f8fafc", width: "100%", height: "100%" }}
      onPointerMissed={() => onZoneClick(null)}
    >
      <FactoryScene scene={scene} onZoneClick={onZoneClick} />
    </Canvas>
  );
};

export default FactoryCanvas;

