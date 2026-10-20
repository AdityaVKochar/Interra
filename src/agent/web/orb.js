// The agent visualizer: one 2D canvas that can draw five styles, after
// LiveKit's Agents UI (aura, wave, radial, grid and bars).
//
// White is the person and cyan is the agent. The judge page feeds it the
// microphone level, the agent's playback level and the agent state; the
// visualizer only eases toward those targets, it never invents them.

export const STYLES = [
  { id: "aura", label: "Aura" },
  { id: "wave", label: "Wave" },
  { id: "radial", label: "Radial" },
  { id: "grid", label: "Grid" },
  { id: "bars", label: "Bars" },
];

const STYLE_KEY = "interra-visualizer";
const FADE_SECONDS = 0.45;

const PALETTE = {
  dark: { agent: [31, 213, 249], person: [237, 237, 237], ring: "rgba(255, 255, 255, 0.22)" },
  light: { agent: [8, 145, 178], person: [38, 38, 38], ring: "rgba(0, 0, 0, 0.22)" },
};

function approach(current, target, rate, dt) {
  return current + (target - current) * (1 - Math.exp(-rate * dt));
}

function smoothstep(edge0, edge1, x) {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

function isStyle(id) {
  return STYLES.some((style) => style.id === id);
}

// ---------- the five drawings ----------
// Each receives the 2D context, the centre, the radius R and the eased
// frame values: level (0–1), think (0–1), flow (time that speeds up with
// activity), rgb (person to agent colour) and dpr.

function drawAura(ctx, cx, cy, R, f) {
  // A soft ribbon: many faint strands whose phases drift apart, then one
  // bright core strand. More level spreads the ribbon and deepens the waves.
  const steps = 140;
  const strands = 14;
  const amp = R * (0.05 + 0.22 * f.level + 0.05 * f.think);
  const spread = R * (0.05 + 0.12 * f.level);
  ctx.shadowColor = f.color(0.8);
  for (let s = 0; s <= strands; s++) {
    const k = s / strands;
    const core = s === strands;
    const shift = core ? 1.2 : k * 2.4;
    const offset = core ? 0 : (k - 0.5) * spread;
    ctx.beginPath();
    for (let i = 0; i <= steps; i++) {
      const a = (i / steps) * Math.PI * 2;
      const n = 0.55 * Math.sin(3 * a + f.flow * 1.3 + shift)
        + 0.3 * Math.sin(5 * a - f.flow * 0.9 + shift * 0.6)
        + 0.15 * Math.sin(2 * a + f.flow * 0.6);
      const r = R * 0.8 + offset + amp * n;
      const x = cx + Math.cos(a + f.flow * 0.15) * r;
      const y = cy + Math.sin(a + f.flow * 0.15) * r;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.lineWidth = (core ? 1.8 : 2.4) * f.dpr;
    ctx.strokeStyle = f.color(core ? 0.95 : 0.1 + 0.12 * Math.sin(k * Math.PI));
    ctx.shadowBlur = (core ? 10 : 18) * f.dpr;
    ctx.stroke();
  }
  ctx.shadowBlur = 0;
}

function drawWave(ctx, cx, cy, R, f) {
  const half = R * 1.12;
  const steps = 220;
  const amp = R * (0.03 + 0.5 * f.level + 0.08 * f.think);
  const fade = ctx.createLinearGradient(cx - half, 0, cx + half, 0);
  fade.addColorStop(0, f.color(0));
  fade.addColorStop(0.2, f.color(0.9));
  fade.addColorStop(0.8, f.color(0.9));
  fade.addColorStop(1, f.color(0));
  ctx.beginPath();
  for (let i = 0; i <= steps; i++) {
    const u = (i / steps) * 2 - 1;
    const envelope = Math.exp(-u * u * 3.2);
    const y = cy + amp * envelope * Math.sin(u * Math.PI * 5.2 - f.flow * 3.2);
    const x = cx + u * half;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.lineWidth = 2.6 * f.dpr;
  ctx.lineJoin = "round";
  ctx.strokeStyle = fade;
  ctx.shadowColor = f.color(0.8);
  ctx.shadowBlur = 12 * f.dpr;
  ctx.stroke();
  ctx.shadowBlur = 0;
}

function drawRadial(ctx, cx, cy, R, f) {
  const count = 32;
  const inner = R * 0.52;
  ctx.lineCap = "round";
  ctx.lineWidth = Math.max(2, R * 0.05);
  for (let i = 0; i < count; i++) {
    const a = (i / count) * Math.PI * 2 - Math.PI / 2;
    const ripple = 0.5 + 0.5 * Math.sin(i * 2.3 + f.flow * 2.4);
    const length = R * (0.1 + 0.42 * f.level * (0.35 + 0.65 * ripple));
    // While thinking a bright sweep travels round the ring.
    const sweep = Math.pow(Math.max(0, Math.cos(a - f.flow * 2.2)), 6);
    const alpha = 0.95 - f.think * 0.6 + f.think * 0.6 * sweep;
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(a) * inner, cy + Math.sin(a) * inner);
    ctx.lineTo(cx + Math.cos(a) * (inner + length), cy + Math.sin(a) * (inner + length));
    ctx.strokeStyle = f.color(alpha);
    ctx.stroke();
  }
}

function drawGrid(ctx, cx, cy, R, f) {
  const n = 15;
  const span = R * 1.5;
  const step = span / (n - 1);
  for (let gy = 0; gy < n; gy++) {
    for (let gx = 0; gx < n; gx++) {
      const x = cx - span / 2 + gx * step;
      const y = cy - span / 2 + gy * step;
      const d = Math.hypot(x - cx, y - cy) / (span / 2);
      if (d > 1.02) continue;
      const pulse = 0.5 + 0.5 * Math.sin(d * 8 - f.flow * 4);
      let v = 0.22 + f.level * pulse * (1.1 - d * 0.7);
      v += f.think * 0.85 * Math.pow(Math.max(0, Math.cos((gx + gy) * 0.55 - f.flow * 3)), 6);
      v = Math.min(1, v);
      ctx.beginPath();
      ctx.arc(x, y, step * 0.17 * (0.65 + 0.6 * v), 0, Math.PI * 2);
      ctx.fillStyle = f.color(0.12 + 0.88 * v);
      ctx.fill();
    }
  }
}

function drawBars(ctx, cx, cy, R, f) {
  // Five rounded bars. They rise with the level; while thinking, a lit bar
  // walks across them.
  const count = 5;
  const width = R * 0.17;
  const gap = R * 0.11;
  const shape = [0.6, 0.85, 1, 0.85, 0.6];
  const total = count * width + (count - 1) * gap;
  const lit = (f.flow * 2.2) % count;
  ctx.shadowColor = f.color(0.7);
  ctx.shadowBlur = 10 * f.dpr;
  for (let i = 0; i < count; i++) {
    const wobble = 0.55 + 0.45 * Math.sin(f.flow * 3 + i * 1.3);
    const height = width + R * 1.05 * f.level * shape[i] * wobble;
    const x = cx - total / 2 + i * (width + gap);
    const y = cy - height / 2;
    const near = Math.max(0, 1 - Math.abs(i - lit));
    const alpha = 0.95 - f.think * 0.65 + f.think * 0.65 * near;
    ctx.beginPath();
    ctx.roundRect(x, y, width, height, width / 2);
    ctx.fillStyle = f.color(alpha);
    ctx.fill();
  }
  ctx.shadowBlur = 0;
}

const DRAW = { aura: drawAura, wave: drawWave, radial: drawRadial, grid: drawGrid, bars: drawBars };

export class Orb {
  constructor(canvas, { reduceMotion = false, style = "aura" } = {}) {
    this.canvas = canvas;
    this.reduceMotion = reduceMotion;
    this.radius = 0.56;
    this.light = 0;
    this.style = isStyle(style) ? style : "aura";
    this.previous = null;
    this.fade = 1;
    this.target = { input: 0, output: 0, mix: 0.5, think: 0 };
    this.value = { input: 0, output: 0, mix: 0.5, think: 0, flow: Math.random() * 40 };
    this.size = [0, 0];
    this.error = "";
    this.init();
  }

  init() {
    this.ctx = this.canvas.getContext("2d");
    this.ok = Boolean(this.ctx);
    if (!this.ok) this.error = "Canvas drawing is not available";
    return this.ok;
  }

  set(target) {
    Object.assign(this.target, target);
  }

  setStyle(id, { instant = false } = {}) {
    if (!isStyle(id) || id === this.style) return;
    this.previous = instant ? null : this.style;
    this.style = id;
    this.fade = instant ? 1 : 0;
  }

  resize() {
    const rect = this.canvas.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(1, Math.min(1400, Math.round(rect.width * ratio)));
    const height = Math.max(1, Math.min(1400, Math.round(rect.height * ratio)));
    if (width !== this.size[0] || height !== this.size[1]) {
      this.canvas.width = width;
      this.canvas.height = height;
      this.size = [width, height];
    }
    this.dpr = ratio;
  }

  render(dt) {
    const value = this.value;
    const target = this.target;
    value.input = approach(value.input, target.input, target.input > value.input ? 18 : 5, dt);
    value.output = approach(value.output, target.output, target.output > value.output ? 16 : 4.5, dt);
    value.mix = approach(value.mix, target.mix, 2.2, dt);
    value.think = approach(value.think, target.think, 3, dt);
    const speed = (0.35 + 1.4 * value.output + 0.8 * value.input + 0.6 * value.think) * (this.reduceMotion ? 0.3 : 1);
    value.flow += dt * speed;
    this.fade = Math.min(1, this.fade + dt / FADE_SECONDS);
    if (!this.ok) return;
    this.resize();

    const ctx = this.ctx;
    const [width, height] = this.size;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const cx = width / 2;
    const cy = height / 2;
    const R = this.radius * 0.5 * Math.min(width, height);

    const palette = this.light ? PALETTE.light : PALETTE.dark;
    const tone = smoothstep(0.2, 0.6, value.mix);
    const rgb = palette.person.map((p, i) => Math.round(p + (palette.agent[i] - p) * tone));
    const frame = {
      level: Math.min(1, Math.max(value.input, value.output)),
      think: value.think,
      flow: value.flow,
      dpr: this.dpr,
      color: (alpha) => `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${Math.max(0, Math.min(1, alpha)).toFixed(3)})`,
    };

    // The dotted boundary from the LiveKit stage.
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, R * 1.28, 0, Math.PI * 2);
    ctx.setLineDash([2 * this.dpr, 5 * this.dpr]);
    ctx.lineWidth = this.dpr;
    ctx.strokeStyle = palette.ring;
    ctx.stroke();
    ctx.restore();

    if (this.previous && this.fade < 1) {
      ctx.save();
      ctx.globalAlpha = 1 - this.fade;
      DRAW[this.previous](ctx, cx, cy, R, frame);
      ctx.restore();
    }
    ctx.save();
    ctx.globalAlpha = this.previous ? this.fade : 1;
    DRAW[this.style](ctx, cx, cy, R, frame);
    ctx.restore();
    if (this.fade >= 1) this.previous = null;
  }
}

// A row of buttons that switches the visualizer, like LiveKit's tiles.
// With cycle set, it steps through the styles until someone picks one.
export function mountStylePicker(host, orb, { cycle = false, seconds = 4 } = {}) {
  if (!host) return null;
  let saved = null;
  try { saved = localStorage.getItem(STYLE_KEY); } catch (error) { saved = null; }
  if (!cycle && isStyle(saved)) orb.setStyle(saved, { instant: true });

  const buttons = STYLES.map((style) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "viz-btn";
    button.dataset.style = style.id;
    button.title = style.label;
    button.setAttribute("aria-label", style.label + " visualizer");
    button.innerHTML = `<svg class="ic" aria-hidden="true"><use href="#v-${style.id}"/></svg>`;
    host.append(button);
    return button;
  });

  const mark = () => {
    for (const button of buttons) button.setAttribute("aria-pressed", String(button.dataset.style === orb.style));
  };

  let timer = null;
  const stop = () => { if (timer) { clearInterval(timer); timer = null; } };
  if (cycle) {
    timer = setInterval(() => {
      const index = STYLES.findIndex((style) => style.id === orb.style);
      orb.setStyle(STYLES[(index + 1) % STYLES.length].id);
      mark();
    }, seconds * 1000);
  }

  host.addEventListener("click", (event) => {
    const button = event.target.closest(".viz-btn");
    if (!button) return;
    stop();
    orb.setStyle(button.dataset.style);
    try { localStorage.setItem(STYLE_KEY, button.dataset.style); } catch (error) { /* per-viewer only */ }
    mark();
  });
  mark();
  return { stop };
}
