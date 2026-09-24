/** GLSL for the research graph. All uniforms are declared in every program that uses them. */

const COMMON = /* glsl */ `
uniform float uP;
uniform float uTime;
uniform float uContract;
uniform float uDrift;
uniform float uScale;
uniform float uSearch;
uniform float uRead;
uniform float uCheck;
uniform float uAmber;
uniform float uResolve;
uniform float uAnswer;
uniform float uPulse;
uniform vec3 uC0;
uniform vec3 uC1;
uniform vec3 uC2;
uniform vec3 uGreen;
uniform vec3 uMint;
uniform vec3 uAmberCol;

float easeOut(float x){ return 1.0 - pow(1.0 - x, 3.0); }
vec3 clusterCol(float c){ return c < 0.5 ? uC0 : (c < 1.5 ? uC1 : uC2); }
vec3 animPos(vec3 pos, vec3 par, float t0, float dur, float seed){
  float k = easeOut(clamp((uP - t0) / max(dur, 0.001), 0.0, 1.0));
  vec3 q = mix(par, pos, k);
  q += 0.07 * uDrift * k * vec3(sin(uTime*0.4 + seed*17.0), cos(uTime*0.33 + seed*11.0), sin(uTime*0.37 + seed*5.0));
  float cc = smoothstep(seed * 0.3, 1.0, uContract);
  float a = cc * (1.0 - cc) * 3.0;
  float s = sin(a), c = cos(a);
  q.xz = mat2(c, -s, s, c) * q.xz;
  return mix(q, vec3(0.0), cc * (0.93 + 0.07 * seed));
}
`;

export const NODE_VERT = /* glsl */ `
${COMMON}
attribute vec3 aPar;
attribute vec4 aNode; // t0,dur,seed,cluster
attribute vec4 aInfo; // kind,size,relevant,conflict
varying vec3 vColor;
varying float vAlpha;
void main(){
  float kind = aInfo.x, size = aInfo.y, rel = aInfo.z, conf = aInfo.w;
  float vis = smoothstep(0.0, 0.35, (uP - aNode.x) / max(aNode.y, 0.001));
  vec3 p = animPos(position, aPar, aNode.x, aNode.y, aNode.z);
  vec4 mv = modelViewMatrix * vec4(p, 1.0);

  vec3 col; float bright = 1.0; float sz = size;
  if (kind < 0.5) {
    col = mix(uMint, vec3(1.0), 0.55);
    float pulse = 1.0 + 0.12 * sin(uTime * 1.6);
    sz *= pulse; bright = 1.4;
  } else if (kind < 1.5) {
    col = mix(uGreen, uMint, 0.4); bright = 1.15;
  } else {
    col = mix(uMint, vec3(0.75, 0.9, 1.0), aNode.z * 0.5) * 0.85;
    float isRel = rel;
    bright = mix(1.0, mix(0.26, 1.9, isRel), uRead);
    sz *= mix(1.0, mix(0.7, 1.9, isRel), uRead);
    col = mix(col, clusterCol(aNode.w), uCheck * isRel);
    // flashing amber on conflicting sources, resolving back to cluster colour
    col = mix(col, uAmberCol, conf * uAmber);
    bright += conf * uAmber * 1.2;
    // searching shimmer
    bright += uSearch * 0.35 * (0.5 + 0.5 * sin(uTime * 2.0 + aNode.z * 40.0)) * (1.0 - uRead);
  }
  float fade = 1.0 - 0.9 * smoothstep(0.55, 1.0, uContract);
  vAlpha = vis * fade * bright;
  vColor = col;
  sz *= mix(0.25, 1.0, vis);
  float px = sz * uScale / max(-mv.z, 0.1);
  gl_PointSize = clamp(px, 1.5, 140.0);
  gl_Position = projectionMatrix * mv;
}`;

export const NODE_FRAG = /* glsl */ `
varying vec3 vColor;
varying float vAlpha;
void main(){
  float r = length(gl_PointCoord - 0.5) * 2.0;
  if (r > 1.0) discard;
  float glow = exp(-r * r * 4.5) * 0.75 + smoothstep(0.32, 0.0, r);
  gl_FragColor = vec4(vColor * glow * vAlpha, glow * vAlpha);
}`;

export const EDGE_VERT = /* glsl */ `
${COMMON}
attribute vec3 aPar;
attribute vec4 aNode;
attribute vec4 aEdge; // u,eT0,eDur,kind
varying float vU;
varying float vProg;
varying float vKind;
varying float vSeed;
varying float vCl;
void main(){
  vec3 p = animPos(position, aPar, aNode.x, aNode.y, aNode.z);
  vU = aEdge.x;
  vProg = smoothstep(aEdge.y, aEdge.y + aEdge.z, uP);
  vKind = aEdge.w;
  vSeed = aNode.z;
  vCl = aNode.w;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
}`;

export const EDGE_FRAG = /* glsl */ `
${COMMON}
varying float vU;
varying float vProg;
varying float vKind;
varying float vSeed;
varying float vCl;
void main(){
  if (vU > vProg || vProg <= 0.001) discard;
  float head = smoothstep(0.0, 0.12, vProg - vU); // soft growing tip
  vec3 col; float a;
  float fade = 1.0 - smoothstep(0.55, 0.95, uContract);
  if (vKind < 0.5) {
    col = mix(uGreen, uMint, 0.35);
    float t = fract(uTime * uPulse + vSeed * 7.0);
    float pulse = exp(-pow((vU - t) * 9.0, 2.0)) * uSearch;
    a = 0.16 + 0.05 * uRead + pulse * 1.1;
    col += pulse * 0.6;
    a *= 1.0 - 0.5 * uCheck;
  } else if (vKind < 1.5) {
    col = clusterCol(vCl);
    float flow = 0.5 + 0.5 * sin(vU * 6.0 - uTime * 1.5 + vSeed * 6.0);
    a = (0.28 + 0.3 * flow) * uCheck;
  } else {
    float res = uResolve;
    col = mix(uAmberCol, uGreen, res);
    a = mix(0.35 + 0.75 * uAmber, 0.22, res);
    a *= mix(1.0, 0.7 + 0.3 * sin(uTime * 12.0), uAmber * (1.0 - res));
  }
  a *= head * fade;
  gl_FragColor = vec4(col * a, a);
}`;

export const DUST_VERT = /* glsl */ `
uniform float uTime;
uniform float uScale;
uniform float uDrift;
attribute float aSeed;
varying float vA;
void main(){
  vec3 p = position;
  p.x += sin(uTime * 0.05 + aSeed * 30.0) * 0.8 * uDrift;
  p.y = mod(position.y + 11.0 + uTime * 0.07 * uDrift * (0.5 + aSeed), 22.0) - 11.0;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_PointSize = clamp((0.035 + aSeed * 0.05) * uScale / max(-mv.z, 0.1), 1.0, 5.0);
  vA = 0.16 + 0.3 * aSeed;
  gl_Position = projectionMatrix * mv;
}`;

export const DUST_FRAG = /* glsl */ `
uniform vec3 uDustCol;
varying float vA;
void main(){
  float r = length(gl_PointCoord - 0.5) * 2.0;
  if (r > 1.0) discard;
  float g = exp(-r * r * 3.0) * vA;
  gl_FragColor = vec4(uDustCol * g, g);
}`;

export const CORE_VERT = /* glsl */ `
uniform float uAnswer;
uniform float uTime;
varying vec3 vView;
varying vec3 vN;
void main(){
  float s = 0.05 + 1.05 * uAnswer;
  vec4 mv = modelViewMatrix * vec4(position * s, 1.0);
  vView = mv.xyz;
  vN = normalize(normalMatrix * normal);
  gl_Position = projectionMatrix * mv;
}`;

export const CORE_FRAG = /* glsl */ `
uniform float uAnswer;
uniform float uTime;
uniform vec3 uGreen;
uniform vec3 uMint;
varying vec3 vView;
varying vec3 vN;
void main(){
  vec3 fn = normalize(cross(dFdx(vView), dFdy(vView)));
  vec3 V = normalize(-vView);
  float fres = pow(1.0 - abs(dot(fn, V)), 2.0);
  float facet = 0.5 + 0.5 * dot(fn, normalize(vec3(0.4, 0.8, 0.5)));
  float smoothFres = pow(1.0 - abs(dot(normalize(vN), V)), 1.5);
  vec3 col = mix(uGreen * 0.55, uMint, facet * 0.7) + vec3(1.0) * fres * 0.5 + uMint * smoothFres * 0.5;
  col *= 0.75 + 0.25 * sin(uTime * 1.2);
  float a = uAnswer;
  gl_FragColor = vec4(col * a, a * 0.85);
}`;

export const HALO_VERT = /* glsl */ `
uniform float uAnswer;
uniform float uScale;
uniform float uTime;
void main(){
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  float size = 7.5 * uAnswer * (1.0 + 0.04 * sin(uTime * 1.3));
  gl_PointSize = clamp(size * uScale / max(-mv.z, 0.1), 1.0, 1400.0);
  gl_Position = projectionMatrix * mv;
}`;

export const HALO_FRAG = /* glsl */ `
uniform float uAnswer;
uniform vec3 uGreen;
uniform vec3 uMint;
void main(){
  float r = length(gl_PointCoord - 0.5) * 2.0;
  if (r > 1.0) discard;
  float g = exp(-r * r * 6.0) * 0.55 + exp(-r * r * 40.0) * 0.6;
  float ring = exp(-pow((r - 0.62) * 14.0, 2.0)) * 0.12;
  vec3 col = mix(uGreen, uMint, exp(-r * r * 20.0));
  float a = (g + ring) * uAnswer;
  gl_FragColor = vec4(col * a, a);
}`;
