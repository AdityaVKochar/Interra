// Shared by every page: small DOM helpers, formatting, theme, nav and config.

export const $ = (id) => document.getElementById(id);
export const params = new URLSearchParams(location.search);
export const reduceMotion = Boolean(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
export const clamp = (value, low = 0, high = 1) => Math.min(high, Math.max(low, value));
export const nowSeconds = () => Date.now() / 1000;
export const errorText = (error) => (error && error.message ? error.message : String(error));

export function h(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

export function svgIcon(name, className = "ic sm") {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("class", className);
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(ns, "use");
  use.setAttribute("href", "#i-" + name);
  svg.append(use);
  return svg;
}

export function fmtClock(seconds) {
  if (!Number.isFinite(seconds)) return "";
  const sign = seconds < 0 ? "-" : "+";
  const value = Math.abs(seconds);
  const minutes = Math.floor(value / 60);
  return sign + String(minutes).padStart(2, "0") + ":" + (value - minutes * 60).toFixed(3).padStart(6, "0");
}

export function fmtShort(seconds) {
  const value = Math.max(0, seconds || 0);
  return String(Math.floor(value / 60)).padStart(2, "0") + ":" + String(Math.floor(value % 60)).padStart(2, "0");
}

export function fmtNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? String(+number.toFixed(3)) : String(value);
}

export function fmtDuration(seconds) {
  const value = Math.max(0, Math.round(seconds || 0));
  if (value < 60) return value + " s";
  const minutes = Math.floor(value / 60);
  return minutes + " min " + String(value % 60).padStart(2, "0") + " s";
}

export function fmtWhen(epochSeconds) {
  const date = new Date(epochSeconds * 1000);
  const today = new Date();
  const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (date.toDateString() === today.toDateString()) return "Today " + time;
  return date.toLocaleDateString([], { day: "numeric", month: "short" }) + " " + time;
}

export function restartAnimation(node, className) {
  node.classList.remove(className);
  void node.offsetWidth;
  node.classList.add(className);
}

let toastTimer = 0;
export function toast(message) {
  const node = $("toast");
  if (!node) return;
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("show"), 2200);
}

export function copyText(text, done = "Copied") {
  if (!navigator.clipboard) { toast("Copy is not available in this browser"); return; }
  navigator.clipboard.writeText(text).then(() => toast(done), () => toast("Copy was blocked by the browser"));
}

let configRequest = null;
export function loadConfig() {
  if (!configRequest) {
    configRequest = fetch("/api/config", { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : {}))
      .catch(() => ({}));
  }
  return configRequest;
}

const MODEL_NAMES = {
  "deepgram/nova-3": "Deepgram Nova-3",
  "openai/gpt-4.1-mini": "GPT-4.1 mini",
  "cartesia/sonic-3": "Cartesia Sonic-3",
  "assemblyai/universal-3-5-pro": "AssemblyAI Universal-3.5",
  "deepgram/aura-2:athena": "Deepgram Aura-2",
};

export function modelName(id) {
  return MODEL_NAMES[id] || id || "unknown";
}

/** Fill a container with the stack chips from /api/config; the static chips stay if it fails. */
export async function renderModels(container) {
  if (!container) return;
  const config = await loadConfig();
  const models = config.models;
  if (!models) return;
  const llm = models.llm_provider === "ollama" ? "Ollama " + models.ollama_model : modelName(models.llm);
  const items = [
    ["vad", "Silero VAD"],
    ["stt", modelName(models.stt)],
    ["llm", llm + " · temperature " + fmtNumber(config.temperature)],
    ["tts", modelName(models.tts)],
    ["gate", "Quiet window " + fmtNumber(config.commit_quiet_seconds) + " s"],
  ];
  container.replaceChildren(...items.map(([key, value]) => {
    const chip = h("span", "chip");
    chip.append(h("i", null, key), value);
    return chip;
  }));
}

export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem("interra-theme", theme); } catch (error) { /* private window */ }
  window.dispatchEvent(new CustomEvent("interra:theme", { detail: theme }));
}

function initShell() {
  const page = document.body.dataset.page;
  for (const link of document.querySelectorAll(".nav a")) {
    if (link.dataset.page === page) link.setAttribute("aria-current", "page");
  }
  const theme = $("theme");
  if (theme) {
    theme.addEventListener("click", () => applyTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light"));
  }
  if (window.matchMedia) {
    matchMedia("(prefers-color-scheme: light)").addEventListener("change", (event) => {
      let saved = null;
      try { saved = localStorage.getItem("interra-theme"); } catch (error) { /* private window */ }
      if (!saved) applyTheme(event.matches ? "light" : "dark");
    });
  }
  for (const button of document.querySelectorAll("[data-copy]")) {
    button.addEventListener("click", () => copyText(button.parentElement.querySelector("pre").textContent.trim() + "\n", "Commands copied"));
  }
  for (const button of document.querySelectorAll(".cmd-tabs button")) {
    button.addEventListener("click", () => {
      for (const other of document.querySelectorAll(".cmd-tabs button")) other.setAttribute("aria-selected", String(other === button));
      for (const block of document.querySelectorAll(".cmd")) block.hidden = block.dataset.shell !== button.dataset.shell;
    });
  }
}

initShell();
