/* KenzCloudX animated glass ribbon (original implementation), drawn on <canvas id="ribbon"> behind the page.
   Rounded glass tiles are stacked along a 3D Catmull-Rom curve. The curve blends between per-section
   "poses" as the page scrolls ([data-pose="hero|benefits|erp|compliance|looks|how|plans|faq|cta|footer"]),
   and the tiles flow along it.
   - Inner pages (body.inner-page) use a calmer preset: fewer tiles, slower flow, the ribbon kept to the
     inline-end edge ("page" at the top, "page-body" further down); they need no data-pose markup.
   - dir=rtl mirrors every pose horizontally, so Arabic pages are a true mirror image.
   - Phones (<768px): fewer tiles, lower pixel ratio. devicePixelRatio is capped at 2.
   - prefers-reduced-motion: one static frame. No WebGL / any error: html.no-webgl (CSS fallback shape).
   - The loop stops while the tab is hidden. Phones render at most 30 fps.
   - Budget: low-power GPU; no WebGL at all (CSS shape) when the visitor asks to save data or the device
     reports <= 4 GB of memory; a lost WebGL context switches to the CSS shape for the rest of the visit.
   - Pages that do not need it (demo, legal, 404) never load this module (base.html, context.ribbon). */
import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

const root = document.documentElement;
const canvas = document.getElementById('ribbon');
const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
const inner = document.body.classList.contains('inner-page');
const mirror = (root.getAttribute('dir') || '').toLowerCase() === 'rtl' ? -1 : 1;

function fallback() { root.classList.add('no-webgl'); window.__ribbonReady = true; }

/* Save-Data or a small device: keep the static CSS shape, skip WebGL entirely. */
function lowBudget() {
  const conn = navigator.connection;
  if (conn && conn.saveData) return true;
  return typeof navigator.deviceMemory === 'number' && navigator.deviceMemory <= 4;
}

/* Poses in normalised screen units: x,y in [-1,1] of the visible half-size (x = +1 is the inline-end
   edge in LTR, flipped for RTL), z in world units. 6 control points each; points beyond ±1 sit
   off-screen so the ribbon enters and leaves at the edges. */
const POSES = {
  hero:       [[-1.45, 1.20, -2.5], [-0.78, 0.74, -0.4], [-0.08, 0.50, 0.9], [0.52, 0.30, 0.9], [0.86, -0.28, 0.2], [1.02, -1.45, -1.4]],
  benefits:   [[-1.45, -0.05, -2.0], [-0.80, -0.62, 0.2], [-0.05, -0.92, 1.0], [0.62, -0.78, 0.6], [1.05, -0.45, -0.2], [1.50, 0.10, -2.0]],
  erp:        [[0.48, 1.50, -2.0], [0.66, 0.80, -0.2], [0.86, 0.15, 0.6], [0.95, -0.40, 0.4], [1.02, -0.95, -0.4], [1.35, -1.50, -2.0]],
  compliance: [[-1.45, 0.95, -2.0], [-0.95, 0.30, 0.0], [-0.92, -0.35, 0.8], [-0.55, -0.85, 0.6], [0.10, -1.10, -0.2], [0.80, -1.45, -2.0]],
  looks:      [[-1.45, 0.45, -2.0], [-0.70, -0.05, 0.4], [0.05, -0.38, 1.0], [0.68, -0.10, 0.6], [1.05, -0.40, -0.2], [1.50, -0.70, -2.0]],
  how:        [[-1.40, 1.45, -2.0], [-0.92, 0.55, 0.0], [-0.35, -0.30, 0.9], [0.35, -0.72, 0.8], [0.95, -0.85, 0.0], [1.50, -0.80, -2.0]],
  plans:      [[1.45, 1.30, -2.0], [0.95, 0.75, -0.2], [0.88, 0.10, 0.6], [1.00, -0.50, 0.4], [1.12, -1.00, -0.4], [1.45, -1.50, -2.0]],
  faq:        [[0.10, 1.50, -2.0], [0.55, 1.05, -0.2], [0.88, 0.55, 0.6], [1.00, -0.05, 0.6], [1.05, -0.60, -0.2], [1.40, -1.10, -2.0]],
  cta:        [[0.30, 1.50, -2.0], [0.70, 1.00, 0.0], [0.92, 0.40, 0.8], [1.00, -0.20, 0.5], [1.10, -0.75, -0.2], [1.45, -1.30, -2.0]],
  footer:     [[0.40, 1.50, -2.0], [0.75, 1.10, 0.0], [0.95, 0.60, 0.8], [1.05, 0.05, 0.5], [1.15, -0.50, -0.2], [1.45, -1.10, -2.0]],
  /* inner pages: a single sweep through the top inline-end corner, then a quiet pass along the edge */
  page:       [[0.05, 1.55, -2.0], [0.45, 1.08, -0.3], [0.78, 0.62, 0.7], [0.98, 0.05, 0.5], [1.12, -0.55, -0.3], [1.45, -1.15, -2.0]],
  'page-body':[[0.92, 1.55, -2.0], [1.00, 0.85, -0.4], [1.06, 0.15, 0.3], [1.08, -0.55, 0.1], [1.18, -1.15, -0.6], [1.50, -1.60, -2.0]],
};
/* Narrow screens: keep the ribbon off the headlines (top band only). */
const POSES_MOBILE_OVERRIDE = {
  hero: [[-1.7, 1.25, -2.0], [-0.85, 0.92, -0.2], [0.0, 0.72, 0.8], [0.72, 0.50, 0.6], [1.10, 0.10, 0.0], [1.60, -0.35, -2.0]],
  page: [[-1.7, 1.40, -2.0], [-0.80, 1.12, -0.2], [0.05, 0.98, 0.5], [0.80, 0.90, 0.4], [1.30, 0.72, 0.0], [1.75, 0.50, -2.0]],
};
/* On phones, passes along the inline-end edge move further out so they do not sit under body text. */
const MOBILE_PUSH = new Set(['erp', 'plans', 'faq', 'cta', 'footer', 'page-body']);

function hexVec(h) { return new THREE.Vector3(((h >> 16) & 255) / 255, ((h >> 8) & 255) / 255, (h & 255) / 255); }

const vert = /* glsl */`
  attribute float aT;
  varying vec3 vN;
  varying vec3 vV;
  varying vec3 vLN;
  varying vec3 vLP;
  varying float vT;
  void main() {
    vec4 wp = modelMatrix * instanceMatrix * vec4(position, 1.0);
    vec4 mv = viewMatrix * wp;
    vV = -mv.xyz;
    vN = normalize(mat3(viewMatrix) * mat3(modelMatrix) * mat3(instanceMatrix) * normal);
    vLN = normal;
    vLP = position;
    vT = aT;
    gl_Position = projectionMatrix * mv;
  }
`;

const frag = /* glsl */`
  precision highp float;
  uniform vec3 uSky, uAqua, uPeri, uPink, uViolet;
  uniform float uTime, uGlint, uMirror;
  varying vec3 vN;
  varying vec3 vV;
  varying vec3 vLN;
  varying vec3 vLP;
  varying float vT;
  void main() {
    vec3 N = normalize(vN);
    vec3 V = normalize(vV);
    float ndv = clamp(abs(dot(N, V)), 0.0, 1.0);
    float fres = pow(1.0 - ndv, 2.4);
    // rim = the rounded edge band of each slab (local normal not along the slab axis)
    float rim = smoothstep(0.25, 0.95, 1.0 - abs(vLN.z));
    // body colour: sky -> aqua -> periwinkle along the ribbon
    vec3 base = mix(uSky, uAqua, smoothstep(0.0, 0.55, vT));
    base = mix(base, uPeri, smoothstep(0.55, 1.0, vT));
    // gentle diagonal gradient across each face so slabs read as glass, not paint
    float g = clamp(0.5 + (vLP.x - vLP.y) * 0.9, 0.0, 1.0);
    base = mix(base * 0.97, mix(base, vec3(1.0), 0.38), g);
    // lighting (view-space key light from the top, on the inline-start side)
    vec3 L = normalize(vec3(-0.45 * uMirror, 0.75, 0.55));
    float diff = 0.86 + 0.2 * max(dot(N, L), 0.0);
    vec3 col = base * diff;
    // thin-film style tint on rims and grazing angles
    float hueT = 0.5 + 0.5 * sin(vT * 10.0 + fres * 5.0 + uTime * 0.25);
    vec3 irid = mix(uPink, uViolet, hueT);
    col = mix(col, irid, clamp(rim * 0.85 + fres * 0.22, 0.0, 0.92));
    // specular highlight + soft secondary light from below
    vec3 H = normalize(L + V);
    float spec = pow(max(dot(N, H), 0.0), 70.0);
    vec3 L2 = normalize(vec3(0.6 * uMirror, -0.5, 0.6));
    float spec2 = pow(max(dot(N, normalize(L2 + V)), 0.0), 24.0);
    col += vec3(1.0) * spec * 0.75 + vec3(0.85, 0.80, 1.0) * spec2 * 0.18;
    // inner bright line along the top edge of each face (glass bevel catch-light)
    float bevel = smoothstep(0.36, 0.48, vLP.y) * (1.0 - rim) * 0.35;
    col += bevel;
    // travelling glint
    float gl = exp(-pow((vT - uGlint) * 9.0, 2.0));
    col += gl * 0.10;
    float alpha = 0.74 + 0.16 * fres + 0.22 * rim + spec * 0.3;
    gl_FragColor = vec4(clamp(col, 0.0, 1.0), clamp(alpha, 0.0, 0.96));
  }
`;

function init() {
  if (!canvas) return;
  let renderer;
  try {
    const ctx = canvas.getContext('webgl2', { alpha: true }) || canvas.getContext('webgl', { alpha: true });
    if (!ctx) throw new Error('no webgl');
    renderer = new THREE.WebGLRenderer({ canvas, context: ctx, alpha: true, antialias: true, powerPreference: 'low-power' });
  } catch (e) { fallback(); return; }

  renderer.setClearColor(0x000000, 0);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 100);
  camera.position.set(0, 0, 16);

  let mobile = false, N = 0, mesh = null, aT = null, halfW = 1, halfH = 1, tile = 1;
  const geo = new RoundedBoxGeometry(1, 1, 0.11, 4, 0.2);
  const mat = new THREE.ShaderMaterial({
    vertexShader: vert, fragmentShader: frag,
    transparent: true, depthWrite: false, depthTest: true,
    uniforms: {
      uSky: { value: hexVec(0xA9D8F2) }, uAqua: { value: hexVec(0x8AD6DC) }, uPeri: { value: hexVec(0x93A4EE) },
      uPink: { value: hexVec(0xEDB2EE) }, uViolet: { value: hexVec(0x9A86F0) },
      uTime: { value: 0 }, uGlint: { value: 0 }, uMirror: { value: mirror },
    },
  });

  function build() {
    const n = inner ? (mobile ? 26 : 48) : (mobile ? 34 : 62);
    if (n === N && mesh) return;
    if (mesh) { scene.remove(mesh); mesh.dispose(); }
    N = n;
    mesh = new THREE.InstancedMesh(geo, mat, N);
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    mesh.frustumCulled = false;
    aT = new THREE.InstancedBufferAttribute(new Float32Array(N), 1);
    aT.setUsage(THREE.DynamicDrawUsage);
    geo.setAttribute('aT', aT);
    scene.add(mesh);
  }

  function resize() {
    const w = window.innerWidth, h = window.innerHeight;
    mobile = w < 768;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, mobile ? 1.5 : 2));
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    halfH = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * camera.position.z;
    halfW = halfH * camera.aspect;
    tile = (mobile ? 0.7 * halfW : 0.51 * Math.min(halfW, halfH)) * (inner ? 0.86 : 1);
    build();
    measure();
  }

  /* ---- scroll -> pose index ---- */
  let anchors = [];
  function measure() {
    const vh = window.innerHeight, sy = window.scrollY;
    anchors = [...document.querySelectorAll('[data-pose]')].map((el) => {
      const r = el.getBoundingClientRect();
      const key = el.getAttribute('data-pose');
      const y = key === 'hero' ? vh / 2 : r.top + sy + Math.min(r.height, vh) / 2;
      return { key, y };
    });
    // pages without a pose for their first screen start with "page" (inner) or "hero" (home)
    if (!anchors.length || anchors[0].y > vh) {
      anchors.unshift({ key: inner ? 'page' : 'hero', y: vh / 2 });
      const main = document.getElementById('main');
      const end = anchors.length > 1 ? anchors[1].y : (main ? main.getBoundingClientRect().bottom + sy : vh);
      if (inner && end - vh / 2 > vh * 1.6) anchors.splice(1, 0, { key: 'page-body', y: vh * 1.6 });
    }
    anchors.sort((a, b) => a.y - b.y);
  }
  function poseFloat() {
    if (!anchors.length) return 0;
    const c = window.scrollY + window.innerHeight / 2;
    if (c <= anchors[0].y) return 0;
    for (let i = 0; i < anchors.length - 1; i++) {
      const a = anchors[i].y, b = anchors[i + 1].y;
      if (c <= b) return i + (c - a) / Math.max(1, b - a);
    }
    return anchors.length - 1;
  }
  function poseOf(i) {
    const key = anchors[Math.max(0, Math.min(anchors.length - 1, i))]?.key || 'hero';
    if (mobile && POSES_MOBILE_OVERRIDE[key]) return POSES_MOBILE_OVERRIDE[key];
    const p = POSES[key] || POSES.hero;
    if (mobile && MOBILE_PUSH.has(key)) return pushed(key, p);
    return p;
  }
  const pushedCache = {};
  function pushed(key, p) {
    if (!pushedCache[key]) pushedCache[key] = p.map(([x, y, z]) => [x > 0.4 ? x + 0.32 : x, y, z]);
    return pushedCache[key];
  }

  /* ---- per frame ---- */
  const pts = Array.from({ length: 6 }, () => new THREE.Vector3());
  const curve = new THREE.CatmullRomCurve3(pts, false, 'centripetal');
  const m4 = new THREE.Matrix4();
  const P = new THREE.Vector3(), T = new THREE.Vector3(), Vp = new THREE.Vector3(), X = new THREE.Vector3(), Y = new THREE.Vector3(), Z = new THREE.Vector3(), X2 = new THREE.Vector3(), Y2 = new THREE.Vector3();
  const VIEW = new THREE.Vector3(0, 0, 1);
  const flowSpeed = inner ? 0.0028 : 0.004;
  let f = 0, flow = 0, last = performance.now(), time = 0, lastDraw = 0;
  /* one record per tile, reused every frame (no per-frame allocation); `order` is re-sorted in place */
  let recs = [], order = [];
  function ensureRecs() {
    if (recs.length === N) return;
    recs = Array.from({ length: N }, () => ({ u: 0, px: 0, py: 0, pz: 0, xx: 0, xy: 0, xz: 0, yx: 0, yy: 0, yz: 0, zx: 0, zy: 0, zz: 0, sc: 0 }));
    order = recs.slice();
  }
  /* insertion sort by depth: the order barely changes between frames, so this is close to linear */
  function sortByDepth() {
    for (let i = 1; i < order.length; i++) {
      const d = order[i];
      let j = i - 1;
      while (j >= 0 && order[j].pz > d.pz) { order[j + 1] = order[j]; j--; }
      order[j + 1] = d;
    }
  }

  function smooth(t) { return t * t * (3 - 2 * t); }

  function update(dt, staticFrame) {
    time += dt;
    const target = staticFrame ? 0 : poseFloat();
    f = staticFrame ? 0 : f + (target - f) * (1 - Math.exp(-dt * 2.6));
    const flowTarget = staticFrame ? 0 : window.scrollY / window.innerHeight * 0.06 + time * flowSpeed;
    flow += (flowTarget - flow) * (staticFrame ? 1 : 1 - Math.exp(-dt * 3));

    const i0 = Math.floor(f), t = smooth(Math.min(1, Math.max(0, f - i0)));
    const A = poseOf(i0), B = poseOf(i0 + 1);
    const wobble = staticFrame ? 0 : (inner ? 0.6 : 1);
    for (let j = 0; j < 6; j++) {
      const dx = Math.sin(time * 0.35 + j * 1.7) * 0.025 * wobble;
      const dy = Math.cos(time * 0.28 + j * 1.3) * 0.03 * wobble;
      pts[j].set(
        (A[j][0] + (B[j][0] - A[j][0]) * t + dx) * halfW * mirror,
        (A[j][1] + (B[j][1] - A[j][1]) * t + dy) * halfH,
        (A[j][2] + (B[j][2] - A[j][2]) * t) * (mobile ? 0.6 : 1)
      );
    }
    curve.updateArcLengths();

    ensureRecs();
    for (let i = 0; i < N; i++) {
      let u = ((i + 0.5) / N + flow) % 1;
      if (u < 0) u += 1;
      curve.getPointAt(u, P);
      curve.getTangentAt(u, T);
      // tilt each slab's face towards the viewer so we see stacked faces, not edges
      Vp.copy(VIEW).addScaledVector(T, -VIEW.dot(T)).normalize();
      const tilt = 0.74 + 0.2 * Math.sin(u * 7.0 + time * 0.22 + flow * 6.0);
      Z.copy(T).multiplyScalar(Math.cos(tilt)).addScaledVector(Vp, Math.sin(tilt)).normalize();
      X.crossVectors(T, Vp).normalize();
      Y.crossVectors(Z, X).normalize();
      const roll = (0.18 * Math.sin(u * 5.0 - time * 0.18) + 0.55) * mirror;
      const c = Math.cos(roll), s = Math.sin(roll);
      X2.copy(X).multiplyScalar(c).addScaledVector(Y, s);
      Y2.copy(Y).multiplyScalar(c).addScaledVector(X, -s);
      const sc = tile * (0.92 + 0.08 * Math.sin(u * 3.1));
      const r = recs[i];
      r.u = u; r.px = P.x; r.py = P.y; r.pz = P.z;
      r.xx = X2.x; r.xy = X2.y; r.xz = X2.z; r.yx = Y2.x; r.yy = Y2.y; r.yz = Y2.z; r.zx = Z.x; r.zy = Z.y; r.zz = Z.z; r.sc = sc;
    }
    // back to front so the translucent slabs blend correctly
    sortByDepth();
    for (let i = 0; i < N; i++) {
      const d = order[i];
      m4.set(
        d.xx * d.sc, d.yx * d.sc, d.zx * d.sc, d.px,
        d.xy * d.sc, d.yy * d.sc, d.zy * d.sc, d.py,
        d.xz * d.sc, d.yz * d.sc, d.zz * d.sc, d.pz,
        0, 0, 0, 1
      );
      mesh.setMatrixAt(i, m4);
      aT.array[i] = d.u;
    }
    mesh.instanceMatrix.needsUpdate = true;
    aT.needsUpdate = true;
    mat.uniforms.uTime.value = time;
    mat.uniforms.uGlint.value = staticFrame ? -1 : ((time * 0.05) % 1.4) - 0.2;
  }

  let raf = 0, running = false, measureTimer = 0, lost = false;
  const MOBILE_FRAME = 1000 / 30;
  function frame(now) {
    raf = requestAnimationFrame(frame);
    if (mobile && now - lastDraw < MOBILE_FRAME - 1) return; // phones: at most 30 fps
    lastDraw = now;
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    update(dt, false);
    renderer.render(scene, camera);
  }
  function start() {
    if (running || reduced || lost) return;
    running = true; last = performance.now(); raf = requestAnimationFrame(frame);
    measureTimer = setInterval(measure, 2000); // keeps anchors right after reveals and accordions change heights
  }
  function stop() { running = false; cancelAnimationFrame(raf); clearInterval(measureTimer); }
  function renderStatic() { update(0, true); renderer.render(scene, camera); }

  resize();
  let rt = 0;
  window.addEventListener('resize', () => {
    clearTimeout(rt);
    rt = setTimeout(() => { if (lost) return; resize(); if (reduced) renderStatic(); }, 120);
  });
  window.addEventListener('load', measure);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(measure);

  /* A lost context never comes back to life here: we stay on the CSS shape (rebuilding every GPU resource
     after a restore is not worth it for a decoration), and visibilitychange can no longer restart the loop. */
  canvas.addEventListener('webglcontextlost', (e) => { e.preventDefault(); lost = true; stop(); fallback(); canvas.classList.remove('ready'); });
  canvas.addEventListener('webglcontextrestored', () => { lost = true; fallback(); });

  if (reduced) {
    renderStatic();
  } else {
    f = poseFloat();
    start();
    document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); else if (!lost) start(); });
  }
  root.classList.remove('no-webgl');
  window.__ribbonReady = true;
  requestAnimationFrame(() => canvas.classList.add('ready'));
}

if (lowBudget()) fallback();
else {
  try { init(); } catch (e) { console.error(e); fallback(); }
}
