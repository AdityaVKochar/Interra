# Full Duplex Bench v3 migration

The updated Theme 05 participant guide received on 2026-09-24 replaces the
earlier queue protocol with Full-Duplex-Bench v3 and a LiveKit voice-agent
runtime. This document records the requirements that now govern the submission.

## Official benchmark

- Repository: `DanielLin94144/Full-Duplex-Bench`, `v3/` directory.
- Pinned repository commit for local reproduction:
  `3e799c45a045256f47d5f1c9cda90157e2d2ec9e`.
- Released set: 100 recordings, 79 unique scenarios, 12 speakers.
- Domains: travel and identity, finance and billing, housing and location,
  and ecommerce support.
- Difficulty: one, two, or three chained tool calls.
- Speech conditions: fillers, pauses, hesitation, false starts, and
  self-correction.

The benchmark code and released audio remain external and are not copied into
the submission repository. `scripts/fdb_v3.py bootstrap` checks out the official
source at the pinned revision, and `--download-data` obtains the published data.

## Submission contract

The repository must provide:

1. A LiveKit voice agent using any supported realtime or cascaded architecture.
2. Exact setup and run steps plus a one-command end-to-end reproduction path.
3. FDB-v3 results and logs including seeds and model configuration.
4. One working extension beyond the benchmark domains.
5. A three-to-five-minute video showing a real benchmark interruption and the
   extension running end to end.
6. A slide deck of no more than eight slides.

Round 1 weighting is 60 percent official normalized benchmark score, 20 percent
extension, and 20 percent documentation, architecture, and video. Ties use the
strict pass-rate component. The organizers re-run the submission on one NVIDIA
48 GB GPU with CUDA 12.x or 13.x, or against declared hosted APIs.

## Interra provider profile

The first FDB-v3 profile is a cascaded LiveKit session:

- Silero VAD for speech boundaries.
- ElevenLabs Scribe v2 Realtime for STT with `no_verbatim=False` so corrections
  and disfluencies are retained.
- Ollama Qwen 3 8B for tool selection and chained reasoning.
- ElevenLabs Turbo v2.5 for streaming TTS.
- The official `MockAPIRegistry` loaded from the pinned benchmark checkout.

Required hosted secret names are `LIVEKIT_URL`, `LIVEKIT_API_KEY`,
`LIVEKIT_API_SECRET`, and `ELEVEN_API_KEY`. `OPENAI_API_KEY` is needed only to
reproduce the optional local LLM-judge reports; the organizers use their pinned
judge for official scoring.

## Rules preserved in implementation

- No benchmark examples or expected answers are placed in prompts or code.
- No state is cached across scenarios.
- Hosted speech APIs are declared; no team-owned server is called at evaluation.
- Tool results, not model memory, ground the final response.
- Versions, model IDs, benchmark commit, configuration, and reports are recorded.
- Credentials remain outside Git.

## Extension

Camera-assisted device troubleshooting remains the selected extension because
the repository already contains asynchronous image observations, source-bound
embeddings, correction-aware state, and stale-result rejection. It is not complete
for the new guide until it is reachable through the LiveKit session and appears
in a genuine end-to-end video.

## Historical work

The queue adapter, nine-scenario Samsung kit, `submission.yaml`, and prior 49.5
score belong to the superseded evaluation contract. They are retained as
engineering evidence and regression coverage, but they must not be reported as
FDB-v3 results.
