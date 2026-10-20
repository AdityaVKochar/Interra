// The recorded run, played from its own trace with the original timestamps.
// Idle gaps longer than GAP seconds are shortened, and the page says so.
// No model runs here; the verdict shown is the pinned evaluator's.

import { $, clamp, fmtShort, h, svgIcon, toast } from "./shell.js";
import { Conversation } from "./conversation.js";
import { describeResult, fmtValue } from "./trace.js";

const GAP = 2.5;
const el = {
  play: $("play"), playLabel: $("play-label"), restart: $("restart"),
  time: $("play-time"), scrub: $("scrub"), fill: $("scrub-fill"),
  speeds: document.querySelectorAll(".speed button"),
  result: $("result"), meta: $("replay-meta"),
};

const player = {
  steps: [],
  total: 0,
  cursor: 0,
  position: 0,
  anchor: 0,
  anchorAt: 0,
  speed: 1,
  playing: false,
  finished: false,
  data: null,
  lastStep: null,
};

const convo = new Conversation({ mode: "voice", clock: () => replayClock() });
convo.agentLabel = "the recording";
// The 4 October run predates the commit gate (added 17 October): its call was never held.
convo.waitingOverride = "This run predates the commit gate, so its tool call ran as soon as the model planned it. The steps still show where the turn was.";
$("gate-window").parentElement.textContent = "Recorded before the gate";
convo.setGate("Waiting");

function replayClock() {
  const step = player.lastStep;
  if (!step) return player.steps.length ? player.steps[0].record.time : Date.now() / 1000;
  return step.record.time + Math.max(0, player.position - step.at);
}

const MARKS = {
  user_state: (r) => (r.state === "speaking" ? ["var(--warm)", "You start speaking"] : null),
  turn_held: () => ["var(--held)", "Turn held"],
  tool_call_pending: () => ["var(--holding)", "Call held at the gate"],
  tool_call: () => ["var(--executed)", "Tool call executed"],
  tool_call_dropped: () => ["var(--dropped)", "Tool call dropped"],
  conversation_item: (r) => (r.role === "assistant" ? ["var(--cool)", "Agent reply"] : null),
  participant_disconnected: () => ["var(--session)", "Participant left"],
};

function build(data) {
  const records = (data.records || []).filter((record) => typeof record.time === "number").sort((a, b) => a.time - b.time);
  let at = 0;
  let previous = records.length ? records[0].time : 0;
  player.steps = records.map((record) => {
    const gap = record.time - previous;
    previous = record.time;
    at += Math.min(gap, GAP);
    return { at, record, shortened: gap > GAP ? gap : 0 };
  });
  player.total = at;
  player.data = data;
  for (const old of el.scrub.querySelectorAll(".mark")) old.remove();
  for (const step of player.steps) {
    const mark = MARKS[step.record.kind] && MARKS[step.record.kind](step.record);
    if (!mark) continue;
    const node = h("span", "mark");
    node.style.left = (player.total ? (step.at / player.total) * 100 : 0) + "%";
    node.style.setProperty("--c", mark[0]);
    node.title = mark[1] + " · " + fmtShort(step.at);
    node.dataset.at = String(step.at);
    el.scrub.append(node);
  }
  const shortened = player.steps.filter((step) => step.shortened).length;
  el.meta.textContent = data.scenario + " · room " + data.room + " · " + records.length + " recorded events"
    + (shortened ? " · " + shortened + " idle gaps over " + GAP + " s shortened" : "");
  renderResult(data.result, data.report);
}

function resetView() {
  convo.reset(player.steps.length ? player.steps[0].record.time : null);
  convo.txSource = "trace"; // a recording has no LiveKit captions; its trace is the transcript
  player.cursor = 0;
  player.lastStep = null;
  player.finished = false;
}

function apply(step) {
  player.lastStep = step;
  convo.onRecord(step.record, "replay");
}

function catchUp() {
  while (player.cursor < player.steps.length && player.steps[player.cursor].at <= player.position) {
    apply(player.steps[player.cursor]);
    player.cursor += 1;
  }
}

function render() {
  const total = player.total || 1;
  el.fill.style.width = clamp(player.position / total) * 100 + "%";
  el.time.textContent = fmtShort(player.position) + " / " + fmtShort(player.total);
  for (const mark of el.scrub.querySelectorAll(".mark")) mark.classList.toggle("passed", Number(mark.dataset.at) <= player.position);
}

function setPlaying(playing) {
  player.playing = playing;
  el.play.dataset.state = playing ? "live" : "idle";
  el.play.querySelector("use").setAttribute("href", playing ? "#i-pause" : "#i-play");
  el.playLabel.textContent = playing ? "Pause" : player.finished ? "Play again" : player.position > 0 ? "Resume" : "Play the recording";
  convo.phase = playing || (player.position > 0 && !player.finished) ? "replay" : player.finished ? "ended" : "idle";
  convo.statusPrefix = !playing && player.position > 0 && !player.finished ? "Paused · " : "";
}

function play() {
  if (!player.steps.length) return;
  if (player.finished) { resetView(); player.position = 0; }
  player.anchor = player.position;
  player.anchorAt = performance.now();
  setPlaying(true);
}

function pause() {
  setPlaying(false);
}

function finish() {
  player.finished = true;
  const result = player.data && player.data.result;
  if (result) {
    const passed = Boolean(result.passed);
    convo.transcript.chip("result", passed ? "result-pass" : "result-fail", passed ? "Strict check passed" : "Strict check not passed", describeResult(result), {
      icon: passed ? "check-circle" : "x-circle", time: replayClock(), details: result.checks,
    });
  }
  convo.endText = "Replay finished";
  convo.agentState = null;
  convo.userSpeaking = false;
  setPlaying(false);
  convo.hint("Replay finished. The official result for this recording is below the player and at the end of the transcript.");
}

function seek(target) {
  const wasPlaying = player.playing;
  resetView();
  player.position = clamp(target, 0, player.total);
  catchUp();
  render();
  if (wasPlaying) play();
  else setPlaying(false);
}

convo.onFrame = (now) => {
  if (!player.playing) return;
  player.position = Math.min(player.total + 0.8, player.anchor + ((now - player.anchorAt) / 1000) * player.speed);
  catchUp();
  render();
  if (player.cursor >= player.steps.length && player.position >= player.total + 0.7) finish();
};

el.play.addEventListener("click", () => (player.playing ? pause() : play()));
el.restart.addEventListener("click", () => { resetView(); player.position = 0; render(); play(); });
for (const button of el.speeds) {
  button.addEventListener("click", () => {
    player.anchor = player.position;
    player.anchorAt = performance.now();
    player.speed = Number(button.dataset.speed) || 1;
    for (const other of el.speeds) other.setAttribute("aria-pressed", String(other === button));
  });
}
el.scrub.addEventListener("click", (event) => {
  const rect = el.scrub.getBoundingClientRect();
  seek(((event.clientX - rect.left) / rect.width) * player.total);
});

// ---------- the official result ----------

function mismatchedKeys(detail) {
  const keys = new Set();
  for (const match of String(detail.explanation || "").matchAll(/Mismatch '([^']+)'/g)) keys.add(match[1]);
  return keys;
}

function checkRow(ok, label, expected, actual) {
  const row = h("div", "check-row");
  row.append(svgIcon(ok ? "check-circle" : "x-circle", "ic sm " + (ok ? "ok" : "bad")), h("span", null, label));
  const expectedCell = h("span");
  expectedCell.append(expected);
  const actualCell = h("span");
  actualCell.append(actual);
  row.append(expectedCell, actualCell);
  return row;
}

function renderResult(result, report) {
  const body = $("result-body");
  if (!result) {
    body.replaceChildren(h("p", null, "The official report does not hold exactly one entry for this scenario, so no verdict is shown."));
    return;
  }
  const passed = Boolean(result.passed);
  const verdict = h("span", "verdict " + (passed ? "pass" : "fail"));
  verdict.append(svgIcon(passed ? "check-circle" : "x-circle"), passed ? "Strict check passed" : "Strict check not passed");
  $("result-verdict").replaceChildren(verdict);
  $("result-title").textContent = result.title || result.scenario_id;
  const rows = [];
  const head = h("div", "check-row head");
  head.append(h("span"), h("span", null, "Check"), h("span", null, "Expected"), h("span", null, "Recorded"));
  rows.push(head);
  const checks = result.checks || {};
  if (checks.tool_selection) {
    rows.push(checkRow(Boolean(checks.tool_selection.passed), "Tool selection",
      (checks.tool_selection.expected || []).join(", ") || "none", (checks.tool_selection.actual || []).join(", ") || "none"));
  }
  for (const detail of (checks.argument_accuracy && checks.argument_accuracy.details) || []) {
    const wrong = mismatchedKeys(detail);
    const keys = new Set([...Object.keys(detail.expected_args || {}), ...Object.keys(detail.actual_args || {})]);
    for (const key of keys) {
      const ok = detail.passed || !wrong.has(key);
      rows.push(checkRow(ok, detail.function + " · " + key.replace(/_/g, " "),
        fmtValue((detail.expected_args || {})[key]), fmtValue((detail.actual_args || {})[key])));
    }
  }
  const checksNode = h("div", "checks");
  checksNode.append(...rows);
  const note = h("p", null, (result.failure_reason ? result.failure_reason + ". " : "") + "From " + (report || "the official report") + ". This page compares nothing itself; it shows the evaluator's checks.");
  body.replaceChildren(checksNode, note);
}

async function load() {
  try {
    const response = await fetch("/api/replay", { cache: "no-store" });
    if (!response.ok) throw new Error((await response.text()) || String(response.status));
    build(await response.json());
    resetView();
    render();
    setPlaying(false);
    convo.hint("Press play. The recording's own trace drives the orb, the transcript and the gate card. No model runs during the replay.");
    const query = new URLSearchParams(location.search);
    const at = Number(query.get("t"));
    if (Number.isFinite(at) && at > 0) seek(at);
    if (query.get("autoplay") === "1") play();
  } catch (error) {
    toast("The recorded trace could not be loaded");
    convo.hint("The recorded trace could not be loaded: " + (error && error.message ? error.message : error), true);
  }
}

convo.start();
load();
