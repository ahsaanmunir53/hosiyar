import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { BANDS, bandLines, shieldOutline } from "./geometry";

export type SealStatus = "idle" | "scanning" | "likely_scam" | "suspicious" | "no_red_flags";

const TINTS: Record<SealStatus, string> = {
  idle: "#9fe3c8",
  scanning: "#b9f0dc",
  no_red_flags: "#5ccfa5",
  suspicious: "#e7b54c",
  likely_scam: "#f2668c",
};

const vertexShader = /* glsl */ `
  attribute float aParam;
  uniform float uTime;
  uniform float uGlitch;
  varying float vParam;
  varying float vY;
  void main() {
    vParam = aParam;
    vec3 p = position;
    float n = sin(aParam * 211.0 + uTime * 23.0) * sin(aParam * 97.0 - uTime * 17.0);
    p.xy += normalize(p.xy + 0.0001) * n * uGlitch * 0.06;
    vec4 world = modelMatrix * vec4(p, 1.0);
    vY = world.y;
    gl_Position = projectionMatrix * viewMatrix * world;
  }
`;

const fragmentShader = /* glsl */ `
  uniform float uTime;
  uniform vec3 uTint;
  uniform float uTintMix;
  uniform float uScan;
  uniform float uScanOn;
  uniform float uHue;
  uniform float uOpacity;
  varying float vParam;
  varying float vY;
  // Holographic foil: teal, gold and rose, shifting along the line and over time.
  vec3 foil(float t) {
    vec3 a = vec3(0.62, 0.70, 0.62);
    vec3 b = vec3(0.30, 0.22, 0.26);
    vec3 c = vec3(1.0, 1.0, 1.0);
    vec3 d = vec3(0.05, 0.33, 0.62);
    return a + b * cos(6.28318 * (c * t + d));
  }
  void main() {
    vec3 col = foil(vParam * 3.0 + uTime * 0.04 + uHue);
    col = mix(col, uTint, uTintMix);
    float beam = uScanOn * smoothstep(0.22, 0.0, abs(vY - uScan));
    col += beam * vec3(0.9, 1.0, 0.95);
    gl_FragColor = vec4(col, uOpacity + beam * 0.5);
  }
`;

function Rings({ status, still }: { status: SealStatus; still: boolean }) {
  const group = useRef<THREE.Group>(null);
  const spread = useRef(0);
  const glitch = useRef(0);
  const speedMult = useRef(1);
  const tint = useRef(new THREE.Color(TINTS.idle));
  const tintMix = useRef(0);
  const prevStatus = useRef<SealStatus>(status);

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uTint: { value: new THREE.Color(TINTS.idle) },
      uTintMix: { value: 0 },
      uScan: { value: -3 },
      uScanOn: { value: 0 },
      uGlitch: { value: 0 },
    }),
    [],
  );

  const rings = useMemo(
    () =>
      BANDS.flatMap((spec, bandIndex) =>
        bandLines(spec).map((data, lineIndex) => {
          const geometry = new THREE.BufferGeometry();
          geometry.setAttribute("position", new THREE.BufferAttribute(data.positions, 3));
          geometry.setAttribute("aParam", new THREE.BufferAttribute(data.params, 1));
          const material = new THREE.ShaderMaterial({
            vertexShader,
            fragmentShader,
            uniforms: { ...uniforms, uHue: { value: bandIndex * 0.21 }, uOpacity: { value: spec.opacity } },
            transparent: true,
            depthWrite: false,
            blending: THREE.AdditiveBlending,
          });
          const line = new THREE.LineLoop(geometry, material);
          return { spec, line, baseZ: spec.z, index: bandIndex, key: `${bandIndex}-${lineIndex}` };
        }),
      ),
    [uniforms],
  );

  useEffect(
    () => () =>
      rings.forEach(({ line }) => {
        line.geometry.dispose();
        (line.material as THREE.Material).dispose();
      }),
    [rings],
  );

  useEffect(() => {
    if (status === "likely_scam" && prevStatus.current !== "likely_scam") glitch.current = 1;
    prevStatus.current = status;
  }, [status]);

  useFrame((state, delta) => {
    const dt = still ? 0 : Math.min(delta, 0.05);
    const scanning = status === "scanning";
    const verdict = status !== "idle" && !scanning;

    const targetSpeed = scanning ? 4.5 : status === "no_red_flags" ? 0.6 : status === "likely_scam" ? 1.4 : 1;
    speedMult.current = THREE.MathUtils.damp(speedMult.current, targetSpeed, 3, dt || 1);
    spread.current = THREE.MathUtils.damp(spread.current, status === "likely_scam" ? 1 : 0, 2.5, dt || 1);
    glitch.current = still ? 0 : Math.max(0, glitch.current - dt * 0.9);
    tint.current.lerp(new THREE.Color(TINTS[status]), still ? 1 : 1 - Math.exp(-4 * dt));
    tintMix.current = THREE.MathUtils.damp(tintMix.current, verdict ? 0.78 : scanning ? 0.2 : 0, 3, dt || 1);

    uniforms.uTime.value += dt * speedMult.current;
    uniforms.uTint.value.copy(tint.current);
    uniforms.uTintMix.value = tintMix.current;
    uniforms.uGlitch.value = glitch.current + (status === "likely_scam" ? 0.08 : 0);
    uniforms.uScanOn.value = THREE.MathUtils.damp(uniforms.uScanOn.value, scanning ? 1 : 0, 6, dt || 1);
    uniforms.uScan.value = Math.sin(state.clock.elapsedTime * 2.1) * 2.1;

    rings.forEach(({ spec, line, baseZ, index }) => {
      line.rotation.z += spec.speed * dt * speedMult.current;
      const dir = index % 2 === 0 ? 1 : -1;
      line.position.z = baseZ + spread.current * dir * (0.2 + index * 0.16);
    });

    if (group.current) {
      const wobble = status === "suspicious" && !still ? Math.sin(state.clock.elapsedTime * 1.6) * 0.06 : 0;
      const px = still ? 0 : state.pointer.y * 0.25;
      const py = still ? 0 : state.pointer.x * 0.35;
      group.current.rotation.x = THREE.MathUtils.damp(group.current.rotation.x, -0.18 + px, 3, dt || 1);
      group.current.rotation.y = THREE.MathUtils.damp(group.current.rotation.y, 0.22 + py + wobble, 3, dt || 1);
    }
  });

  return (
    <group ref={group} rotation={[-0.18, 0.22, 0]}>
      {rings.map(({ line, key }) => (
        <primitive key={key} object={line} />
      ))}
      <Shield status={status} still={still} />
    </group>
  );
}

function glyphCurves(status: SealStatus): THREE.Curve<THREE.Vector3>[] {
  const v = (x: number, y: number) => new THREE.Vector3(x, y, 0);
  if (status === "no_red_flags") {
    const path = new THREE.CurvePath<THREE.Vector3>();
    path.add(new THREE.LineCurve3(v(-0.22, 0.02), v(-0.05, -0.16)));
    path.add(new THREE.LineCurve3(v(-0.05, -0.16), v(0.26, 0.2)));
    return [path];
  }
  if (status === "likely_scam") {
    return [new THREE.LineCurve3(v(-0.19, 0.19), v(0.19, -0.19)), new THREE.LineCurve3(v(-0.19, -0.19), v(0.19, 0.19))];
  }
  if (status === "suspicious") {
    return [new THREE.LineCurve3(v(0, 0.26), v(0, -0.08)), new THREE.LineCurve3(v(0, -0.2), v(0, -0.215))];
  }
  return [];
}

function Shield({ status, still }: { status: SealStatus; still: boolean }) {
  const mesh = useRef<THREE.Mesh>(null);
  const material = useMemo(
    () =>
      new THREE.MeshPhysicalMaterial({
        color: new THREE.Color("#dfe9e2"),
        metalness: 0.92,
        roughness: 0.26,
        clearcoat: 1,
        clearcoatRoughness: 0.15,
        iridescence: 1,
        iridescenceIOR: 1.4,
        iridescenceThicknessRange: [180, 620],
      }),
    [],
  );
  const geometry = useMemo(() => {
    const shape = new THREE.Shape();
    shieldOutline().forEach(([x, y], i) => (i === 0 ? shape.moveTo(x, y) : shape.lineTo(x, y)));
    const g = new THREE.ExtrudeGeometry(shape, {
      depth: 0.16,
      bevelEnabled: true,
      bevelThickness: 0.06,
      bevelSize: 0.05,
      bevelSegments: 6,
      curveSegments: 24,
    });
    g.center();
    return g;
  }, []);
  const glyphMaterial = useMemo(
    () => new THREE.MeshStandardMaterial({ color: "#0c2420", emissive: new THREE.Color(TINTS.idle), emissiveIntensity: 0.9, roughness: 0.4 }),
    [],
  );
  const glyphs = useMemo(
    () => glyphCurves(status).map((c) => new THREE.TubeGeometry(c, 32, 0.045, 10, false)),
    [status],
  );

  useEffect(() => () => glyphs.forEach((g) => g.dispose()), [glyphs]);
  useEffect(
    () => () => {
      geometry.dispose();
      material.dispose();
      glyphMaterial.dispose();
    },
    [geometry, material, glyphMaterial],
  );

  useFrame((state, delta) => {
    const dt = still ? 1 : Math.min(delta, 0.05);
    const target = new THREE.Color(status === "idle" || status === "scanning" ? "#dfe9e2" : TINTS[status]).lerp(new THREE.Color("#ffffff"), 0.35);
    material.color.lerp(target, 1 - Math.exp(-3 * dt));
    glyphMaterial.emissive.lerp(new THREE.Color(TINTS[status]), 1 - Math.exp(-4 * dt));
    if (mesh.current && !still) {
      mesh.current.position.y = Math.sin(state.clock.elapsedTime * 0.8) * 0.03;
    }
  });

  return (
    <group scale={0.82} position={[0, 0.04, 0.2]}>
      <mesh ref={mesh} geometry={geometry} material={material} />
      <group position={[0, 0.06, 0.2]}>
        {glyphs.map((g, i) => (
          <mesh key={`${status}-${i}`} geometry={g} material={glyphMaterial} />
        ))}
      </group>
    </group>
  );
}

function Environment() {
  const { gl, scene } = useThree();
  useEffect(() => {
    const pmrem = new THREE.PMREMGenerator(gl);
    const env = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = env;
    return () => {
      scene.environment = null;
      env.dispose();
      pmrem.dispose();
    };
  }, [gl, scene]);
  return null;
}

function Invalidate({ status }: { status: SealStatus }) {
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    invalidate();
    const id = setTimeout(invalidate, 50);
    return () => clearTimeout(id);
  }, [status, invalidate]);
  return null;
}

export default function Seal3D({ status, reducedMotion }: { status: SealStatus; reducedMotion: boolean }) {
  return (
    <Canvas
      dpr={[1, 1.75]}
      camera={{ position: [0, 0, 6.7], fov: 40 }}
      gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      frameloop={reducedMotion ? "demand" : "always"}
      aria-hidden="true"
    >
      <Environment />
      <ambientLight intensity={0.35} />
      <directionalLight position={[2.5, 3, 4]} intensity={1.4} />
      <directionalLight position={[-3, -2, 2]} intensity={0.5} color="#9fe3c8" />
      <Rings status={status} still={reducedMotion} />
      {reducedMotion && <Invalidate status={status} />}
    </Canvas>
  );
}
