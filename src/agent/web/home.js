// Overview: the hero orb walks through the states a session goes through.
// It is an illustration, not a session; the label says which state it shows.

import { Orb } from "./orb.js";
import { $, reduceMotion, renderModels } from "./shell.js";

const STATES = [
  { tone: "idle", text: "Ready", seconds: 2.4, mix: 0.5, think: 0, input: 0, output: 0.06 },
  { tone: "user", text: "You are speaking", seconds: 3.2, mix: 0.03, think: 0, input: 0.5, output: 0 },
  { tone: "hold", text: "Holding the call until you are quiet", seconds: 1.8, mix: 0.42, think: 0.55, input: 0, output: 0.08 },
  { tone: "think", text: "Thinking", seconds: 1.8, mix: 0.64, think: 1, input: 0, output: 0.12 },
  { tone: "agent", text: "Speaking", seconds: 3.4, mix: 1, think: 0, input: 0, output: 0.55 },
];

const wrap = $("hero-orb-wrap");
const pill = $("hero-state");
const label = $("hero-state-text");
const orb = new Orb($("hero-orb"), { reduceMotion });
orb.radius = 0.6;
orb.light = document.documentElement.dataset.theme === "light" ? 1 : 0;
if (!orb.ok) wrap.classList.add("no-webgl");
window.addEventListener("interra:theme", (event) => { orb.light = event.detail === "light" ? 1 : 0; });

let index = 0;
let since = performance.now();
let last = since;

function show(state) {
  pill.dataset.tone = state.tone;
  label.textContent = state.text;
}

function frame(now) {
  const dt = Math.min(0.1, (now - last) / 1000);
  last = now;
  let state = STATES[index];
  if ((now - since) / 1000 > state.seconds && !reduceMotion) {
    index = (index + 1) % STATES.length;
    since = now;
    state = STATES[index];
    show(state);
  }
  const t = now / 1000;
  const sway = 0.5 + 0.25 * Math.sin(t * 7.1) + 0.25 * Math.sin(t * 3.3 + 1.3);
  orb.set({
    input: state.input ? state.input * (0.6 + 0.4 * sway) : 0,
    output: state.output ? state.output * (0.6 + 0.4 * sway) : 0.05 + 0.03 * Math.sin(t * 1.3),
    mix: state.mix,
    think: state.think,
  });
  orb.render(dt);
  requestAnimationFrame(frame);
}

show(STATES[0]);
requestAnimationFrame(frame);
renderModels($("models"));
