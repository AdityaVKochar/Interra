// The agent orb: one full-screen triangle and a fragment shader.
//
// Warm colour is the person and cool colour is the agent. The judge page
// feeds it the microphone level, the agent's playback level and the agent
// state; the orb only eases toward those targets, it never invents them.

const VERTEX = `
attribute vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
`;

const FRAGMENT = `
precision highp float;
uniform vec2 uRes;
uniform float uFlow;
uniform float uIn;
uniform float uOut;
uniform float uMix;
uniform float uThink;
uniform float uLight;
uniform float uRadius;
uniform vec3 uW1;
uniform vec3 uW2;
uniform vec3 uC1;
uniform vec3 uC2;

float hash(vec2 p) {
  p = fract(p * vec2(234.34, 435.345));
  p += dot(p, p + 34.23);
  return fract(p.x * p.y);
}

float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
             mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}

float fbm(vec2 p) {
  float v = 0.0;
  float a = 0.52;
  mat2 m = mat2(1.6, 1.2, -1.2, 1.6);
  for (int i = 0; i < 4; i++) { v += a * noise(p); p = m * p; a *= 0.42; }
  return v / 0.9;
}

float fbm3(vec2 p) {
  float v = 0.0;
  float a = 0.5;
  mat2 m = mat2(1.6, 1.2, -1.2, 1.6);
  for (int i = 0; i < 3; i++) { v += a * noise(p); p = m * p; a *= 0.5; }
  return v;
}

void main() {
  float s = min(uRes.x, uRes.y);
  vec2 uv = (gl_FragCoord.xy - 0.5 * uRes) / (0.5 * s);
  float r = length(uv);
  float energy = max(uIn, uOut);

  // The rim breathes with sound. Angle is sampled on a circle so it has no seam.
  vec2 dir = r > 0.0001 ? uv / r : vec2(1.0, 0.0);
  float wob = fbm3(dir * 1.35 + vec2(uFlow * 0.33, -uFlow * 0.21)) - 0.5;
  float R = uRadius * (1.0 + 0.05 * uOut + 0.035 * uIn + wob * (0.025 + 0.11 * energy));
  float aa = 2.2 / s;
  float disc = 1.0 - smoothstep(R - aa, R + aa, r);

  vec3 glowCol = mix(uW1, uC2, uMix);
  float outside = max(r - R, 0.0);
  float glow = exp(-outside * (6.5 - 2.0 * energy)) * (1.0 - disc);
  float ga = glow * (0.14 + 0.5 * energy) * mix(1.0, 0.7, uLight);

  if (disc <= 0.0) {
    gl_FragColor = vec4(glowCol * ga, ga);
    return;
  }

  float rr = clamp(r / R, 0.0, 1.0);
  vec3 n = normalize(vec3(uv / R, sqrt(max(0.0, 1.0 - rr * rr))));

  // Thinking twists the inside, more toward the centre.
  float sw = uThink * ((1.0 - rr) * 2.2 + uFlow * 0.2);
  float cs = cos(sw);
  float sn = sin(sw);
  vec2 p = mat2(cs, -sn, sn, cs) * (uv / R) * 0.8 + n.xy * 0.32;

  // Large, slow fields: two warped layers read as silk rather than marble.
  vec2 q = vec2(fbm(p + vec2(0.0, uFlow * 0.2)), fbm(p + vec2(4.7, -uFlow * 0.17)));
  float f = fbm(p * 0.9 + 1.5 * q + vec2(uFlow * 0.07, -uFlow * 0.05));
  float ribbon = 0.5 + 0.5 * sin(5.5 * f + 2.2 * q.y + uFlow * 0.55);

  float m = clamp(uMix + (q.x - 0.5) * 0.85, 0.0, 1.0);
  vec3 warm = mix(uW1, uW2, smoothstep(0.25, 0.85, f));
  vec3 cool = mix(uC2, uC1, smoothstep(0.25, 0.85, f));
  vec3 col = mix(warm, cool, smoothstep(0.12, 0.88, m));

  vec3 L = normalize(vec3(-0.45, 0.55, 0.72));
  float diff = clamp(dot(n, L), 0.0, 1.0);
  // Pastel lift toward white: brighter toward the light and along the ribbons.
  float lift = 0.14 + 0.2 * diff + 0.22 * smoothstep(0.62, 1.0, ribbon) + 0.06 * uLight;
  col = mix(col, vec3(1.0), clamp(lift, 0.0, 0.62));
  col *= 0.88 + 0.16 * diff;

  float fres = pow(1.0 - n.z, 2.2);
  col += fres * mix(uW2, uC1, uMix) * (0.22 + 0.45 * energy);
  col = mix(col, vec3(1.0), fres * 0.18);

  vec3 H = normalize(L + vec3(0.0, 0.0, 1.0));
  float facing = max(dot(n, H), 0.0);
  col += pow(facing, 7.0) * 0.14 + pow(facing, 48.0) * 0.16;

  vec3 outCol = col * disc + glowCol * ga;
  float alpha = clamp(disc + ga, 0.0, 1.0);
  gl_FragColor = vec4(outCol, alpha);
}
`;

const PALETTE = {
  warmA: [1.0, 0.43, 0.1],
  warmB: [1.0, 0.71, 0.37],
  coolA: [0.71, 0.75, 1.0],
  coolB: [0.36, 0.34, 0.92],
};

function compile(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const info = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(info || "shader did not compile");
  }
  return shader;
}

function approach(current, target, rate, dt) {
  return current + (target - current) * (1 - Math.exp(-rate * dt));
}

export class Orb {
  constructor(canvas, { reduceMotion = false } = {}) {
    this.canvas = canvas;
    this.reduceMotion = reduceMotion;
    this.radius = 0.56;
    this.light = 0;
    this.target = { input: 0, output: 0, mix: 0.5, think: 0 };
    this.value = { input: 0, output: 0, mix: 0.5, think: 0, flow: Math.random() * 40 };
    this.ok = false;
    this.error = "";
    this.size = [0, 0];
    canvas.addEventListener("webglcontextlost", (event) => {
      event.preventDefault();
      this.ok = false;
    });
    canvas.addEventListener("webglcontextrestored", () => this.init());
    this.init();
  }

  init() {
    try {
      const gl = this.canvas.getContext("webgl", { alpha: true, premultipliedAlpha: true, antialias: false, powerPreference: "low-power" });
      if (!gl) throw new Error("WebGL is not available");
      const program = gl.createProgram();
      gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, VERTEX));
      gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, FRAGMENT));
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        throw new Error(gl.getProgramInfoLog(program) || "shader program did not link");
      }
      gl.useProgram(program);
      const buffer = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
      const position = gl.getAttribLocation(program, "aPos");
      gl.enableVertexAttribArray(position);
      gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
      const names = ["uRes", "uFlow", "uIn", "uOut", "uMix", "uThink", "uLight", "uRadius", "uW1", "uW2", "uC1", "uC2"];
      this.u = Object.fromEntries(names.map((name) => [name, gl.getUniformLocation(program, name)]));
      gl.uniform3fv(this.u.uW1, PALETTE.warmA);
      gl.uniform3fv(this.u.uW2, PALETTE.warmB);
      gl.uniform3fv(this.u.uC1, PALETTE.coolA);
      gl.uniform3fv(this.u.uC2, PALETTE.coolB);
      gl.clearColor(0, 0, 0, 0);
      this.gl = gl;
      this.size = [0, 0];
      this.ok = true;
    } catch (error) {
      this.ok = false;
      this.error = String(error && error.message ? error.message : error);
    }
    return this.ok;
  }

  set(target) {
    Object.assign(this.target, target);
  }

  resize() {
    const rect = this.canvas.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 1.6);
    const width = Math.max(1, Math.min(900, Math.round(rect.width * ratio)));
    const height = Math.max(1, Math.min(900, Math.round(rect.height * ratio)));
    if (width !== this.size[0] || height !== this.size[1]) {
      this.canvas.width = width;
      this.canvas.height = height;
      this.size = [width, height];
      if (this.gl) this.gl.viewport(0, 0, width, height);
    }
  }

  render(dt) {
    const value = this.value;
    const target = this.target;
    value.input = approach(value.input, target.input, target.input > value.input ? 18 : 5, dt);
    value.output = approach(value.output, target.output, target.output > value.output ? 16 : 4.5, dt);
    value.mix = approach(value.mix, target.mix, 2.2, dt);
    value.think = approach(value.think, target.think, 3, dt);
    const speed = (0.22 + 1.45 * value.output + 0.75 * value.input + 0.55 * value.think) * (this.reduceMotion ? 0.3 : 1);
    value.flow += dt * speed;
    if (!this.ok || !this.gl) return;
    this.resize();
    const gl = this.gl;
    const u = this.u;
    gl.uniform2f(u.uRes, this.size[0], this.size[1]);
    gl.uniform1f(u.uFlow, value.flow);
    gl.uniform1f(u.uIn, value.input);
    gl.uniform1f(u.uOut, value.output);
    gl.uniform1f(u.uMix, value.mix);
    gl.uniform1f(u.uThink, value.think);
    gl.uniform1f(u.uLight, this.light);
    gl.uniform1f(u.uRadius, this.radius);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }
}
