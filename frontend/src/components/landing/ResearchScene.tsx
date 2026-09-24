import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import type { MotionValue } from "framer-motion";
import {
  CLUSTER_COLORS, PALETTE, STAGES, TUNE, sampleCamera, win,
} from "./scene/research-config";
import { buildGraph } from "./scene/research-graph";
import {
  CORE_FRAG, CORE_VERT, DUST_FRAG, DUST_VERT, EDGE_FRAG, EDGE_VERT,
  HALO_FRAG, HALO_VERT, NODE_FRAG, NODE_VERT,
} from "./scene/research-shaders";

/**
 * Contract (consumed by Landing.tsx via React.lazy): a fixed full-viewport R3F
 * canvas visualising a research run as a growing knowledge graph.
 * `progress` is a 0..1 MotionValue of page scroll.
 */
export interface ResearchSceneProps {
  progress: MotionValue<number>;
}

const col = (hex: string) => new THREE.Color(hex);

function makeUniforms() {
  const u = <T,>(v: T) => ({ value: v });
  return {
    uP: u(0), uTime: u(0), uContract: u(0), uDrift: u(1), uScale: u(600),
    uSearch: u(0), uRead: u(0), uCheck: u(0), uAmber: u(0), uResolve: u(0),
    uAnswer: u(0), uPulse: u(TUNE.pulseSpeed),
    uC0: u(col(CLUSTER_COLORS[0])), uC1: u(col(CLUSTER_COLORS[1])), uC2: u(col(CLUSTER_COLORS[2])),
    uGreen: u(col(PALETTE.green)), uMint: u(col(PALETTE.mint)),
    uAmberCol: u(col(PALETTE.amber)), uDustCol: u(col(PALETTE.dust)),
  };
}

type Uniforms = ReturnType<typeof makeUniforms>;

function mat(vs: string, fs: string, uniforms: Uniforms) {
  return new THREE.ShaderMaterial({
    vertexShader: vs, fragmentShader: fs, uniforms: uniforms as unknown as Record<string, THREE.IUniform>,
    transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending,
  });
}

function attr(g: THREE.BufferGeometry, name: string, arr: Float32Array, size: number) {
  g.setAttribute(name, new THREE.BufferAttribute(arr, size));
}

function Graph({ progress, reduced }: { progress: MotionValue<number>; reduced: boolean }) {
  const { camera, gl, size } = useThree();
  const uniforms = useMemo(makeUniforms, []);
  const data = useMemo(buildGraph, []);
  const state = useRef({ p: -1, time: 0, mx: 0, my: 0, tmx: 0, tmy: 0 });

  const { nodeGeo, edgeGeo, dustGeo, haloGeo, coreGeo, wireGeo } = useMemo(() => {
    const nodeGeo = new THREE.BufferGeometry();
    attr(nodeGeo, "position", data.nPos, 3);
    attr(nodeGeo, "aPar", data.nPar, 3);
    attr(nodeGeo, "aNode", data.nNode, 4);
    attr(nodeGeo, "aInfo", data.nInfo, 4);
    const edgeGeo = new THREE.BufferGeometry();
    attr(edgeGeo, "position", data.ePos, 3);
    attr(edgeGeo, "aPar", data.ePar, 3);
    attr(edgeGeo, "aNode", data.eNode, 4);
    attr(edgeGeo, "aEdge", data.eEdge, 4);
    const dustGeo = new THREE.BufferGeometry();
    const dp = new Float32Array((data.dust.length / 4) * 3);
    const ds = new Float32Array(data.dust.length / 4);
    for (let i = 0; i < ds.length; i++) {
      dp.set([data.dust[i * 4], data.dust[i * 4 + 1], data.dust[i * 4 + 2]], i * 3);
      ds[i] = data.dust[i * 4 + 3];
    }
    attr(dustGeo, "position", dp, 3);
    attr(dustGeo, "aSeed", ds, 1);
    const haloGeo = new THREE.BufferGeometry();
    attr(haloGeo, "position", new Float32Array([0, 0, 0]), 3);
    const coreGeo = new THREE.IcosahedronGeometry(0.62, 1);
    const wireGeo = new THREE.EdgesGeometry(new THREE.IcosahedronGeometry(0.95, 1));
    return { nodeGeo, edgeGeo, dustGeo, haloGeo, coreGeo, wireGeo };
  }, [data]);

  const mats = useMemo(() => ({
    node: mat(NODE_VERT, NODE_FRAG, uniforms),
    edge: mat(EDGE_VERT, EDGE_FRAG, uniforms),
    dust: mat(DUST_VERT, DUST_FRAG, uniforms),
    core: mat(CORE_VERT, CORE_FRAG, uniforms),
    halo: mat(HALO_VERT, HALO_FRAG, uniforms),
    wire: new THREE.LineBasicMaterial({
      color: PALETTE.mint, transparent: true, opacity: 0, depthWrite: false,
      depthTest: false, blending: THREE.AdditiveBlending,
    }),
  }), [uniforms]);

  useEffect(() => {
    if (reduced) return;
    const onMove = (e: PointerEvent) => {
      state.current.tmx = (e.clientX / window.innerWidth) * 2 - 1;
      state.current.tmy = (e.clientY / window.innerHeight) * 2 - 1;
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => window.removeEventListener("pointermove", onMove);
  }, [reduced]);

  useEffect(() => () => {
    [nodeGeo, edgeGeo, dustGeo, haloGeo, coreGeo, wireGeo].forEach((g) => g.dispose());
    Object.values(mats).forEach((m) => m.dispose());
  }, [nodeGeo, edgeGeo, dustGeo, haloGeo, coreGeo, wireGeo, mats]);

  const coreRef = useRef<THREE.Mesh>(null);
  const wireRef = useRef<THREE.LineSegments>(null);

  useFrame((_, rawDelta) => {
    const s = state.current;
    const dt = Math.min(rawDelta, 0.05);
    const target = Math.min(1, Math.max(0, progress.get() || 0));
    if (s.p < 0) s.p = target;
    s.p += (target - s.p) * (1 - Math.exp(-dt * TUNE.progressDamp));
    const p = s.p;
    s.time += dt * (reduced ? TUNE.reducedTimeScale : 1);
    const t = s.time;
    s.mx += (s.tmx - s.mx) * (1 - Math.exp(-dt * TUNE.mouseDamp));
    s.my += (s.tmy - s.my) * (1 - Math.exp(-dt * TUNE.mouseDamp));

    const u = uniforms;
    u.uP.value = p;
    u.uTime.value = t;
    u.uDrift.value = reduced ? TUNE.reducedDrift : TUNE.drift;
    u.uScale.value = (size.height * gl.getPixelRatio()) /
      (2 * Math.tan(THREE.MathUtils.degToRad(TUNE.fov) / 2));
    u.uSearch.value = win(p, STAGES.search) * (1 - win(p, STAGES.searchFade)) * 0.9;
    u.uRead.value = win(p, STAGES.read);
    u.uCheck.value = win(p, STAGES.check);
    const flick = 0.7 + 0.3 * Math.sin(t * 9);
    u.uAmber.value = win(p, STAGES.conflictIn) * (1 - win(p, STAGES.conflictOut)) * flick;
    u.uResolve.value = win(p, STAGES.resolve);
    u.uContract.value = win(p, STAGES.contract);
    u.uAnswer.value = win(p, STAGES.answer);

    // camera: damped keyframes + idle orbit + parallax
    const k = sampleCamera(p);
    const par = reduced ? 0 : 1;
    const az = THREE.MathUtils.degToRad(k.azim + t * TUNE.orbitIdleDegPerSec * par + s.mx * TUNE.parallaxAzim * par);
    const el = THREE.MathUtils.degToRad(k.elev - s.my * TUNE.parallaxElev * par);
    camera.position.set(
      Math.sin(az) * Math.cos(el) * k.dist,
      Math.sin(el) * k.dist,
      Math.cos(az) * Math.cos(el) * k.dist,
    );
    const aspect = size.width / Math.max(1, size.height);
    const offX = TUNE.sceneOffsetX * Math.min(1, Math.max(0, aspect - 1));
    camera.lookAt(offX, k.lookY, 0);

    const a = u.uAnswer.value;
    if (coreRef.current) coreRef.current.rotation.set(t * 0.25, t * 0.4, 0);
    if (wireRef.current) {
      wireRef.current.rotation.set(-t * 0.18, t * 0.22, 0);
      wireRef.current.scale.setScalar(0.05 + 1.05 * a);
      mats.wire.opacity = 0.35 * a;
    }
  });

  return (
    <>
      <points geometry={dustGeo} material={mats.dust} frustumCulled={false} renderOrder={0} />
      <lineSegments geometry={edgeGeo} material={mats.edge} frustumCulled={false} renderOrder={1} />
      <points geometry={nodeGeo} material={mats.node} frustumCulled={false} renderOrder={2} />
      <mesh ref={coreRef} geometry={coreGeo} material={mats.core} frustumCulled={false} renderOrder={3} />
      <lineSegments ref={wireRef} geometry={wireGeo} material={mats.wire} frustumCulled={false} renderOrder={3} />
      <points geometry={haloGeo} material={mats.halo} frustumCulled={false} renderOrder={4} />
    </>
  );
}

export default function ResearchScene({ progress }: ResearchSceneProps) {
  const [visible, setVisible] = useState(
    typeof document === "undefined" ? true : document.visibilityState !== "hidden",
  );
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const onVis = () => setVisible(document.visibilityState !== "hidden");
    document.addEventListener("visibilitychange", onVis);
    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (mq) {
      setReduced(mq.matches);
      const onMq = (e: MediaQueryListEvent) => setReduced(e.matches);
      mq.addEventListener?.("change", onMq);
      return () => {
        document.removeEventListener("visibilitychange", onVis);
        mq.removeEventListener?.("change", onMq);
      };
    }
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  return (
    <Canvas
      aria-hidden
      className="pointer-events-none"
      style={{ position: "fixed", inset: 0, zIndex: 0, pointerEvents: "none" }}
      dpr={[1, TUNE.dprMax]}
      frameloop={visible ? "always" : "never"}
      camera={{ fov: TUNE.fov, near: 0.1, far: 120, position: [0, 0.8, 9] }}
      gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      onCreated={({ gl }) => gl.setClearColor(0x000000, 0)}
    >
      <Graph progress={progress} reduced={reduced} />
    </Canvas>
  );
}
