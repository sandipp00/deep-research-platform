/** Tunables + keyframes for the Lumen research-graph scene. Tune here. */

export const PALETTE = {
  bg: "#0B1220",
  green: "#22C55E", // brand accent (accent.signal)
  mint: "#86EFAC",
  cyan: "#22D3EE",
  violet: "#8B5CF6",
  amber: "#F59E0B",
  dust: "#7C93B8",
} as const;

/** Agreeing clusters glow one of these colours during CROSS-CHECK. */
export const CLUSTER_COLORS = [PALETTE.green, PALETTE.cyan, PALETTE.violet] as const;

export const GRAPH = {
  seed: 20260924,
  subCount: 5,
  sourcesPerSub: 62, // total nodes = 1 + 5 + 310 = 316 (<= 400)
  subRadius: 3.4,
  relevantRatio: 0.34,
  agreeMax: 110,
  conflictCount: 5,
  dustCount: 280,
} as const;

/** Stage windows in scroll progress [start, end]. */
export const STAGES = {
  plan: [0.17, 0.3],
  search: [0.36, 0.5],
  searchFade: [0.66, 0.76],
  read: [0.5, 0.62],
  check: [0.66, 0.78],
  conflictIn: [0.7, 0.74],
  conflictOut: [0.82, 0.88],
  resolve: [0.82, 0.9],
  contract: [0.86, 1.0],
  answer: [0.9, 1.0],
} as const;

export const TUNE = {
  dprMax: 1.75,
  progressDamp: 4.5, // higher = snappier follow of scroll
  mouseDamp: 3,
  parallaxAzim: 6, // degrees
  parallaxElev: 4,
  pulseSpeed: 0.32,
  drift: 1,
  reducedDrift: 0.25,
  reducedTimeScale: 0.35,
  sceneOffsetX: -1.4, // shifts graph to the right on landscape screens
  fov: 45,
  orbitIdleDegPerSec: 1.2,
} as const;

export interface CamKey {
  t: number;
  dist: number;
  azim: number; // deg
  elev: number; // deg
  lookY: number;
}

export const CAMERA_KEYS: CamKey[] = [
  { t: 0.0, dist: 9, azim: 0, elev: 6, lookY: 0 },
  { t: 0.2, dist: 12, azim: 20, elev: 12, lookY: 0 },
  { t: 0.4, dist: 15, azim: 45, elev: 16, lookY: 0 },
  { t: 0.6, dist: 9, azim: 80, elev: 8, lookY: 0.2 },
  { t: 0.8, dist: 13, azim: 120, elev: 14, lookY: 0 },
  { t: 1.0, dist: 8.5, azim: 150, elev: 4, lookY: 0 },
];

const sm = (x: number) => x * x * (3 - 2 * x);

export function sampleCamera(p: number): CamKey {
  const k = CAMERA_KEYS;
  const c = Math.min(1, Math.max(0, p));
  for (let i = 0; i < k.length - 1; i++) {
    const a = k[i];
    const b = k[i + 1];
    if (c <= b.t) {
      const f = sm((c - a.t) / (b.t - a.t));
      return {
        t: c,
        dist: a.dist + (b.dist - a.dist) * f,
        azim: a.azim + (b.azim - a.azim) * f,
        elev: a.elev + (b.elev - a.elev) * f,
        lookY: a.lookY + (b.lookY - a.lookY) * f,
      };
    }
  }
  return { ...k[k.length - 1], t: c };
}

/** smoothstep window helper */
export function win(p: number, w: readonly [number, number]): number {
  const x = Math.min(1, Math.max(0, (p - w[0]) / (w[1] - w[0])));
  return x * x * (3 - 2 * x);
}
