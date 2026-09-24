import { GRAPH } from "./research-config";

/** Deterministic PRNG (mulberry32). */
export function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface N {
  pos: [number, number, number];
  par: [number, number, number];
  t0: number;
  dur: number;
  seed: number;
  cl: number;
  kind: number; // 0 seed, 1 sub, 2 source
  size: number;
  rel: number;
  conf: number;
  branch: number;
}

export interface GraphData {
  nodeCount: number;
  nPos: Float32Array;
  nPar: Float32Array;
  nNode: Float32Array; // t0,dur,seed,cluster
  nInfo: Float32Array; // kind,size,relevant,conflict
  edgeVertCount: number;
  ePos: Float32Array;
  ePar: Float32Array;
  eNode: Float32Array;
  eEdge: Float32Array; // u, eT0, eDur, kind
  dust: Float32Array; // xyz + seed
}

const norm = (v: number[]): [number, number, number] => {
  const l = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / l, v[1] / l, v[2] / l];
};

export function buildGraph(): GraphData {
  const rnd = mulberry32(GRAPH.seed);
  const nodes: N[] = [];
  const O: [number, number, number] = [0, 0, 0];

  nodes.push({ pos: O, par: O, t0: -1, dur: 1, seed: 0.5, cl: 0, kind: 0, size: 0.6, rel: 1, conf: 0, branch: -1 });

  const subs: number[] = [];
  const n = GRAPH.subCount;
  for (let i = 0; i < n; i++) {
    const y = 1 - (i + 0.5) * (2 / n);
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const th = i * 2.399963 + rnd() * 0.5;
    const d = norm([Math.cos(th) * r, y * 0.85, Math.sin(th) * r]);
    const R = GRAPH.subRadius * (0.9 + rnd() * 0.2);
    subs.push(nodes.length);
    nodes.push({
      pos: [d[0] * R, d[1] * R, d[2] * R], par: O,
      t0: 0.17 + i * 0.012, dur: 0.12, seed: rnd(), cl: 0, kind: 1, size: 0.46, rel: 1, conf: 0, branch: i,
    });
  }

  const treeEdges: [number, number, number, number][] = []; // a,b,t0,dur
  subs.forEach((s) => treeEdges.push([0, s, nodes[s].t0, nodes[s].dur + 0.03]));

  subs.forEach((s, bi) => {
    const sp = nodes[s].pos;
    const sd = norm(sp);
    for (let k = 0; k < GRAPH.sourcesPerSub; k++) {
      const u = norm([rnd() * 2 - 1 + sd[0] * 0.9, rnd() * 2 - 1 + sd[1] * 0.9, rnd() * 2 - 1 + sd[2] * 0.9]);
      const r = 0.9 + Math.pow(rnd(), 0.7) * 2.2;
      const idx = nodes.length;
      const t0 = 0.36 + rnd() * 0.14;
      const dur = 0.1 + rnd() * 0.05;
      nodes.push({
        pos: [sp[0] + u[0] * r, sp[1] + u[1] * r, sp[2] + u[2] * r], par: sp,
        t0, dur, seed: rnd(), cl: Math.floor(rnd() * 3), kind: 2,
        size: 0.07 + Math.pow(rnd(), 2) * 0.1,
        rel: rnd() < GRAPH.relevantRatio ? 1 : 0, conf: 0, branch: bi,
      });
      treeEdges.push([s, idx, t0, dur]);
    }
  });

  const rel = nodes.map((nd, i) => (nd.kind === 2 && nd.rel ? i : -1)).filter((i) => i >= 0);
  const dist = (a: number, b: number) =>
    Math.hypot(nodes[a].pos[0] - nodes[b].pos[0], nodes[a].pos[1] - nodes[b].pos[1], nodes[a].pos[2] - nodes[b].pos[2]);

  const cross: [number, number, number, number, number][] = []; // a,b,t0,dur,kind
  const seen = new Set<string>();
  for (const a of rel) {
    if (cross.length >= GRAPH.agreeMax) break;
    let best = -1;
    let bd = 1e9;
    for (const b of rel) {
      if (b === a || nodes[b].cl !== nodes[a].cl || nodes[b].branch === nodes[a].branch) continue;
      const d = dist(a, b);
      if (d < bd) { bd = d; best = b; }
    }
    if (best < 0) continue;
    const key = a < best ? `${a}-${best}` : `${best}-${a}`;
    if (seen.has(key)) continue;
    seen.add(key);
    cross.push([a, best, 0.68 + rnd() * 0.1, 0.07, 1]);
  }

  let made = 0;
  for (let tries = 0; tries < 200 && made < GRAPH.conflictCount; tries++) {
    const a = rel[Math.floor(rnd() * rel.length)];
    let best = -1;
    let bd = 1e9;
    for (const b of rel) {
      if (nodes[b].cl === nodes[a].cl || nodes[b].branch === nodes[a].branch || nodes[b].conf || nodes[a].conf) continue;
      const d = dist(a, b);
      if (d < bd) { bd = d; best = b; }
    }
    if (best < 0) continue;
    nodes[a].conf = 1;
    nodes[best].conf = 1;
    cross.push([a, best, 0.72 + rnd() * 0.04, 0.05, 2]);
    made++;
  }

  const nc = nodes.length;
  const nPos = new Float32Array(nc * 3), nPar = new Float32Array(nc * 3);
  const nNode = new Float32Array(nc * 4), nInfo = new Float32Array(nc * 4);
  nodes.forEach((nd, i) => {
    nPos.set(nd.pos, i * 3); nPar.set(nd.par, i * 3);
    nNode.set([nd.t0, nd.dur, nd.seed, nd.cl], i * 4);
    nInfo.set([nd.kind, nd.size, nd.rel, nd.conf], i * 4);
  });

  const edges: [number, number, number, number, number][] = [
    ...treeEdges.map((e) => [e[0], e[1], e[2], e[3], 0] as [number, number, number, number, number]),
    ...cross,
  ];
  const ev = edges.length * 2;
  const ePos = new Float32Array(ev * 3), ePar = new Float32Array(ev * 3);
  const eNode = new Float32Array(ev * 4), eEdge = new Float32Array(ev * 4);
  edges.forEach(([a, b, t0, dur, kind], i) => {
    [a, b].forEach((id, end) => {
      const nd = nodes[id];
      const v = i * 2 + end;
      ePos.set(nd.pos, v * 3); ePar.set(nd.par, v * 3);
      eNode.set([nd.t0, nd.dur, nd.seed, kind === 0 ? nd.cl : nodes[a].cl], v * 4);
      eEdge.set([end, t0, dur, kind], v * 4);
    });
  });

  const dc = GRAPH.dustCount;
  const dust = new Float32Array(dc * 4);
  for (let i = 0; i < dc; i++) {
    dust.set([(rnd() - 0.5) * 34, (rnd() - 0.5) * 22, (rnd() - 0.5) * 30, rnd()], i * 4);
  }

  return { nodeCount: nc, nPos, nPar, nNode, nInfo, edgeVertCount: ev, ePos, ePar, eNode, eEdge, dust };
}
