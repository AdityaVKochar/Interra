// Interra judge console.
//
// Two sources feed this page and neither is invented here:
//   * LiveKit, for audio, the agent state attribute and live transcription
//     (the lk.transcription text streams the agent publishes);
//   * the worker trace (/events), for every gate decision and tool call.
// The replay plays one recorded trace with its original timestamps.

import { Orb } from "./orb.js";

const LIVEKIT_CLIENT = "https://cdn.jsdelivr.net/npm/livekit-client@2.15.8/+esm";
const PROMPTS = {
  voice: "Find flights to Las Vegas on August fifth. Oh, wait. Make it August eighth.",
  camera: "What does this code mean? Then: Book a check for Friday. Oh, wait. Make it Saturday. Then ask: Did it go through?",
};
const REPLAY_GAP_LIMIT = 2.5;
const MAX_LOG_ROWS = 3000;
const BAR_COUNT = 24;

const params = new URLSearchParams(location.search);
const reduceMotion = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
const $ = (id) => document.getElementById(id);

const cfg = {
  voice_agent: "interra-benchmark",
  camera_agent: "interra-camera-troubleshooter",
  commit_quiet_seconds: 0.6,
  temperature: 0,
  models: null,
  livekit_configured: true,
  livekit_host: "",
};

const el = {
  body: document.body,
  conn: $("conn"), connText: $("conn-text"), theme: $("theme"),
  modeVoice: $("mode-voice"), modeCamera: $("mode-camera"),
  pill: $("status-pill"), pillText: $("status-text"),
  orbWrap: $("orb-wrap"), orbCanvas: $("orb"), orbPulse: $("orb-pulse"),
  videoFrame: $("video-frame"), preview: $("preview"), frameNote: $("frame-note"),
  bars: $("bars"), hint: $("status"),
  now: $("now"), nowKind: $("now-kind"), nowText: $("now-text"), nowTime: $("now-time"), nowIcon: $("now-icon"),
  pipeline: $("pipeline"), toolStep: $("tool-step"),
  quiet: $("quiet"), quietBar: $("quiet-bar"), quietValue: $("quiet-value"), quietLabel: $("quiet-label"),
  mic: $("mic"), micWave: $("mic-wave"), cam: $("cam"),
  start: $("start"), startLabel: $("start-label"), elapsed: $("elapsed"),
  speaker: $("speaker"), replay: $("replay"), replayLabel: $("replay-label"), replay2: $("replay-2"),
  agentAudio: $("agent-audio"), prompt: $("prompt"),
  tx: $("tx"), txScroll: $("tx-scroll"), txEmpty: $("tx-empty"), txJump: $("tx-jump"),
  txBadge: $("tx-badge"), txBadgeText: $("tx-badge-text"), txCopy: $("tx-copy"), txClear: $("tx-clear"),
  log: $("log"), logScroll: $("log-scroll"), logEmpty: $("log-empty"), logCount: $("log-count"),
  filters: $("filters"), search: $("log-search"), logFollow: $("log-follow"), logCopy: $("log-copy"),
  logDownload: $("log-download"), logClear: $("log-clear"), logPaused: $("log-paused"),
  models: $("models"), toast: $("toast"),
};

// ---------- small helpers ----------

function h(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function svgIcon(name, className = "ic sm") {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("class", className);
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(ns, "use");
  use.setAttribute("href", "#i-" + name);
  svg.append(use);
  return svg;
}

const clamp = (value, low = 0, high = 1) => Math.min(high, Math.max(low, value));
const nowSeconds = () => Date.now() / 1000;
const errorText = (error) => (error && error.message ? error.message : String(error));

function randomId(length = 8) {
  const alphabet = "abcdefghijklmnopqrstuvwxyz0123456789";
  let out = "";
  for (const byte of crypto.getRandomValues(new Uint8Array(length))) out += alphabet[byte % alphabet.length];
  return out;
}

function fmtClock(seconds) {
  if (!Number.isFinite(seconds)) return "";
  const sign = seconds < 0 ? "-" : "+";
  const value = Math.abs(seconds);
  const minutes = Math.floor(value / 60);
  return sign + String(minutes).padStart(2, "0") + ":" + (value - minutes * 60).toFixed(3).padStart(6, "0");
}

function fmtShort(seconds) {
  const value = Math.max(0, seconds || 0);
  return String(Math.floor(value / 60)).padStart(2, "0") + ":" + String(Math.floor(value % 60)).padStart(2, "0");
}

function fmtNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? String(+number.toFixed(3)) : String(value);
}

function fmtValue(value) {
  if (typeof value === "string") return "“" + value + "”";
  if (typeof value === "number") return fmtNumber(value);
  if (value === null || value === undefined) return "none";
  return JSON.stringify(value);
}

function fmtCall(call) {
  const name = (call && call.function) || "tool";
  const args = (call && call.args) || {};
  const bits = Object.entries(args).map(([key, value]) => key.replace(/_/g, " ") + " " + fmtValue(value));
  return bits.length ? name + " · " + bits.join(" · ") : name;
}

function callKey(call) {
  return ((call && call.function) || "") + " " + JSON.stringify((call && call.args) || {});
}

function callDuration(call) {
  if (!call || typeof call.timestamp_start !== "number" || typeof call.timestamp_end !== "number") return "";
  return " · " + Math.max(0, Math.round((call.timestamp_end - call.timestamp_start) * 1000)) + " ms";
}

function resultSummary(result) {
  if (result === null || result === undefined) return "no result";
  if (typeof result !== "object") return String(result);
  const parts = [];
  if (result.status) parts.push(String(result.status));
  const list = Object.values(result).find(Array.isArray);
  if (list) parts.push(list.length + (list.length === 1 ? " item" : " items"));
  if (result.message) parts.push(String(result.message));
  return parts.join(" · ") || "done";
}

function hostOf(url) {
  try { return new URL(url.replace(/^ws/, "http")).host; } catch (error) { return url; }
}

function jsonBlock(value) {
  const pre = document.createElement("pre");
  const text = JSON.stringify(value, null, 2) ?? String(value);
  const pattern = /("(?:\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(?:true|false)\b|\bnull\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;
  let last = 0;
  let match;
  while ((match = pattern.exec(text))) {
    if (match.index > last) pre.append(text.slice(last, match.index));
    const token = match[0];
    let className = "j-num";
    if (token[0] === "\"") className = match[2] ? "j-key" : "j-str";
    else if (token === "true" || token === "false") className = "j-bool";
    else if (token === "null") className = "j-null";
    pre.append(h("span", className, token));
    last = match.index + token.length;
  }
  if (last < text.length) pre.append(text.slice(last));
  return pre;
}

let toastTimer = 0;
function toast(message) {
  el.toast.textContent = message;
  el.toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.toast.classList.remove("show"), 2200);
}

function copyText(text, done = "Copied") {
  if (!navigator.clipboard) { toast("Copy is not available in this browser"); return; }
  navigator.clipboard.writeText(text).then(() => toast(done), () => toast("Copy was blocked by the browser"));
}

function restartAnimation(node, className) {
  node.classList.remove(className);
  void node.offsetWidth;
  node.classList.add(className);
}

function hint(text, isError = false) {
  el.hint.textContent = text;
  el.hint.classList.toggle("err", isError);
}

// ---------- session state ----------

const app = {
  mode: "voice",
  phase: "idle", // idle | connecting | live | replay | ended
  session: 0,
  room: null,
  events: null,
  roomName: "",
  agentIdentity: "",
  agentPresent: false,
  agentState: null,
  agentFromAttribute: false,
  userSpeaking: false,
  quietSince: null,
  turnHadTool: false,
  micMuted: false,
  camOff: false,
  speakerMuted: false,
  audioBlocked: false,
  meters: { mic: null, agent: null },
  txSource: null, // stream | trace
  txBuffer: [],
  txTimer: 0,
  traceUserSegment: 0,
  traceAgentSegment: 0,
  pending: new Map(),
  sequence: 0,
  quiet: { active: false, seconds: 0.6, state: "holding", shownUntil: 0, value: 0, tool: "" },
  connectedAt: 0,
  traceSeen: false,
  traceWatch: 0,
  replay: null,
  endText: "",
  status: { tone: "", text: "", shimmer: null },
  lastNowKind: "Waiting",
};

function clockNow() {
  const replay = app.replay;
  if (replay) return replay.lastTime + ((performance.now() - replay.lastAt) / 1000) * replay.speed;
  return nowSeconds();
}

function agentName(mode = app.mode) {
  return mode === "camera" ? cfg.camera_agent : cfg.voice_agent;
}

function modeHint(mode) {
  return mode === "camera"
    ? "Camera mode. The camera worker must be running. Hold E1 up to the webcam."
    : "Voice mode. The benchmark worker must be running under the name " + cfg.voice_agent + ".";
}

// ---------- logs ----------

const CATEGORIES = [
  ["all", "All", null],
  ["speech", "Speech", "var(--heard)"],
  ["gate", "Gate", "var(--held)"],
  ["tool", "Tools", "var(--executed)"],
  ["agent", "Agent", "var(--cool)"],
  ["session", "Session", "var(--session)"],
  ["error", "Errors", "var(--error)"],
];

const USER_STATE_TEXT = { speaking: "You started speaking", listening: "You stopped speaking", away: "You are away" };
const AGENT_STATE_TEXT = {
  initializing: "Agent is starting",
  idle: "Agent is idle",
  listening: "Agent is listening",
  thinking: "Agent is thinking",
  speaking: "Agent is speaking",
};

const pick = (value, record) => (typeof value === "function" ? value(record) : value);

const KINDS = {
  session_started: { cat: "session", icon: "login", label: "session", msg: () => "Worker session started" },
  session_closed: {
    cat: (r) => (r.failed ? "error" : "session"), icon: "logout", label: "closed",
    msg: (r) => "Session closed" + (r.reason ? " · " + String(r.reason).replace("CloseReason.", "").toLowerCase() : "") + (r.failed ? " · failed" : ""),
  },
  session_cleanup: { cat: "session", icon: "logout", label: "cleanup", msg: () => "Speech providers released" },
  session_drain_started: { cat: "session", icon: "hourglass", label: "drain", msg: () => "Participant left; finishing pending speech" },
  session_drain_completed: { cat: "session", icon: "check", label: "drained", msg: () => "Pending speech finished" },
  session_drain_timeout: { cat: "error", icon: "alert", label: "drain", msg: () => "Pending speech did not finish in time" },
  participant_disconnected: { cat: "session", icon: "logout", label: "left", msg: () => "The participant left the room" },
  provider_cooldown_started: { cat: "session", icon: "hourglass", label: "cooldown", msg: (r) => "Provider cooldown of " + fmtNumber(r.seconds ?? 0) + " s before the next room" },
  provider_cooldown_completed: { cat: "session", icon: "check", label: "ready", msg: () => "Worker ready for the next room" },
  user_state: { cat: "speech", icon: "user", label: "you", msg: (r) => USER_STATE_TEXT[r.state] || "You are " + r.state },
  agent_state: { cat: "agent", icon: "bot", label: "agent", msg: (r) => AGENT_STATE_TEXT[r.state] || "Agent " + r.state },
  transcript: { cat: "speech", icon: "ear", label: (r) => (r.is_final ? "heard" : "hearing"), msg: (r) => r.transcript || "" },
  conversation_item: {
    cat: (r) => (r.role === "assistant" ? "agent" : "speech"),
    icon: (r) => (r.role === "assistant" ? "audio" : "message"),
    label: (r) => (r.role === "assistant" ? "said" : "turn"),
    msg: (r) => (r.text || "") + (r.interrupted ? "  · interrupted" : ""),
  },
  turn_held: { cat: "gate", icon: "hourglass", label: "turn held", msg: (r) => "Unfinished turn held: “" + (r.transcript || "") + "”" },
  turn_released: { cat: "gate", icon: "corner", label: "released", msg: (r) => "Held turn released (" + (r.reason || "") + "): “" + (r.transcript || "") + "”" },
  turn_release_failed: { cat: "error", icon: "alert", label: "release", msg: (r) => "Held turn could not be released: " + (r.error || "") },
  tool_call_pending: {
    cat: "gate", icon: "loader", label: "holding",
    msg: (r) => fmtCall(r.call) + " · waits for " + fmtNumber(r.quiet_seconds ?? cfg.commit_quiet_seconds) + " s of quiet",
  },
  tool_call_dropped: { cat: "gate", icon: "x-circle", label: "dropped", msg: (r) => fmtCall(r.call) + " · " + (r.reason || "dropped") + " · not logged" },
  tool_call_deduplicated: { cat: "gate", icon: "repeat", label: "reused", msg: (r) => fmtCall(r.call) + " · not run again" },
  tool_call: {
    cat: (r) => (r.status === "failed" ? "error" : "tool"),
    icon: (r) => (r.status === "failed" ? "alert" : "zap"),
    label: (r) => (r.status === "failed" ? "tool failed" : "executed"),
    msg: (r) => fmtCall(r.call) + callDuration(r.call) + " → " + resultSummary(r.result),
  },
  camera_frame: {
    cat: "agent", icon: "image", label: "frame",
    msg: (r) => (r.attached ? "Latest camera frame attached to this turn" + (r.width ? " · " + r.width + "×" + r.height : "") : "No camera frame for this turn"),
  },
  session_error: {
    cat: "error", icon: "alert", label: "error",
    msg: (r) => [r.source, r.error].filter(Boolean).join(": ") + (r.recoverable === false ? " · not recoverable" : ""),
  },
};

function entryFromRecord(record, source) {
  const meta = KINDS[record.kind] || {
    cat: "session", icon: "activity", label: String(record.kind || "event").replace(/_/g, " "),
    msg: (r) => {
      const { time, kind, room, ...rest } = r;
      return JSON.stringify(rest).slice(0, 240);
    },
  };
  return {
    t: typeof record.time === "number" ? record.time : clockNow(),
    kind: String(record.kind || "event"),
    cat: pick(meta.cat, record),
    icon: pick(meta.icon, record),
    label: pick(meta.label, record),
    msg: pick(meta.msg, record),
    src: source,
    interim: record.kind === "transcript" && !record.is_final,
    trace: true,
    data: record,
  };
}

class LogView {
  constructor() {
    this.entries = [];
    this.filter = "all";
    this.query = "";
    this.showInterim = false;
    this.follow = true;
    this.unseen = 0;
    this.base = null;
    this.total = {};
    this.interim = {};
    this.buttons = new Map();
    this.buildFilters();
    el.search.addEventListener("input", () => { this.query = el.search.value.trim().toLowerCase(); this.refilter(); });
    el.search.addEventListener("keydown", (event) => { if (event.key === "Escape") { el.search.value = ""; this.query = ""; this.refilter(); el.search.blur(); } });
    el.logScroll.addEventListener("scroll", () => {
      const atBottom = el.logScroll.scrollHeight - el.logScroll.scrollTop - el.logScroll.clientHeight < 28;
      if (atBottom !== this.follow) this.setFollow(atBottom, false);
    });
    el.logFollow.addEventListener("click", () => this.setFollow(!this.follow, true));
    el.logPaused.addEventListener("click", () => this.setFollow(true, true));
    el.logCopy.addEventListener("click", () => {
      const shown = this.entries.filter((entry) => !entry.row.hidden);
      if (!shown.length) { toast("No events to copy"); return; }
      copyText(shown.map((entry) => JSON.stringify(this.exportable(entry))).join("\n") + "\n", "Copied " + shown.length + " events");
    });
    el.logDownload.addEventListener("click", () => this.download());
    el.logClear.addEventListener("click", () => this.clear());
    el.log.addEventListener("click", (event) => {
      const row = event.target.closest(".log-row");
      if (!row || event.target.closest("pre")) return;
      const entry = this.entries.find((item) => item.row === row);
      if (!entry) return;
      if (!entry.pre) { entry.pre = jsonBlock(this.exportable(entry)); row.querySelector(".log-main").append(entry.pre); }
      row.classList.toggle("open");
    });
  }

  buildFilters() {
    for (const [id, label, color] of CATEGORIES) {
      const button = h("button");
      button.type = "button";
      button.setAttribute("aria-pressed", String(id === this.filter));
      if (color) { button.style.setProperty("--c", color); button.append(h("i")); }
      button.append(label);
      const count = h("em", null, "0");
      button.append(count);
      button.addEventListener("click", () => {
        this.filter = id;
        for (const [key, item] of this.buttons) item.button.setAttribute("aria-pressed", String(key === id));
        this.refilter();
      });
      el.filters.append(button);
      this.buttons.set(id, { button, count });
    }
    const interim = h("button", "toggle");
    interim.type = "button";
    interim.setAttribute("aria-pressed", "false");
    interim.title = "Show interim transcripts";
    interim.append("interim");
    interim.addEventListener("click", () => {
      this.showInterim = !this.showInterim;
      interim.setAttribute("aria-pressed", String(this.showInterim));
      this.refilter();
    });
    el.filters.append(interim);
  }

  setBase(time) { this.base = time; }

  exportable(entry) {
    if (entry.trace) return entry.data;
    return { time: entry.t, kind: entry.kind, source: entry.src, message: entry.msg, ...(entry.data ? { data: entry.data } : {}) };
  }

  add(entry) {
    if (this.base === null) this.base = entry.t;
    this.entries.push(entry);
    this.total[entry.cat] = (this.total[entry.cat] || 0) + 1;
    if (entry.interim) this.interim[entry.cat] = (this.interim[entry.cat] || 0) + 1;
    entry.row = this.render(entry);
    entry.row.hidden = !this.matches(entry);
    el.log.append(entry.row);
    while (this.entries.length > MAX_LOG_ROWS) {
      const old = this.entries.shift();
      old.row.remove();
      this.total[old.cat] -= 1;
      if (old.interim) this.interim[old.cat] -= 1;
    }
    this.updateCounts();
    if (!entry.row.hidden) {
      if (this.follow) this.scrollToEnd();
      else { this.unseen += 1; this.updatePaused(); }
    }
    return entry;
  }

  render(entry) {
    const row = h("li", "log-row new" + (entry.interim ? " interim" : ""));
    row.dataset.cat = entry.cat;
    row.dataset.kind = entry.kind;
    if (entry.pass !== undefined) row.dataset.pass = String(entry.pass);
    row.addEventListener("animationend", () => row.classList.remove("new"), { once: true });
    const time = h("time", null, this.base !== null ? fmtClock(entry.t - this.base) : "");
    time.dateTime = new Date(entry.t * 1000).toISOString();
    time.title = new Date(entry.t * 1000).toISOString();
    const main = h("div", "log-main");
    const line = h("div", "log-line");
    line.append(h("span", "log-kind", entry.label), h("span", "log-msg", entry.msg), h("span", "log-src", entry.src === "worker" ? "worker" : entry.src));
    main.append(line);
    row.append(time, svgIcon(entry.icon, "ic xs"), main);
    return row;
  }

  matches(entry) {
    if (entry.interim && !this.showInterim) return false;
    if (this.filter !== "all") {
      const cat = entry.cat === "result" ? "tool" : entry.cat;
      if (cat !== this.filter) return false;
    }
    if (this.query) {
      if (!entry.haystack) entry.haystack = (entry.label + " " + entry.kind + " " + entry.msg + " " + entry.src + " " + JSON.stringify(entry.data || {})).toLowerCase();
      if (!entry.haystack.includes(this.query)) return false;
    }
    return true;
  }

  refilter() {
    for (const entry of this.entries) entry.row.hidden = !this.matches(entry);
    this.updateCounts();
    if (this.follow) this.scrollToEnd();
  }

  updateCounts() {
    const shown = (cat) => (this.total[cat] || 0) - (this.showInterim ? 0 : this.interim[cat] || 0);
    let all = 0;
    for (const [id] of CATEGORIES) {
      if (id === "all") continue;
      const count = shown(id) + (id === "tool" ? shown("result") : 0);
      this.buttons.get(id).count.textContent = String(count);
      all += count;
    }
    this.buttons.get("all").count.textContent = String(all);
    const visible = this.entries.reduce((count, entry) => count + (entry.row.hidden ? 0 : 1), 0);
    el.logCount.textContent = visible === this.entries.length ? this.entries.length + " events" : visible + " of " + this.entries.length + " events";
    el.logEmpty.hidden = this.entries.length > 0;
  }

  setFollow(follow, scroll) {
    this.follow = follow;
    el.logFollow.setAttribute("aria-pressed", String(follow));
    if (follow) { this.unseen = 0; if (scroll) this.scrollToEnd(); }
    this.updatePaused();
  }

  updatePaused() {
    el.logPaused.textContent = this.unseen + (this.unseen === 1 ? " new event" : " new events") + " · follow";
    el.logPaused.classList.toggle("show", !this.follow && this.unseen > 0);
  }

  scrollToEnd() {
    el.logScroll.scrollTop = el.logScroll.scrollHeight;
  }

  download() {
    if (!this.entries.length) { toast("No events to download"); return; }
    const body = this.entries.map((entry) => JSON.stringify(this.exportable(entry))).join("\n") + "\n";
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([body], { type: "application/x-ndjson" }));
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    link.download = "interra-" + (app.roomName || "session") + "-" + stamp + ".jsonl";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 4000);
  }

  clear() {
    this.entries = [];
    this.total = {};
    this.interim = {};
    this.unseen = 0;
    el.log.replaceChildren();
    this.setFollow(true, false);
    this.updateCounts();
  }
}

// ---------- transcript ----------

class TranscriptView {
  constructor() {
    this.segments = new Map();
    this.chips = new Map();
    this.group = null;
    this.dots = null;
    this.dotsTimer = 0;
    this.base = null;
    this.stick = true;
    el.txScroll.addEventListener("scroll", () => {
      this.stick = el.txScroll.scrollHeight - el.txScroll.scrollTop - el.txScroll.clientHeight < 40;
      if (this.stick) el.txJump.classList.remove("show");
    });
    el.txJump.addEventListener("click", () => { this.stick = true; this.scrollToEnd(true); el.txJump.classList.remove("show"); });
    el.txCopy.addEventListener("click", () => {
      const text = this.text();
      if (!text) { toast("The transcript is empty"); return; }
      copyText(text, "Transcript copied");
    });
    el.txClear.addEventListener("click", () => this.clear());
  }

  setBase(time) { this.base = time; }

  stamp(time) {
    return this.base === null ? "" : fmtShort(time - this.base);
  }

  ensureGroup(role, time) {
    if (this.group && this.group.role === role && el.tx.lastElementChild === this.group.node) return this.group;
    const node = h("li", "msg " + role);
    const avatar = h("div", "avatar " + role, role === "user" ? "YOU" : "");
    const body = h("div", "msg-body");
    const meta = h("div", "msg-meta");
    meta.append(h("b", null, role === "user" ? "You" : "Interra"), h("span", null, this.stamp(time)));
    body.append(meta);
    node.append(avatar, body);
    el.tx.append(node);
    this.group = { role, node, body, meta };
    return this.group;
  }

  upsert(id, role, text, { final = false, time = clockNow(), interrupted = false } = {}) {
    let segment = this.segments.get(id);
    if (!segment) {
      if (!text) return;
      if (role === "agent") this.removeDots();
      const group = this.ensureGroup(role, time);
      const bubble = h("div", "bubble");
      group.body.append(bubble);
      segment = { id, role, bubble, group, text: "", final: false, time };
      this.segments.set(id, segment);
    }
    segment.text = text;
    segment.final = final;
    segment.bubble.textContent = text;
    segment.bubble.classList.toggle("interim", role === "user" && !final);
    segment.bubble.classList.toggle("streaming", role === "agent" && !final);
    segment.group.node.classList.toggle("streaming", role === "agent" && !final);
    if (interrupted) this.tag(segment.group, "interrupted");
    this.changed();
  }

  tag(group, label) {
    if (group.meta.querySelector(".tag[data-label='" + label + "']")) return;
    const tag = h("span", "tag warn", label);
    tag.dataset.label = label;
    group.meta.append(tag);
  }

  markInterrupted(role) {
    const segments = [...this.segments.values()].filter((segment) => segment.role === role);
    const last = segments[segments.length - 1];
    if (last) this.tag(last.group, "interrupted");
  }

  showDots() {
    clearTimeout(this.dotsTimer);
    if (this.dots) return;
    const group = this.ensureGroup("agent", clockNow());
    const dots = h("div", "bubble speaking-dots");
    dots.append(h("i"), h("i"), h("i"));
    dots.setAttribute("aria-label", "The agent is speaking");
    group.body.append(dots);
    group.node.classList.add("streaming");
    this.dots = { node: dots, group };
    this.changed();
  }

  removeDots() {
    clearTimeout(this.dotsTimer);
    if (!this.dots) return;
    const { node, group } = this.dots;
    node.remove();
    group.node.classList.remove("streaming");
    if (!group.body.querySelector(".bubble")) {
      group.node.remove();
      if (this.group === group) this.group = null;
    }
    this.dots = null;
    this.changed();
  }

  removeDotsSoon() {
    clearTimeout(this.dotsTimer);
    this.dotsTimer = setTimeout(() => this.removeDots(), 1500);
  }

  chip(key, kind, title, text, { icon = "info", time = clockNow(), details, note } = {}) {
    let chip = this.chips.get(key);
    if (!chip) {
      const node = h("li", "event-chip");
      chip = { node, time };
      this.chips.set(key, chip);
      el.tx.append(node);
      this.group = null;
    } else {
      restartAnimation(chip.node, "flash");
    }
    chip.kind = kind;
    chip.title = title;
    chip.text = text;
    chip.node.dataset.kind = kind;
    const parts = [svgIcon(icon, "ic sm"), h("b", null, title + " · " + this.stamp(chip.time)), h("span", null, text + (note ? " " + note : ""))];
    if (details !== undefined && details !== null) {
      const more = h("details");
      more.append(h("summary", null, "details"), jsonBlock(details));
      parts.push(more);
    }
    chip.node.replaceChildren(...parts);
    this.changed();
  }

  changed() {
    el.txEmpty.hidden = el.tx.children.length > 0;
    if (this.stick) this.scrollToEnd(false);
    else el.txJump.classList.add("show");
  }

  scrollToEnd(smooth) {
    el.txScroll.scrollTo({ top: el.txScroll.scrollHeight, behavior: smooth && !reduceMotion ? "smooth" : "auto" });
  }

  clear() {
    this.segments.clear();
    this.chips.clear();
    this.group = null;
    this.dots = null;
    clearTimeout(this.dotsTimer);
    el.tx.replaceChildren();
    this.stick = true;
    el.txJump.classList.remove("show");
    this.changed();
  }

  text() {
    const lines = [];
    for (const node of el.tx.children) {
      if (node.classList.contains("event-chip")) {
        const chip = [...this.chips.values()].find((item) => item.node === node);
        if (chip) lines.push("[" + this.stamp(chip.time) + "] · " + chip.title + " " + chip.text);
        continue;
      }
      const role = node.classList.contains("user") ? "You" : "Interra";
      for (const segment of this.segments.values()) {
        if (segment.group.node === node) lines.push("[" + this.stamp(segment.time) + "] " + role + ": " + segment.text);
      }
    }
    return lines.join("\n");
  }
}

function setTranscriptBadge(text, on, source = "") {
  el.txBadgeText.textContent = text;
  el.txBadge.dataset.on = String(on);
  if (source) el.txBadge.dataset.source = source;
  else delete el.txBadge.dataset.source;
}

// ---------- gate card ----------

const NOW_ICONS = {
  Waiting: "gate", Heard: "ear", Held: "hourglass", Holding: "loader", Released: "corner",
  Dropped: "x-circle", Executed: "zap", Reused: "repeat", Said: "audio", Error: "alert",
};

function pipelineFor(kind) {
  const tool = app.turnHadTool ? "done" : "";
  return {
    Waiting: {},
    Heard: { heard: "on" },
    Held: { heard: "done", gate: "on" },
    Released: { heard: "done", gate: "done" },
    Holding: { heard: "done", gate: "on" },
    Dropped: { heard: "done", gate: "done", tool: "on" },
    Executed: { heard: "done", gate: "done", tool: "on" },
    Reused: { heard: "done", gate: "done", tool: "on" },
    Said: { heard: "done", gate: app.turnHadTool ? "done" : "", tool, said: "on" },
    Error: { tool: "on" },
  }[kind] || {};
}

function setNow(kind, text, time) {
  const changed = app.lastNowKind !== kind;
  app.lastNowKind = kind;
  el.now.dataset.kind = kind;
  el.nowKind.textContent = kind;
  if (el.nowText.textContent !== text) {
    el.nowText.textContent = text;
    if (changed) restartAnimation(el.nowText, "swap");
  }
  if (changed) el.nowIcon.replaceChildren(svgIcon(NOW_ICONS[kind] || "gate"));
  el.nowTime.textContent = typeof time === "number" && logs.base !== null ? fmtClock(time - logs.base) : "";
  const steps = pipelineFor(kind);
  for (const step of el.pipeline.children) {
    const state = steps[step.dataset.step];
    step.dataset.on = state === "on" ? "true" : state === "done" ? "done" : "false";
  }
  el.toolStep.textContent = ["Dropped", "Executed", "Reused"].includes(kind) ? kind : "Tool";
}

function pulse(kind) {
  const color = { executed: "var(--executed)", dropped: "var(--dropped)", reused: "var(--reused)", held: "var(--held)", frame: "var(--cool)" }[kind];
  if (!color) return;
  el.orbPulse.style.setProperty("--pulse", color);
  restartAnimation(el.orbPulse, "go");
}

function updateQuiet() {
  const quiet = app.quiet;
  if (!quiet.active) {
    if (el.quiet.classList.contains("keep") && performance.now() > quiet.shownUntil) el.quiet.classList.remove("keep");
    if (!el.quiet.classList.contains("keep")) return;
  } else if (app.userSpeaking || app.quietSince === null) {
    quiet.value = 0;
    el.quietLabel.textContent = "Waiting for you to finish";
  } else {
    quiet.value = clamp((clockNow() - app.quietSince) / quiet.seconds);
    el.quietLabel.textContent = "Quiet window";
  }
  el.quietBar.style.transform = "scaleX(" + quiet.value.toFixed(3) + ")";
  el.quietValue.textContent = (quiet.value * quiet.seconds).toFixed(1) + " / " + quiet.seconds.toFixed(1) + " s";
}

// ---------- trace records ----------

function onTraceRecord(record, source) {
  if (!record || typeof record !== "object") return;
  app.traceSeen = true;
  logs.add(entryFromRecord(record, source));
  switch (record.kind) {
    case "user_state": {
      const speaking = record.state === "speaking";
      if (speaking && !app.userSpeaking && app.lastNowKind === "Said") app.turnHadTool = false;
      app.userSpeaking = speaking;
      app.quietSince = speaking ? null : record.time;
      break;
    }
    case "agent_state":
      setAgentState(record.state, source === "replay" ? "replay" : "trace");
      break;
    case "transcript":
      if (record.is_final && !app.userSpeaking) app.quietSince = record.time;
      if (record.transcript) setNow("Heard", record.transcript, record.time);
      traceTranscript(record);
      break;
    case "conversation_item":
      if (record.role === "assistant" && record.text) {
        setNow("Said", record.text, record.time);
        if (app.txSource === "stream" && record.interrupted) transcript.markInterrupted("agent");
      }
      traceTranscript(record);
      break;
    case "turn_held":
      setNow("Held", "Holding the call until you finish. " + (record.transcript || ""), record.time);
      transcript.chip("held:" + ++app.sequence, "held", "Turn held", "Waiting for you to finish: “" + (record.transcript || "") + "”", { icon: "hourglass", time: record.time });
      pulse("held");
      break;
    case "turn_released":
      setNow("Released", "Released the held turn (" + (record.reason || "silence") + "). " + (record.transcript || ""), record.time);
      break;
    case "tool_call_pending":
      startPending(record);
      break;
    case "tool_call_dropped":
      resolvePending(record, "dropped");
      break;
    case "tool_call_deduplicated":
      resolvePending(record, "reused");
      break;
    case "tool_call":
      resolvePending(record, record.status === "failed" ? "failed" : "executed");
      break;
    case "camera_frame":
      showFrame(record);
      break;
    case "session_error":
      if (source !== "replay") hint("Worker error: " + (record.error || "unknown"), true);
      break;
    default:
      break;
  }
}

function startPending(record) {
  app.turnHadTool = true;
  const key = callKey(record.call);
  const chipKey = "call:" + ++app.sequence;
  const seconds = Number(record.quiet_seconds ?? cfg.commit_quiet_seconds) || 0.6;
  transcript.chip(chipKey, "holding", "Holding", fmtCall(record.call), {
    icon: "loader", time: record.time, note: "· runs after " + fmtNumber(seconds) + " s of quiet",
  });
  const waiting = app.pending.get(key) || [];
  waiting.push(chipKey);
  app.pending.set(key, waiting);
  Object.assign(app.quiet, { active: true, seconds, state: "holding", value: 0, tool: (record.call && record.call.function) || "the call" });
  el.quiet.dataset.state = "holding";
  el.quiet.classList.add("keep");
  setNow("Holding", "Holding " + fmtCall(record.call) + " until you have been quiet for " + fmtNumber(seconds) + " s. If you keep speaking it is dropped before it is logged.", record.time);
}

const OUTCOMES = {
  dropped: { chip: "dropped", title: "Dropped", icon: "x-circle", now: "Dropped", pulse: "dropped" },
  executed: { chip: "executed", title: "Executed", icon: "zap", now: "Executed", pulse: "executed" },
  failed: { chip: "dropped", title: "Tool failed", icon: "alert", now: "Error", pulse: "dropped" },
  reused: { chip: "reused", title: "Reused", icon: "repeat", now: "Reused", pulse: "reused" },
};

function resolvePending(record, outcome) {
  app.turnHadTool = true;
  const meta = OUTCOMES[outcome];
  const key = callKey(record.call);
  const waiting = app.pending.get(key);
  const held = Boolean(waiting && waiting.length);
  const chipKey = held ? waiting.shift() : "call:" + ++app.sequence;
  if (waiting && !waiting.length) app.pending.delete(key);
  const text = fmtCall(record.call);
  const notes = {
    dropped: "· you kept speaking, so it was not logged",
    reused: "· identical call in this room; the first result was reused",
    executed: callDuration(record.call),
    failed: "· " + resultSummary(record.result),
  };
  transcript.chip(chipKey, meta.chip, meta.title, text, {
    icon: meta.icon, time: record.time, note: notes[outcome],
    details: outcome === "executed" || outcome === "failed" ? record.result : undefined,
  });
  const lines = {
    dropped: "Dropped " + text + ". You kept speaking, so this call was not logged.",
    executed: "Executed " + text + ".",
    failed: text + " failed: " + resultSummary(record.result) + ".",
    reused: "Reused " + text + ". It was not run again.",
  };
  setNow(meta.now, lines[outcome], record.time);
  pulse(meta.pulse);
  if (held && app.pending.size === 0) {
    app.quiet.active = false;
    app.quiet.state = outcome === "failed" ? "dropped" : outcome;
    if (outcome !== "dropped") app.quiet.value = 1;
    el.quiet.dataset.state = app.quiet.state;
    el.quiet.classList.add("keep");
    app.quiet.shownUntil = performance.now() + 2800;
    updateQuiet();
  }
}

let frameNoteTimer = 0;
function showFrame(record) {
  const text = record.attached
    ? "Frame attached to your turn" + (record.width ? " · " + record.width + "×" + record.height : "")
    : "No camera frame reached this turn";
  el.frameNote.textContent = text;
  el.frameNote.classList.add("flash");
  clearTimeout(frameNoteTimer);
  frameNoteTimer = setTimeout(() => {
    el.frameNote.classList.remove("flash");
    el.frameNote.textContent = "Your latest frame joins your next spoken turn.";
  }, 2400);
  transcript.chip("frame:" + ++app.sequence, record.attached ? "frame" : "system", record.attached ? "Frame" : "No frame", text, { icon: "image", time: record.time });
  if (record.attached) pulse("frame");
}

function traceTranscript(record) {
  if (app.txSource === "stream") return;
  if (app.txSource === null) {
    app.txBuffer.push(record);
    if (!app.txTimer) {
      const session = app.session;
      app.txTimer = setTimeout(() => {
        app.txTimer = 0;
        if (session !== app.session || app.txSource !== null) return;
        app.txSource = "trace";
        setTranscriptBadge("trace", true);
        clientLog("transcript_source", "No LiveKit transcription stream arrived; the transcript is built from the worker trace", { icon: "info" });
        const buffered = app.txBuffer;
        app.txBuffer = [];
        for (const item of buffered) applyTraceTranscript(item);
      }, 2500);
    }
    return;
  }
  applyTraceTranscript(record);
}

function applyTraceTranscript(record) {
  if (record.kind === "transcript") {
    const text = (record.transcript || "").trim();
    if (!text) return;
    transcript.upsert("tu-" + app.traceUserSegment, "user", text, { final: Boolean(record.is_final), time: record.time });
    if (record.is_final) app.traceUserSegment += 1;
  } else if (record.kind === "conversation_item" && record.role === "assistant" && record.text) {
    transcript.upsert("ta-" + app.traceAgentSegment++, "agent", record.text, { final: true, time: record.time, interrupted: Boolean(record.interrupted) });
  }
}

function setAgentState(state, from) {
  if (!state) return;
  if (from === "attribute") app.agentFromAttribute = true;
  else if (from === "trace" && app.agentFromAttribute && app.phase === "live") return;
  const previous = app.agentState;
  app.agentState = state;
  if (state === "speaking" && app.txSource === "trace") transcript.showDots();
  if (previous === "speaking" && state !== "speaking") transcript.removeDotsSoon();
}

function clientLog(kind, msg, { cat = "session", icon = "activity", data, src = app.phase === "replay" ? "replay" : "browser", t } = {}) {
  return logs.add({ t: t ?? clockNow(), kind, cat, icon, label: kind.replace(/_/g, " "), msg, src, interim: false, data });
}

// ---------- audio ----------

let audioContext = null;
function getAudioContext() {
  if (!audioContext) {
    const Context = window.AudioContext || window.webkitAudioContext;
    if (!Context) return null;
    audioContext = new Context();
  }
  if (audioContext.state === "suspended") audioContext.resume().catch(() => {});
  return audioContext;
}

class Meter {
  constructor(track) {
    this.ok = false;
    this.level = 0;
    const context = getAudioContext();
    if (!context || !track) return;
    try {
      this.source = context.createMediaStreamSource(new MediaStream([track]));
      this.analyser = context.createAnalyser();
      this.analyser.fftSize = 1024;
      this.analyser.smoothingTimeConstant = 0.55;
      this.analyser.minDecibels = -92;
      this.analyser.maxDecibels = -18;
      this.source.connect(this.analyser);
      this.samples = new Float32Array(this.analyser.fftSize);
      this.spectrum = new Uint8Array(this.analyser.frequencyBinCount);
      this.binHz = context.sampleRate / this.analyser.fftSize;
      this.ok = true;
    } catch (error) {
      this.ok = false;
    }
  }

  sample() {
    if (!this.ok) return 0;
    this.analyser.getFloatTimeDomainData(this.samples);
    let sum = 0;
    for (let i = 0; i < this.samples.length; i++) sum += this.samples[i] * this.samples[i];
    const decibels = 20 * Math.log10(Math.sqrt(sum / this.samples.length) + 1e-9);
    const target = clamp((decibels + 58) / 46);
    this.level += (target - this.level) * (target > this.level ? 0.55 : 0.12);
    return this.level;
  }

  bands(out) {
    if (!this.ok) return out.fill(0);
    this.analyser.getByteFrequencyData(this.spectrum);
    const low = 90;
    const high = 5200;
    for (let i = 0; i < out.length; i++) {
      const from = Math.max(1, Math.floor((low * Math.pow(high / low, i / out.length)) / this.binHz));
      const to = Math.max(from + 1, Math.ceil((low * Math.pow(high / low, (i + 1) / out.length)) / this.binHz));
      let peak = 0;
      for (let bin = from; bin < to && bin < this.spectrum.length; bin++) peak = Math.max(peak, this.spectrum[bin]);
      out[i] = Math.pow(peak / 255, 1.7);
    }
    return out;
  }

  close() {
    try { if (this.source) this.source.disconnect(); } catch (error) { /* already closed */ }
    this.ok = false;
  }
}

// ---------- visuals ----------

const orb = new Orb(el.orbCanvas, { reduceMotion });
if (!orb.ok) el.orbWrap.classList.add("no-webgl");

const bars = [];
for (let i = 0; i < BAR_COUNT; i++) {
  const bar = document.createElement("i");
  el.bars.append(bar);
  bars.push(bar);
}
const bandBuffer = new Float32Array(BAR_COUNT / 2);
const barHeights = new Float32Array(BAR_COUNT);
const micHistory = new Array(26).fill(0);
let micTick = 0;
let micDrawnEmpty = false;
let palette = {};

function readPalette() {
  const style = getComputedStyle(document.documentElement);
  palette = { warm: style.getPropertyValue("--warm").trim() || "#ff7a1a", muted: style.getPropertyValue("--text-3").trim() || "#666" };
  micDrawnEmpty = false;
}

function wobble(time, seed) {
  return 0.5 + 0.25 * Math.sin(time * 7.3 + seed * 1.7) + 0.25 * Math.sin(time * 3.1 + seed * 0.9);
}

function visualState() {
  if (app.phase === "connecting") return "connecting";
  if (app.phase === "live") {
    if (!app.agentPresent || app.agentState === "initializing") return "connecting";
    if (app.quiet.active) return "holding";
    return app.agentState || "listening";
  }
  if (app.phase === "replay") {
    if (app.quiet.active) return "holding";
    return app.agentState || "idle";
  }
  return "idle";
}

function orbMix(state) {
  if (state === "speaking") return 1;
  if (state === "thinking") return 0.64;
  if (state === "holding") return 0.42;
  if (state === "listening") return app.userSpeaking ? 0.02 : 0.32;
  return app.userSpeaking ? 0.04 : 0.5;
}

function drawBars(time, state, input, output) {
  let tone = "idle";
  let meter = null;
  let level = 0;
  const highlight = new Set();
  barHeights.fill(0.12);
  if (state === "speaking") { tone = "agent"; meter = app.meters.agent; level = output; }
  else if (app.userSpeaking && (app.phase === "live" || app.phase === "replay")) { tone = "user"; meter = app.micMuted ? null : app.meters.mic; level = input; }
  if (tone !== "idle") {
    const half = BAR_COUNT / 2;
    if (meter && meter.ok) meter.bands(bandBuffer);
    for (let i = 0; i < half; i++) {
      const value = meter && meter.ok ? bandBuffer[i] : wobble(time, i) * (0.35 + level * 0.9);
      const height = 0.12 + 0.88 * clamp(value * (1.15 - i / (half * 2.2)));
      barHeights[half - 1 - i] = height;
      barHeights[half + i] = height;
    }
  } else if (state === "connecting") {
    const step = Math.floor((time * 1000) / (1600 / (BAR_COUNT / 2))) % (BAR_COUNT / 2);
    highlight.add(step).add(BAR_COUNT - 1 - step);
    for (const index of highlight) barHeights[index] = 0.42;
  } else if (state === "listening") {
    if (Math.floor(time * 2) % 2 === 0) { highlight.add(BAR_COUNT / 2 - 1).add(BAR_COUNT / 2); }
  } else if (state === "thinking" || state === "holding") {
    tone = "think";
    const offset = Math.floor((time * 1000) / 150) % 4;
    highlight.add(BAR_COUNT / 2 - 1 - offset).add(BAR_COUNT / 2 + offset);
    for (const index of highlight) barHeights[index] = 0.3;
  } else {
    for (let i = 0; i < BAR_COUNT; i++) barHeights[i] = 0.1 + 0.05 * (0.5 + 0.5 * Math.sin(time * 1.4 + i * 0.45));
  }
  if (el.bars.dataset.tone !== tone) el.bars.dataset.tone = tone;
  for (let i = 0; i < BAR_COUNT; i++) {
    bars[i].style.transform = "scaleY(" + barHeights[i].toFixed(3) + ")";
    const on = highlight.has(i);
    if (bars[i].classList.contains("hl") !== on) bars[i].classList.toggle("hl", on);
  }
}

function drawMicWave(dt, level, active) {
  micTick += dt;
  if (micTick >= 0.05) {
    micTick = 0;
    micHistory.shift();
    micHistory.push(active ? level : 0);
  }
  const empty = micHistory.every((value) => value < 0.005);
  if (empty && micDrawnEmpty) return;
  micDrawnEmpty = empty;
  const canvas = el.micWave;
  const context = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  context.clearRect(0, 0, width, height);
  const count = micHistory.length;
  const gap = 2.4;
  const barWidth = (width - gap * (count - 1)) / count;
  context.fillStyle = app.micMuted || !active ? palette.muted : palette.warm;
  context.globalAlpha = app.micMuted || !active ? 0.55 : 1;
  for (let i = 0; i < count; i++) {
    const barHeight = Math.max(4, micHistory[i] * (height - 6));
    const x = i * (barWidth + gap);
    const y = (height - barHeight) / 2;
    if (context.roundRect) { context.beginPath(); context.roundRect(x, y, barWidth, barHeight, barWidth / 2); context.fill(); }
    else context.fillRect(x, y, barWidth, barHeight);
  }
  context.globalAlpha = 1;
}

function updateStatus() {
  const state = visualState();
  let tone = "idle";
  let text = "Ready";
  let shimmer = false;
  if (app.phase === "ended") {
    text = app.endText || "Call ended";
  } else if (app.phase !== "idle") {
    if (state === "connecting") {
      tone = "wait";
      shimmer = true;
      text = app.phase === "connecting" ? "Connecting…" : app.agentPresent ? "Agent is starting…" : "Waiting for " + agentName() + " to join…";
    } else if (state === "holding") {
      tone = "hold";
      text = "Holding " + app.quiet.tool + " until you are quiet";
    } else if (state === "thinking") {
      tone = "think";
      shimmer = true;
      text = "Thinking…";
    } else if (state === "speaking") {
      tone = "agent";
      text = "Speaking";
    } else if (app.userSpeaking) {
      tone = "user";
      text = "Listening to you";
    } else if (app.phase === "replay" && state === "idle") {
      tone = "wait";
      text = "Waiting for the recording";
    } else {
      tone = "live";
      text = "Listening";
    }
    if (app.phase === "replay") text = "Replay · " + text;
  }
  const status = app.status;
  if (status.tone !== tone) { status.tone = tone; el.pill.dataset.tone = tone; }
  if (status.text !== text) { status.text = text; el.pillText.textContent = text; }
  if (status.shimmer !== shimmer) { status.shimmer = shimmer; el.pillText.classList.toggle("on", shimmer && !reduceMotion); }
}

let lastFrame = performance.now();
let lastUser = "";
let lastElapsed = "";
function frame(now) {
  const dt = Math.min(0.1, Math.max(0, (now - lastFrame) / 1000));
  lastFrame = now;
  const time = now / 1000;
  const state = visualState();
  const micLevel = app.meters.mic ? app.meters.mic.sample() : 0;
  const agentLevel = app.meters.agent ? app.meters.agent.sample() : 0;
  let input = app.micMuted ? 0 : micLevel;
  let output = agentLevel;
  if (!app.meters.agent && state === "speaking") output = 0.3 + 0.35 * wobble(time, 3);
  if (!app.meters.mic && app.userSpeaking) input = 0.25 + 0.3 * wobble(time * 1.2, 7);
  if (state === "idle" && !app.userSpeaking) output = Math.max(output, 0.05 + 0.04 * Math.sin(time * 1.3));
  const think = state === "thinking" ? 1 : state === "holding" ? 0.55 : state === "connecting" ? 0.35 : 0;
  orb.set({ input, output, mix: orbMix(state), think });
  orb.render(dt);
  if (!orb.ok) el.orbWrap.style.setProperty("--lvl", Math.max(input, output).toFixed(3));
  const user = app.userSpeaking || (app.phase === "live" && micLevel > 0.32) ? "speaking" : "quiet";
  if (user !== lastUser) { lastUser = user; el.orbWrap.dataset.user = user; }
  drawBars(time, state, input, output);
  drawMicWave(dt, micLevel, app.phase === "live" && !app.micMuted);
  updateQuiet();
  updateStatus();
  if (app.phase === "live" && app.connectedAt) {
    const elapsed = fmtShort((now - app.connectedAt) / 1000);
    if (elapsed !== lastElapsed) { lastElapsed = elapsed; el.elapsed.textContent = elapsed; }
  }
  requestAnimationFrame(frame);
}

// ---------- phase and controls ----------

function setConn(state) {
  el.conn.dataset.state = state;
  el.connText.textContent = { idle: "Offline", connecting: "Connecting", live: "Live", reconnecting: "Reconnecting", replay: "Replay", ended: "Offline" }[state] || state;
  const project = cfg.livekit_host ? "LiveKit project " + cfg.livekit_host : "LiveKit project not configured";
  el.conn.title = state === "live" ? project + " · room " + app.roomName : project;
}

function setPhase(phase) {
  app.phase = phase;
  el.body.dataset.phase = phase;
  const live = phase === "live";
  const connecting = phase === "connecting";
  const replay = phase === "replay";
  el.start.dataset.state = live ? "live" : connecting ? "connecting" : "idle";
  el.startLabel.textContent = live ? "End" : connecting ? "Connecting" : "Start";
  el.start.querySelector(".phone use").setAttribute("href", live ? "#i-phone-off" : "#i-phone");
  el.start.setAttribute("aria-label", live ? "End the session" : "Start a " + app.mode + " session");
  el.elapsed.hidden = !live;
  el.mic.disabled = !live;
  el.cam.disabled = !live;
  el.replayLabel.textContent = replay ? "Stop replay" : "Replay scored run";
  el.replay.querySelector("use").setAttribute("href", replay ? "#i-stop" : "#i-rotate");
  el.replay2.replaceChildren(svgIcon(replay ? "stop" : "play"), replay ? "Stop replay" : "Replay this recording");
  setConn(live ? "live" : connecting ? "connecting" : replay ? "replay" : "idle");
  if (!live && !replay) setTranscriptBadge(phase === "connecting" ? "waiting" : "idle", false);
}

function resetSession() {
  clearTimeout(app.txTimer);
  clearTimeout(app.traceWatch);
  Object.assign(app, {
    agentIdentity: "", agentPresent: false, agentState: null, agentFromAttribute: false,
    userSpeaking: false, quietSince: null, turnHadTool: false, micMuted: false, camOff: false,
    txSource: null, txBuffer: [], txTimer: 0, traceUserSegment: 0, traceAgentSegment: 0,
    traceSeen: false, traceWatch: 0, connectedAt: 0, endText: "", lastNowKind: "",
  });
  app.pending.clear();
  Object.assign(app.quiet, { active: false, value: 0, state: "holding", shownUntil: 0, tool: "" });
  el.quiet.classList.remove("keep");
  el.mic.setAttribute("aria-pressed", "false");
  el.cam.setAttribute("aria-pressed", "false");
  logs.clear();
  transcript.clear();
  setNow("Waiting", "Nothing has been decided yet.");
}

async function loadLiveKit() {
  return import(LIVEKIT_CLIENT);
}

async function startCall() {
  if (app.phase === "connecting") return;
  if (app.phase === "live") { await endCall("You left the room."); return; }
  if (app.phase === "replay") stopReplay(false);
  const session = ++app.session;
  resetSession();
  getAudioContext();
  app.roomName = "demo-" + app.mode + "-" + randomId(8);
  const base = nowSeconds();
  logs.setBase(base);
  transcript.setBase(base);
  setPhase("connecting");
  hint("Opening a room for " + agentName() + ".");
  clientLog("connecting", "Opening room " + app.roomName, { icon: "link", data: { room: app.roomName, mode: app.mode, agent: agentName() } });
  try {
    const LK = await loadLiveKit();
    if (session !== app.session) return;
    openTrace(app.roomName, session);
    const response = await fetch("/token?mode=" + app.mode + "&room=" + encodeURIComponent(app.roomName), { cache: "no-store" });
    if (!response.ok) throw new Error((await response.text()) || "could not open a room (" + response.status + ")");
    const { url, token } = await response.json();
    if (session !== app.session) return;
    clientLog("token", "Token minted on this machine; dispatching " + agentName(), { icon: "check", data: { room: app.roomName, agent: agentName(), livekit: hostOf(url) } });
    const room = new LK.Room({
      adaptiveStream: true,
      dynacast: true,
      audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    app.room = room;
    wireRoom(LK, room, session);
    room.registerTextStreamHandler("lk.transcription", (reader, participant) => onTranscription(room, session, reader, participant));
    await room.connect(url, token);
    if (session !== app.session) { room.disconnect(); return; }
    app.connectedAt = performance.now();
    setPhase("live");
    setTranscriptBadge("live", true);
    clientLog("room_connected", "Connected to " + hostOf(url), { icon: "link", data: { room: app.roomName, livekit: hostOf(url) } });
    try { await room.startAudio(); } catch (error) { /* allowed after the next click */ }
    await room.localParticipant.setMicrophoneEnabled(true);
    if (session !== app.session) return;
    const microphone = room.localParticipant.getTrackPublication(LK.Track.Source.Microphone);
    if (microphone && microphone.track && microphone.track.mediaStreamTrack) app.meters.mic = new Meter(microphone.track.mediaStreamTrack);
    if (app.mode === "camera") {
      await room.localParticipant.setCameraEnabled(true);
      if (session !== app.session) return;
      attachPreview(room, LK);
    }
    for (const participant of room.remoteParticipants.values()) if (participant.isAgent) agentJoined(participant);
    hint(app.mode === "camera"
      ? "Connected. The mic waveform must move while you talk. Hold E1 in the picture, then say the line."
      : "Connected. The mic waveform must move while you talk. Say the line, pause after fifth, then correct it.");
  } catch (error) {
    if (session !== app.session) return;
    clientLog("start_failed", "Did not start: " + errorText(error), { cat: "error", icon: "alert" });
    app.session += 1;
    await teardown();
    app.endText = "Did not start";
    setPhase("ended");
    hint("Did not start: " + errorText(error), true);
  }
}

function wireRoom(LK, room, session) {
  const E = LK.RoomEvent;
  const alive = () => session === app.session && app.room === room;
  room.on(E.ParticipantConnected, (participant) => { if (alive() && participant.isAgent) agentJoined(participant); });
  room.on(E.ParticipantDisconnected, (participant) => {
    if (!alive() || !participant.isAgent || participant.identity !== app.agentIdentity) return;
    app.agentPresent = false;
    app.agentState = null;
    clientLog("agent_left", "Agent left · " + participant.identity, { cat: "agent", icon: "logout" });
  });
  room.on(E.ParticipantAttributesChanged, (changed, participant) => {
    if (!alive() || !participant.isAgent || !("lk.agent.state" in changed)) return;
    setAgentState(changed["lk.agent.state"], "attribute");
  });
  room.on(E.TrackSubscribed, (track, publication, participant) => {
    if (alive() && track.kind === LK.Track.Kind.Audio) attachAgentAudio(room, track, participant);
  });
  room.on(E.TrackUnsubscribed, (track) => {
    if (!alive() || track.kind !== LK.Track.Kind.Audio) return;
    track.detach();
    if (app.meters.agent) { app.meters.agent.close(); app.meters.agent = null; }
  });
  room.on(E.AudioPlaybackStatusChanged, () => { if (alive()) setAudioBlocked(!room.canPlaybackAudio); });
  room.on(E.Reconnecting, () => {
    if (!alive()) return;
    setConn("reconnecting");
    clientLog("reconnecting", "Connection lost; reconnecting", { cat: "error", icon: "alert" });
  });
  room.on(E.Reconnected, () => {
    if (!alive()) return;
    setConn("live");
    clientLog("reconnected", "Reconnected", { icon: "check" });
  });
  room.on(E.Disconnected, (reason) => {
    if (!alive()) return;
    clientLog("disconnected", "The room closed" + (reason !== undefined ? " (" + reason + ")" : ""), { icon: "logout" });
    app.session += 1;
    teardown().then(() => {
      app.endText = "Call ended";
      setPhase("ended");
      hint("The room closed.");
    });
  });
  room.on(E.ConnectionQualityChanged, (quality, participant) => {
    if (alive() && participant === room.localParticipant) el.conn.dataset.quality = String(quality);
  });
  room.on(E.MediaDevicesError, (error) => {
    if (!alive()) return;
    clientLog("device_error", "Microphone or camera error: " + errorText(error), { cat: "error", icon: "alert" });
    hint("Microphone or camera error: " + errorText(error), true);
  });
  room.on(E.LocalTrackPublished, (publication) => {
    if (!alive()) return;
    const camera = publication.source === LK.Track.Source.Camera;
    clientLog(camera ? "camera_on" : "mic_on", (camera ? "Camera" : "Microphone") + " published", { icon: camera ? "video" : "mic" });
  });
}

function agentJoined(participant) {
  if (app.agentIdentity === participant.identity && app.agentPresent) return;
  app.agentIdentity = participant.identity;
  app.agentPresent = true;
  clientLog("agent_joined", "Agent joined · " + participant.identity, { cat: "agent", icon: "bot", data: { identity: participant.identity, name: participant.name, attributes: participant.attributes } });
  const state = participant.attributes && participant.attributes["lk.agent.state"];
  if (state) setAgentState(state, "attribute");
  const session = app.session;
  clearTimeout(app.traceWatch);
  app.traceWatch = setTimeout(() => {
    if (session !== app.session || app.traceSeen) return;
    clientLog("trace_missing", "No worker trace for this room yet. The worker may run on another machine, or INTERRA_FDB_TRACE_DIR differs from this page's. Transcription and audio still work.", { icon: "info" });
  }, 10000);
}

function attachAgentAudio(room, track, participant) {
  const element = track.attach();
  element.autoplay = true;
  element.muted = app.speakerMuted;
  el.agentAudio.replaceChildren(element);
  if (app.meters.agent) app.meters.agent.close();
  app.meters.agent = new Meter(track.mediaStreamTrack);
  clientLog("agent_audio", "Agent audio subscribed" + (participant ? " · " + participant.identity : ""), { cat: "agent", icon: "volume" });
  room.startAudio()
    .then(() => element.play())
    .then(() => setAudioBlocked(false))
    .catch((error) => {
      setAudioBlocked(true);
      hint("Sound is blocked: " + errorText(error) + ". Press the speaker button.", true);
    });
}

function attachPreview(room, LK) {
  const camera = room.localParticipant.getTrackPublication(LK.Track.Source.Camera);
  if (camera && camera.track) {
    camera.track.attach(el.preview);
    el.videoFrame.classList.add("has-video");
  }
}

function setAudioBlocked(blocked) {
  app.audioBlocked = blocked;
  el.speaker.classList.toggle("attention", blocked);
  el.speaker.title = blocked ? "Allow agent audio" : app.speakerMuted ? "Unmute agent audio" : "Mute agent audio";
}

async function onTranscription(room, session, reader, participant) {
  if (session !== app.session) return;
  const info = reader.info || {};
  const attributes = info.attributes || {};
  const local = room.localParticipant && participant && participant.identity === room.localParticipant.identity;
  const role = local ? "user" : "agent";
  const id = "s-" + (attributes["lk.segment_id"] || info.id);
  const time = info.timestamp ? info.timestamp / 1000 : nowSeconds();
  useStreamTranscript();
  let text = "";
  try {
    for await (const chunk of reader) {
      if (session !== app.session) return;
      text += decodeChunk(chunk);
      transcript.upsert(id, role, text, { final: false, time });
    }
  } catch (error) {
    if (session === app.session) clientLog("transcription", "A transcription stream ended early: " + errorText(error), { cat: "error", icon: "alert" });
  }
  if (session !== app.session) return;
  const closing = (reader.info && reader.info.attributes) || attributes;
  transcript.upsert(id, role, text, { final: role === "agent" || closing["lk.transcription_final"] === "true", time });
}

function decodeChunk(chunk) {
  if (typeof chunk !== "string") return "";
  if (chunk.startsWith("{")) {
    let out = "";
    for (const part of chunk.split("\n")) {
      if (!part) continue;
      try {
        const value = JSON.parse(part);
        if (typeof value.text !== "string") return chunk;
        out += value.text;
      } catch (error) {
        return chunk;
      }
    }
    return out;
  }
  return chunk;
}

function useStreamTranscript() {
  if (app.txSource === "stream") return;
  if (app.txSource === null) clientLog("transcript_source", "Live transcription from LiveKit text streams", { icon: "message" });
  app.txSource = "stream";
  app.txBuffer = [];
  clearTimeout(app.txTimer);
  app.txTimer = 0;
  transcript.removeDots();
  setTranscriptBadge("live", true);
}

function openTrace(roomName, session) {
  closeTrace();
  const source = new EventSource("/events?room=" + encodeURIComponent(roomName));
  app.events = source;
  let warned = false;
  source.addEventListener("hello", (message) => {
    if (session !== app.session) return;
    let info = {};
    try { info = JSON.parse(message.data); } catch (error) { return; }
    if (info.resumed) return;
    clientLog("trace", info.exists ? "Reading worker trace " + info.trace : "Waiting for worker trace " + info.trace, { icon: "file", data: info });
  });
  source.onmessage = (message) => {
    if (session !== app.session) return;
    let record;
    try { record = JSON.parse(message.data); } catch (error) { return; }
    onTraceRecord(record, "worker");
  };
  source.onerror = () => {
    if (session !== app.session || warned || source.readyState !== EventSource.CONNECTING) return;
    warned = true;
    clientLog("trace_retry", "Trace stream interrupted; it resumes from the last event it delivered", { cat: "error", icon: "alert" });
  };
}

function closeTrace() {
  if (app.events) { app.events.close(); app.events = null; }
}

async function teardown() {
  closeTrace();
  clearTimeout(app.txTimer);
  clearTimeout(app.traceWatch);
  for (const name of ["mic", "agent"]) {
    if (app.meters[name]) { app.meters[name].close(); app.meters[name] = null; }
  }
  el.agentAudio.replaceChildren();
  el.preview.srcObject = null;
  el.videoFrame.classList.remove("has-video");
  setAudioBlocked(false);
  const room = app.room;
  app.room = null;
  app.agentPresent = false;
  app.agentState = null;
  app.userSpeaking = false;
  app.quiet.active = false;
  transcript.removeDots();
  if (room) {
    try { await room.disconnect(); } catch (error) { /* already closed */ }
  }
}

async function endCall(message) {
  app.session += 1;
  await teardown();
  clientLog("left", message, { icon: "logout" });
  app.endText = "Call ended";
  setPhase("ended");
  hint(message);
}

async function toggleMic() {
  const room = app.room;
  if (!room || app.phase !== "live") return;
  const muted = !app.micMuted;
  try {
    await room.localParticipant.setMicrophoneEnabled(!muted);
    app.micMuted = muted;
    el.mic.setAttribute("aria-pressed", String(muted));
    el.mic.title = muted ? "Unmute microphone" : "Mute microphone";
    clientLog(muted ? "mic_muted" : "mic_unmuted", muted ? "Microphone muted" : "Microphone unmuted", { icon: muted ? "mic-off" : "mic" });
  } catch (error) {
    hint("Could not change the microphone: " + errorText(error), true);
  }
}

async function toggleCamera() {
  const room = app.room;
  if (!room || app.phase !== "live" || app.mode !== "camera") return;
  const off = !app.camOff;
  try {
    await room.localParticipant.setCameraEnabled(!off);
    app.camOff = off;
    el.cam.setAttribute("aria-pressed", String(off));
    el.cam.title = off ? "Turn camera on" : "Turn camera off";
    if (off) el.videoFrame.classList.remove("has-video");
    else attachPreview(room, await loadLiveKit());
    clientLog(off ? "camera_off" : "camera_on", off ? "Camera off; no frame reaches the next turn" : "Camera on", { icon: off ? "video-off" : "video" });
  } catch (error) {
    hint("Could not change the camera: " + errorText(error), true);
  }
}

function toggleSpeaker() {
  if (app.audioBlocked && app.room) {
    app.room.startAudio().then(() => {
      setAudioBlocked(false);
      const audio = el.agentAudio.querySelector("audio");
      if (audio) audio.play().catch(() => {});
      hint("Agent audio is on.");
    }).catch((error) => hint("Sound is still blocked: " + errorText(error), true));
    return;
  }
  app.speakerMuted = !app.speakerMuted;
  el.speaker.setAttribute("aria-pressed", String(app.speakerMuted));
  el.speaker.title = app.speakerMuted ? "Unmute agent audio" : "Mute agent audio";
  for (const audio of el.agentAudio.querySelectorAll("audio")) audio.muted = app.speakerMuted;
}

async function setMode(next, { keepSession = false } = {}) {
  if (!keepSession) {
    if (app.phase === "live" || app.phase === "connecting") await endCall("Switched mode, so the room was closed.");
    if (app.phase === "replay") stopReplay(true);
  }
  app.mode = next;
  el.body.dataset.mode = next;
  el.prompt.textContent = PROMPTS[next];
  el.modeVoice.setAttribute("aria-selected", String(next === "voice"));
  el.modeCamera.setAttribute("aria-selected", String(next === "camera"));
  orb.radius = next === "camera" ? 0.6 : 0.56;
  el.start.setAttribute("aria-label", "Start a " + next + " session");
  if (!keepSession) hint(modeHint(next));
}

// ---------- recorded replay ----------

async function toggleReplay() {
  if (app.phase === "replay") { stopReplay(true); return; }
  if (app.phase === "live" || app.phase === "connecting") await endCall("Left the room to play the recorded run.");
  let data;
  try {
    const response = await fetch("/replay", { cache: "no-store" });
    if (!response.ok) throw new Error((await response.text()) || String(response.status));
    data = await response.json();
  } catch (error) {
    toast("The recorded trace could not be loaded: " + errorText(error));
    return;
  }
  startReplay(data);
}

function startReplay(data) {
  const records = (data.records || []).filter((record) => typeof record.time === "number").sort((a, b) => a.time - b.time);
  if (!records.length) { toast("The recorded trace has no events for this room"); return; }
  const session = ++app.session;
  if (app.mode !== "voice") setMode("voice", { keepSession: true });
  resetSession();
  app.txSource = "trace";
  const first = records[0].time;
  logs.setBase(first);
  transcript.setBase(first);
  const speed = clamp(Number(params.get("speed")) || 1, 0.25, 40);
  let at = 0;
  let previous = first;
  const steps = records.map((record) => {
    const gap = record.time - previous;
    previous = record.time;
    at += Math.min(gap, REPLAY_GAP_LIMIT);
    return { at, record, shortened: gap > REPLAY_GAP_LIMIT ? gap : 0 };
  });
  const replay = { session, timers: [], data, lastTime: first, lastAt: performance.now(), speed };
  app.replay = replay;
  setPhase("replay");
  setTranscriptBadge("replay", true, "replay");
  clientLog("replay_started", "Replaying " + (data.scenario || "the scored recording") + " · room " + data.room + " · " + records.length + " recorded events", {
    src: "replay", icon: "rotate", t: first,
    data: { source: data.source, room: data.room, scenario: data.scenario, events: records.length, idle_gap_limit_seconds: REPLAY_GAP_LIMIT, speed },
  });
  hint("Playing the recorded 4 October 2026 trace with its original timestamps. No model runs during the replay.");
  for (const step of steps) {
    replay.timers.push(setTimeout(() => {
      if (app.replay !== replay) return;
      replay.lastTime = step.record.time;
      replay.lastAt = performance.now();
      if (step.shortened) {
        clientLog("gap", "Idle gap of " + step.shortened.toFixed(1) + " s shortened to " + REPLAY_GAP_LIMIT + " s", { src: "replay", icon: "hourglass", t: step.record.time - step.shortened });
      }
      onTraceRecord(step.record, "replay");
    }, (step.at * 1000) / speed));
  }
  replay.timers.push(setTimeout(() => finishReplay(replay), (at * 1000) / speed + 700));
}

function describeResult(result) {
  if (result.passed) return "Tool selection and arguments matched.";
  const parts = [];
  const checks = result.checks || {};
  if (checks.tool_selection) parts.push(checks.tool_selection.passed ? "tool selection matched" : "tool selection did not match");
  for (const detail of (checks.argument_accuracy && checks.argument_accuracy.details) || []) {
    if (!detail.passed && detail.explanation) parts.push(detail.explanation);
  }
  return parts.join("; ") || result.failure_reason || "not passed";
}

function finishReplay(replay) {
  if (app.replay !== replay) return;
  const result = replay.data.result;
  if (result) {
    const passed = Boolean(result.passed);
    const detail = describeResult(result);
    transcript.chip("result", passed ? "result-pass" : "result-fail", passed ? "Strict check passed" : "Strict check not passed", detail, {
      icon: passed ? "check-circle" : "x-circle", time: replay.lastTime, details: result.checks,
    });
    logs.add({
      t: replay.lastTime, kind: "result", cat: "result", icon: passed ? "check-circle" : "x-circle",
      label: passed ? "passed" : "not passed", msg: result.scenario_id + " · " + (result.title || "") + " · " + detail,
      src: "replay", interim: false, data: result, pass: passed,
    });
  }
  app.replay = null;
  app.endText = "Replay finished";
  app.agentState = null;
  app.userSpeaking = false;
  setPhase("ended");
  setTranscriptBadge("replay", false, "replay");
  hint("Replay finished. The official result for this recording is at the end of the transcript and the logs.");
}

function stopReplay(announce) {
  const replay = app.replay;
  if (!replay) return;
  for (const timer of replay.timers) clearTimeout(timer);
  app.replay = null;
  app.session += 1;
  app.agentState = null;
  app.userSpeaking = false;
  app.quiet.active = false;
  transcript.removeDots();
  if (announce) {
    clientLog("replay_stopped", "Replay stopped", { src: "replay", icon: "stop" });
    app.endText = "Replay stopped";
    setPhase("ended");
    setTranscriptBadge("replay", false, "replay");
  }
}

// ---------- config and page wiring ----------

const MODEL_NAMES = {
  "deepgram/nova-3": "Deepgram Nova-3",
  "openai/gpt-4.1-mini": "GPT-4.1 mini",
  "cartesia/sonic-3": "Cartesia Sonic-3",
  "assemblyai/universal-3-5-pro": "AssemblyAI Universal-3.5",
  "deepgram/aura-2:athena": "Deepgram Aura-2",
};

function modelName(id) {
  return MODEL_NAMES[id] || id || "unknown";
}

function renderModels() {
  const models = cfg.models;
  if (!models) return;
  const llm = models.llm_provider === "ollama" ? "Ollama " + models.ollama_model : modelName(models.llm);
  const items = [
    ["stt", modelName(models.stt)],
    ["llm", llm + " · temperature " + fmtNumber(cfg.temperature)],
    ["tts", modelName(models.tts)],
    ["gate", "Quiet window " + fmtNumber(cfg.commit_quiet_seconds) + " s"],
  ];
  el.models.replaceChildren(...items.map(([key, value]) => {
    const item = h("span");
    item.append(h("i", null, key), value);
    return item;
  }));
}

async function loadConfig() {
  try {
    const response = await fetch("/config", { cache: "no-store" });
    if (!response.ok) return;
    Object.assign(cfg, await response.json());
    renderModels();
    setConn(el.conn.dataset.state || "idle");
    if (!cfg.livekit_configured) {
      hint("LiveKit is not configured here. Set LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET in .env, then restart this page. The recorded replay still works.", true);
    }
  } catch (error) {
    /* the static defaults stay */
  }
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  orb.light = theme === "light" ? 1 : 0;
  try { localStorage.setItem("interra-theme", theme); } catch (error) { /* private window */ }
  readPalette();
}

const logs = new LogView();
const transcript = new TranscriptView();

el.start.addEventListener("click", () => startCall());
el.mic.addEventListener("click", () => toggleMic());
el.cam.addEventListener("click", () => toggleCamera());
el.speaker.addEventListener("click", () => toggleSpeaker());
el.replay.addEventListener("click", () => toggleReplay());
el.replay2.addEventListener("click", () => {
  window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
  toggleReplay();
});
el.modeVoice.addEventListener("click", () => { if (app.mode !== "voice") setMode("voice"); });
el.modeCamera.addEventListener("click", () => { if (app.mode !== "camera") setMode("camera"); });
el.theme.addEventListener("click", () => applyTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light"));

for (const tab of document.querySelectorAll(".mobile-tabs button")) {
  tab.addEventListener("click", () => {
    const name = tab.id.replace("tab-", "");
    el.body.dataset.tab = name;
    for (const other of document.querySelectorAll(".mobile-tabs button")) other.setAttribute("aria-selected", String(other === tab));
  });
}

for (const button of document.querySelectorAll(".cmd-tabs button")) {
  button.addEventListener("click", () => {
    for (const other of document.querySelectorAll(".cmd-tabs button")) other.setAttribute("aria-selected", String(other === button));
    for (const block of document.querySelectorAll(".cmd")) block.hidden = block.dataset.shell !== button.dataset.shell;
  });
}

for (const button of document.querySelectorAll("[data-copy]")) {
  button.addEventListener("click", () => copyText(button.parentElement.querySelector("pre").textContent.trim() + "\n", "Commands copied"));
}

document.addEventListener("keydown", (event) => {
  const typing = event.target instanceof HTMLElement && (event.target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName));
  if (event.key === "/" && !typing) { event.preventDefault(); el.search.focus(); }
});

window.addEventListener("beforeunload", () => {
  if (app.room) app.room.disconnect();
  closeTrace();
});

window.matchMedia && matchMedia("(prefers-color-scheme: light)").addEventListener("change", (event) => {
  let saved = null;
  try { saved = localStorage.getItem("interra-theme"); } catch (error) { /* private window */ }
  if (!saved) applyTheme(event.matches ? "light" : "dark");
});

orb.light = document.documentElement.dataset.theme === "light" ? 1 : 0;
readPalette();
const startMode = params.get("mode") === "camera" ? "camera" : "voice";
setMode(startMode, { keepSession: true });
hint(params.get("mode") ? modeHint(startMode) : "Choose a mode, then start. Use headphones so the agent does not hear itself.");
setPhase("idle");
setNow("Waiting", "Nothing has been decided yet.");
logs.updateCounts();
transcript.changed();
loadConfig().then(() => { if (params.get("replay") === "1") toggleReplay(); });
requestAnimationFrame(frame);
