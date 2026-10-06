/* Interra live console: joins a LiveKit room and renders what the agent does. */
(() => {
  "use strict";
  const LK = window.LivekitClient;
  const $ = (id) => document.getElementById(id);
  const TOPIC = "interra.events";

  const state = {
    mode: "benchmark",
    config: null,
    room: null,
    roomName: "",
    segments: new Map(),      // segment id -> bubble element
    toolCards: new Map(),     // call id -> event element
    tickets: new Map(),
    metrics: { tools: 0, interruptions: 0, held: 0, stale: 0, dupes: 0, frames: 0 },
    userStoppedAt: null,
    agentState: "",
    meterTimer: null,
    pollTimer: null,
    started: performance.now(),
  };

  /* ---------- small DOM helpers (text only, never HTML from the room) ---------- */
  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (value === undefined || value === null || value === false) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else node.setAttribute(key, value);
    }
    for (const child of children) if (child !== null && child !== undefined) node.append(child);
    return node;
  }
  const json = (value) => JSON.stringify(value, null, 1);
  const clock = () => {
    const s = (performance.now() - state.started) / 1000;
    return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
  };
  function clearEmpty(container) {
    const empty = container.querySelector(".empty-state");
    if (empty) empty.remove();
  }
  function setMetric(name, value) {
    state.metrics[name] = value;
    $(`m-${name}`).textContent = String(value);
  }
  const bump = (name) => setMetric(name, state.metrics[name] + 1);

  /* ---------- timeline ---------- */
  function addEvent(tone, title, body, extra) {
    const timeline = $("timeline");
    clearEmpty(timeline);
    const node = el("div", { class: `event ${tone}` },
      el("div", { class: "head" }, el("span", { class: "title", text: title }), el("span", { class: "time", text: clock() })));
    if (body) node.append(el("div", { class: "body", text: body }));
    if (extra) node.append(extra);
    timeline.prepend(node);
    return node;
  }
  const pre = (value) => el("pre", { text: typeof value === "string" ? value : json(value) });
  const ms = (value) => (value === undefined || value === null ? "" : `${value} ms`);
  const callText = (fn, args) => `${fn}(${Object.entries(args || {}).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")})`;

  /* ---------- transcript ---------- */
  function speakerOf(identity) {
    if (identity && identity.startsWith("agent")) return "agent";
    if (!state.room) return "user";
    if (identity === state.room.localParticipant.identity) return "user";
    const participant = state.room.remoteParticipants.get(identity);
    if (participant && (participant.isAgent || participant.kind === LK.ParticipantKind?.AGENT)) return "agent";
    return "user";
  }
  function upsertSegment(id, identity, text, final) {
    const transcript = $("transcript");
    clearEmpty(transcript);
    const who = speakerOf(identity);
    let bubble = state.segments.get(id);
    if (!bubble) {
      bubble = el("div", { class: `bubble ${who}` },
        el("div", { class: "who" }, el("span", { text: who === "agent" ? "Agent" : (state.mode === "benchmark" ? "Recorded person" : "You") }), el("span", { text: clock() })),
        el("div", { class: "text" }));
      state.segments.set(id, bubble);
      transcript.append(bubble);
    }
    bubble.querySelector(".text").textContent = text;
    bubble.classList.toggle("interim", !final);
    transcript.scrollTop = transcript.scrollHeight;
    return bubble;
  }
  function markLastAgentInterrupted() {
    const bubbles = [...document.querySelectorAll(".bubble.agent")];
    const last = bubbles[bubbles.length - 1];
    if (last && !last.classList.contains("interrupted")) {
      last.classList.add("interrupted");
      last.querySelector(".who").append(el("span", { class: "tag", text: "interrupted" }));
    }
  }

  /* ---------- states and latency ---------- */
  function setAgentState(value) {
    if (!value || value === state.agentState) return;
    if (value === "speaking" && state.userStoppedAt !== null) {
      const latency = (performance.now() - state.userStoppedAt) / 1000;
      if (latency > 0 && latency < 30) $("m-latency").textContent = `${latency.toFixed(2)} s`;
      state.userStoppedAt = null;
    }
    state.agentState = value;
    document.querySelectorAll("[data-agent-state]").forEach((node) =>
      node.classList.toggle("active", node.dataset.agentState === value));
  }
  function setUserState(value) {
    const node = document.querySelector("[data-user-state]");
    node.textContent = `person: ${value}`;
    node.classList.toggle("user-active", value === "speaking");
    if (value === "listening" || value === "away") state.userStoppedAt = performance.now();
  }

  /* ---------- agent events ---------- */
  function renderTicket(ticket) {
    state.tickets.set(ticket.ticket_id, ticket);
    $("tickets").hidden = false;
    const list = $("ticket-list");
    list.replaceChildren(...[...state.tickets.values()].map((t) =>
      el("div", { class: `ticket ${t.status}` },
        el("code", { text: t.ticket_id }), el("span", { text: `${t.device} · ${t.problem}` }),
        el("span", { class: "status", text: t.status }))));
  }

  function ingest(event) {
    const kind = event.kind;
    switch (kind) {
      case "session_started": {
        const models = [event.stt, event.llm, event.tts].filter(Boolean).join(" · ");
        addEvent("agent", event.agent === "camera" ? "Camera troubleshooter joined" : "Benchmark agent joined", models);
        break;
      }
      case "agent_state": setAgentState(event.state); break;
      case "user_state": setUserState(event.state); break;
      case "transcript":
        if (state.segments.size === 0 && event.is_final && event.transcript) {
          upsertSegment(`event-${Date.now()}`, "user-event", event.transcript, true);
        }
        break;
      case "conversation_item":
        if (event.role === "assistant" && event.interrupted) markLastAgentInterrupted();
        break;
      case "interruption":
        bump("interruptions");
        addEvent("warn", "Person interrupted", `The agent was ${event.agent_state}; it stops and listens.`);
        markLastAgentInterrupted();
        break;
      case "request_superseded":
        $("request-version").hidden = false;
        $("request-version").textContent = `request v${event.request_version}`;
        addEvent("warn", `Correction: request is now v${event.request_version}`, `“${event.transcript}”`);
        break;
      case "turn_held":
        bump("held");
        addEvent("user", "Turn held: sentence not finished", `“${event.transcript}” — waiting for the rest before answering.`);
        break;
      case "turn_released":
        addEvent("user", "Held turn released", event.reason ? `Reason: ${event.reason}` : "");
        break;
      case "tool_call": {   // benchmark agent: completed official mock tool call
        bump("tools");
        const call = event.call || {};
        const took = call.timestamp_end && call.timestamp_start ? Math.round((call.timestamp_end - call.timestamp_start) * 1000) : null;
        addEvent(event.status === "completed" ? "tool" : "bad", `Tool: ${call.function}`, took !== null ? `completed in ${took} ms` : event.status,
          el("div", {}, pre(callText(call.function, call.args)), event.result ? pre(event.result) : null));
        break;
      }
      case "tool_call_deduplicated":
        bump("dupes");
        addEvent("warn", "Duplicate call returned from cache", "Same tool and arguments in this room; the side effect is not repeated.",
          pre(callText(event.call?.function, event.call?.args)));
        break;
      case "tool_started": {
        bump("tools");
        const mode = event.read_only ? "running · read-only" : "running · writes state";
        const simulated = event.simulated_latency_s ? ` · local guide library, simulated ${event.simulated_latency_s}s lookup` : "";
        const card = addEvent("tool", `Tool: ${event.function}`, mode + simulated,
          el("div", {}, pre(callText(event.function, event.args))));
        card.querySelector(".head").prepend(el("span", { class: "spinner" }));
        if (event.request_version !== undefined) {
          card.querySelector(".body").textContent += ` · for request v${event.request_version}`;
        }
        state.toolCards.set(event.call_id, card);
        break;
      }
      case "tool_finished": {
        const card = state.toolCards.get(event.call_id);
        if (card) {
          card.querySelector(".spinner")?.remove();
          card.classList.replace("tool", "ok");
          card.querySelector(".body").textContent = `${event.status} in ${ms(event.elapsed_ms)}`;
          if (event.result) card.append(pre(event.result));
        }
        break;
      }
      case "tool_cancelled": {
        bump("stale");
        const card = state.toolCards.get(event.call_id);
        if (card) { card.querySelector(".spinner")?.remove(); card.classList.replace("tool", "bad"); card.querySelector(".body").textContent = `cancelled after ${ms(event.elapsed_ms)}`; }
        addEvent("bad", "Lookup cancelled", `${event.reason}; its answer will never be spoken.`);
        break;
      }
      case "stale_result_discarded": {
        bump("stale");
        const card = state.toolCards.get(event.call_id);
        if (card) { card.querySelector(".spinner")?.remove(); card.classList.replace("tool", "bad"); card.querySelector(".body").textContent = "result discarded as stale"; }
        addEvent("bad", "Stale result discarded",
          `Issued for request v${event.request_version}, but the person is now on v${event.current_version}.`,
          pre(event.result));
        break;
      }
      case "ticket_opened":
        renderTicket(event.ticket);
        addEvent("ok", `Ticket ${event.ticket.ticket_id} opened`, `${event.ticket.device} · ${event.ticket.problem}`);
        break;
      case "ticket_cancelled":
        renderTicket(event.ticket);
        addEvent("warn", `Ticket ${event.ticket.ticket_id} cancelled`, event.ticket.cancel_reason || "");
        break;
      case "duplicate_write_suppressed":
        bump("dupes");
        renderTicket(event.ticket);
        addEvent("warn", "Duplicate write blocked", `${event.function} repeated; ticket ${event.ticket.ticket_id} was not changed twice.`);
        break;
      case "write_skipped":
        addEvent("warn", "Write skipped", `${event.function}: ${event.reason}`);
        break;
      case "frame_attached": {
        setMetric("frames", state.metrics.frames + 1);
        const img = event.thumbnail ? el("img", { src: `data:image/jpeg;base64,${event.thumbnail}`, alt: "Frame sent to the model" }) : null;
        addEvent("user", `Camera frame sent with request v${event.request_version}`,
          `${event.width}×${event.height}, ${event.age_ms} ms old · ${event.frames_replaced} older frames replaced · ${event.old_images_removed} old image(s) removed from memory`, img);
        $("video-overlay").hidden = false;
        $("video-overlay").textContent = `frames seen by agent: ${event.frames_seen}`;
        break;
      }
      case "no_frame": addEvent("warn", "No camera frame", "The agent asks for the camera or a clearer view."); break;
      case "camera_linked": addEvent("ok", "Camera linked", "Only this participant's camera is used."); break;
      case "camera_unlinked": addEvent("warn", "Camera unlinked", "Pending frame discarded."); break;
      case "session_error": addEvent("bad", "Session error", event.error || ""); break;
      case "session_closed": case "session_cleanup": addEvent("agent", "Session closed", ""); break;
      default: break;
    }
  }

  /* ---------- room ---------- */
  function setConnection(text, tone) {
    const node = $("connection");
    node.textContent = text;
    node.className = `pill ${tone || ""}`;
  }

  function startMeters() {
    clearInterval(state.meterTimer);
    state.meterTimer = setInterval(() => {
      if (!state.room) return;
      let user = 0, agent = 0;
      const all = [state.room.localParticipant, ...state.room.remoteParticipants.values()];
      for (const p of all) {
        const level = p.audioLevel || 0;
        if (speakerOf(p.identity) === "agent") agent = Math.max(agent, level);
        else if (state.mode === "camera" ? p === state.room.localParticipant : p !== state.room.localParticipant) user = Math.max(user, level);
      }
      $("meter-user").style.width = `${Math.min(100, user * 140)}%`;
      $("meter-agent").style.width = `${Math.min(100, agent * 140)}%`;
    }, 100);
  }

  async function connect(session) {
    const room = new LK.Room({ adaptiveStream: true, dynacast: true });
    state.room = room;
    state.roomName = session.room;
    room.on(LK.RoomEvent.TrackSubscribed, (track) => {
      if (track.kind === "audio") document.body.append(Object.assign(track.attach(), { hidden: true }));
    });
    room.on(LK.RoomEvent.DataReceived, (payload, _participant, _kind, topic) => {
      if (topic !== TOPIC) return;
      try { ingest(JSON.parse(new TextDecoder().decode(payload))); } catch (error) { console.warn(error); }
    });
    room.on(LK.RoomEvent.ParticipantAttributesChanged, (changed) => {
      if (changed["lk.agent.state"]) setAgentState(changed["lk.agent.state"]);
    });
    room.on(LK.RoomEvent.ParticipantConnected, (p) => {
      if (speakerOf(p.identity) === "agent" || p.identity.startsWith("agent")) setConnection("Agent in room", "ok");
    });
    room.on(LK.RoomEvent.Disconnected, () => setConnection("Disconnected", "bad"));
    room.registerTextStreamHandler("lk.transcription", async (reader, participantInfo) => {
      const attrs = reader.info.attributes || {};
      const id = attrs["lk.segment_id"] || reader.info.id;
      const final = attrs["lk.transcription_final"] === "true";
      let text = "";
      for await (const chunk of reader) {
        text += chunk;
        upsertSegment(id, participantInfo.identity, text, final);
      }
      upsertSegment(id, participantInfo.identity, text, final);
    });
    setConnection("Connecting…", "warn");
    await room.connect(session.url, session.token);
    setConnection("Connected", "ok");
    $("room-name").hidden = false;
    $("room-name").textContent = session.room;
    $("leave").disabled = false;
    startMeters();
    return room;
  }

  async function leave() {
    clearInterval(state.pollTimer);
    clearInterval(state.meterTimer);
    if (state.room) await state.room.disconnect();
    state.room = null;
    $("leave").disabled = true;
    $("bench-start").disabled = false;
    $("cam-start").disabled = false;
    setConnection("Not connected");
  }

  async function api(path, body) {
    const response = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || response.statusText);
    return data;
  }

  /* ---------- benchmark mode ---------- */
  function renderRecordingMeta() {
    const name = $("recording").value;
    const row = (state.config?.recordings || []).find((r) => r.name === name);
    const meta = $("recording-meta");
    meta.replaceChildren();
    if (!row) return;
    const chips = el("div", { class: "chips" },
      el("span", { class: "chip", text: row.domain || "domain ?" }),
      el("span", { class: "chip", text: `difficulty: ${row.difficulty || "?"}` }),
      row.seconds ? el("span", { class: "chip", text: `${row.seconds.toFixed(1)} s` }) : null,
      row.rollback ? el("span", { class: "chip hot", text: "state rollback" }) : null,
      ...row.features.map((f) => el("span", { class: `chip ${f === "SELF_CORRECTION" ? "hot" : ""}`, text: f.toLowerCase().replace("_", " ") })));
    meta.append(el("div", { class: "hint", text: row.title }), chips);
  }

  async function startBenchmark() {
    const recording = $("recording").value;
    if (!recording) return;
    $("bench-start").disabled = true;
    try {
      const session = await api("/api/session", { mode: "benchmark" });
      await connect(session);
      addEvent("user", "Playing released recording", recording);
      const play = await api("/api/benchmark/play", { room: session.room, recording });
      const startedAt = performance.now();
      const seconds = play.seconds || 30;
      $("bench-status").textContent = "Official recorder is streaming the recording…";
      state.pollTimer = setInterval(async () => {
        const elapsed = (performance.now() - startedAt) / 1000;
        $("bench-progress").style.width = `${Math.min(100, (elapsed / seconds) * 100)}%`;
        const status = await api(`/api/benchmark/status?room=${encodeURIComponent(session.room)}`);
        if (status.state !== "playing") {
          clearInterval(state.pollTimer);
          $("bench-progress").style.width = "100%";
          $("bench-status").textContent = status.state === "done"
            ? `Recording finished. ${status.tool_calls.length} tool call(s) in the trace for this room.`
            : `Recorder exited with ${status.returncode}: ${status.log_tail.slice(-1)[0] || ""}`;
          if (status.tool_calls.length) {
            addEvent("ok", "Trace: tool calls for this room", "From artifacts/fdb_v3/livekit-agent.jsonl, as the benchmark scores them.",
              pre(status.tool_calls.map((c) => callText(c.function, c.args)).join("\n")));
          }
        }
      }, 1000);
    } catch (error) {
      setConnection(error.message, "bad");
      $("bench-start").disabled = false;
    }
  }

  /* ---------- camera mode ---------- */
  async function startCamera() {
    $("cam-start").disabled = true;
    try {
      const session = await api("/api/session", { mode: "camera" });
      const room = await connect(session);
      await room.localParticipant.enableCameraAndMicrophone();
      const publication = [...room.localParticipant.videoTrackPublications.values()][0];
      if (publication?.track) {
        publication.track.attach($("local-video"));
        $("video-empty").hidden = true;
      }
      setConnection("Waiting for the troubleshooter…", "warn");
    } catch (error) {
      setConnection(error.message, "bad");
      $("cam-start").disabled = false;
    }
  }

  /* ---------- setup ---------- */
  function selectMode(mode) {
    state.mode = mode;
    document.querySelectorAll(".tab").forEach((tab) => tab.setAttribute("aria-selected", String(tab.dataset.mode === mode)));
    $("stage-benchmark").hidden = mode !== "benchmark";
    $("stage-camera").hidden = mode !== "camera";
    $("user-label").textContent = mode === "camera" ? "You" : "Recording";
  }

  async function init() {
    document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => selectMode(tab.dataset.mode)));
    $("recording").addEventListener("change", renderRecordingMeta);
    $("bench-start").addEventListener("click", startBenchmark);
    $("cam-start").addEventListener("click", startCamera);
    $("leave").addEventListener("click", leave);
    try {
      state.config = await api("/api/config");
    } catch (error) {
      setConnection("Console server unreachable", "bad");
      return;
    }
    const models = state.config.models;
    $("models").replaceChildren(...["stt", "llm", "tts"].map((key) => el("span", { class: "badge", text: `${key.toUpperCase()} ${models[key]}` })));
    if (state.config.missing_credentials.length) setConnection(`Set ${state.config.missing_credentials.join(", ")}`, "bad");
    const select = $("recording");
    const rows = state.config.recordings;
    if (!rows.length) {
      select.append(el("option", { value: "", text: "No released recordings found" }));
      $("bench-status").textContent = `Download the data: python scripts/fdb_v3.py bootstrap --download-data (${state.config.data_root})`;
      $("bench-start").disabled = true;
    }
    for (const row of rows) {
      const flag = row.features.includes("SELF_CORRECTION") || row.rollback ? "★ " : "";
      select.append(el("option", { value: row.name, text: `${flag}${row.scenario} — ${row.title || row.name}` }));
    }
    renderRecordingMeta();
    if (!LK) setConnection("livekit-client failed to load (check internet)", "bad");
  }

  window.interraConsole = { ingest, upsertSegment, setAgentState, setUserState, selectMode };
  init();
})();
