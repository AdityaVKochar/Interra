# 05 — Multimodal Processing

Official inputs include raw WAV audio and PNG video frames. Hidden multimodal scenarios receive extra weighting, so multimodality must be real, not decorative.

## Design principle

Audio and vision are **input adapters into the same event/state system**.

Do not build:

```text
text agent
audio agent
vision agent
```

as separate independent agents.

Build:

```text
text ───────┐
WAV ────────┼→ typed semantic events/observations → same runtime
PNG ────────┘
```

---

## Audio pipeline

Suggested flow:

```text
AUDIO_CLIP
    ↓
AudioUnderstandingProvider
    ↓
transcript / semantic observation
    ↓
planner/state patch
    ↓
normal interruption + scheduling logic
```

### Required behavior

- Audio processing must be asynchronous.
- New input must not block while audio is being processed.
- If an audio clip corrects a prior slot, use normal localized correction.
- If audio understanding is ambiguous, clarify.
- Preserve the original event timestamp/reference in trace logs.

### Provider output schema

Suggested:

```json
{
  "transcript": "Actually, make that Mumbai in the evening",
  "slot_hints": {
    "destination": "Mumbai",
    "time_of_day": "evening"
  },
  "ambiguous": false,
  "evidence": "user correction"
}
```

The planner may re-interpret the transcript. The audio provider should not directly dispatch tools.

---

## Visual pipeline

Suggested:

```text
VIDEO_FRAME
    ↓
VisionUnderstandingProvider
    ↓
structured visual observation
    ↓
planner/state
```

Example:

```json
{
  "summary": "A charging warning is visible on the device screen.",
  "facts": [
    {
      "name": "visible_warning",
      "value": "charging"
    }
  ],
  "ambiguous": false
}
```

### Rules

- Do not invent facts that are not visually grounded.
- Preserve frame identity/timestamp.
- If perception is ambiguous, ask a targeted clarification rather than acting confidently.
- Visual observations are session-scoped.
- A frame from an obsolete branch of a conversation should not automatically override newer user intent.

---

## Multimodal fusion

A planner turn may use:

- text,
- audio transcript,
- visual observations,
- tool results,
- current session state.

Fusion should be state-aware.

Example:

```text
User: "My phone is not charging."
Frame: charging warning visible.
User interrupts: "Wireless charging works."
```

The newest user information should refine the troubleshooting state rather than discarding all prior evidence.

---

## Timing problem

Multimodal processing may finish out of order.

Example:

```text
t=1.0 audio clip A arrives
t=1.2 image B arrives
t=1.4 user correction C arrives
t=1.5 image B processing finishes
t=1.8 audio A processing finishes
```

Do not apply semantic results based only on completion order.

Each derived observation must carry:

- source event ID,
- source timestamp,
- state/turn context at which it was requested.

The runtime must decide whether the observation is still relevant.

---

## Fast-path behavior while multimodal work runs

The guide expects processing behind conversational acknowledgment.

Safe examples:

```text
"I’m checking what’s visible."
"I heard the update — I’m adjusting the plan."
```

Avoid claiming specific visual/audio interpretation before the corresponding provider result exists.

---

## Testing requirements

### Audio

Test at minimum:

- clear command,
- clear slot correction,
- ambiguous utterance,
- audio arriving during tool call,
- audio correction invalidating an active call,
- delayed audio-processing result after a newer correction.

### Vision

Test:

- clear relevant frame,
- ambiguous frame,
- frame-grounded tool choice,
- stale visual analysis result,
- visual result that conflicts with earlier assumption.

### Combined

Test:

- audio + visual + tool result interleaving,
- interruption during multimodal processing,
- multimodal clarification,
- updated text after old frame processing has started.

---

## Provider strategy

Do not bind the runtime to one vendor.

Use adapters and configuration.

Local tests must use deterministic mock providers.

Cloud/live providers are for integration/demo, not for proving concurrency correctness.

---

## Latency strategy

Do not wait for all modalities if the task can progress safely.

Possible approach:

1. fast acknowledgment,
2. launch audio/vision understanding concurrently,
3. consume additional input,
4. use results as they become valid,
5. re-plan only when new information materially changes the state.

Do not perform speculative state-changing actions from uncertain multimodal evidence.
