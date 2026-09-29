# Current implementation status — 2026-09-29

## Kaggle setup recovery — 2026-09-29

- Switched to `codex/fdb-v3-livekit-kaggle-handoff`; its 89-test baseline passed.
- Kaggle CLI 2.2.4 authenticated with an access token stored outside the repository.
  The existing private kernel and source dataset are accessible.
- The latest kernel had failed before dependency installation because Kaggle's
  Python 3.12 image lacked `ensurepip` for `venv`. The worker now installs the
  matching `python3.12-venv` package before creating its isolated environment,
  alongside `zstd` for Ollama. A new setup-order regression test was added.
- Kaggle's dataset CLI compressed nested source directories separately. The
  worker now accepts one explicit source archive and validates member paths
  before extraction. Two extraction regressions were added.
- Full suite: **92 tests passed** in 9.457 seconds on Python 3.11.15. No new
  FDB-v3 inference or score is claimed yet.
- `.gitignore` now excludes `.env.*` (except the example) and `.venv-fdb/` to
  prevent local settings or installed packages entering the source archive.

Next: upload the corrected private source and kernel, inspect its setup report,
then add the four provider values as Kaggle Secrets and run the first benchmark.
The camera extension, repeated seeded evaluation, video, and release package
remain open. No architectural contract changed in this recovery phase.

The updated Theme 05 guide changes the scored target to FDB-v3 and a LiveKit
voice agent. The repository now contains an initial FDB-v3 adapter using
ElevenLabs speech and a local Ollama reasoning model. **No FDB-v3 benchmark run
has completed, so this remains a migration build rather than a submission-ready
release.**

## FDB-v3 migration

- Added `agent.fdb_livekit`, a LiveKit cascaded agent with Silero VAD,
  ElevenLabs Scribe v2 Realtime, Ollama Qwen 3, ElevenLabs TTS, and the 12
  official tool signatures.
- Preserved disfluencies with `no_verbatim=False`; tool calls run in worker
  threads and emit the official room/timestamp telemetry.
- Added `scripts/fdb_v3.py` to pin the official benchmark at commit
  `3e799c45a045256f47d5f1c9cda90157e2d2ec9e`, obtain the released data, start
  the agent, run inference, and invoke all three evaluation scripts.
- Added the optional `fdb` dependency profile and an environment template with
  secret names only.
- The existing queue runtime and its 49.5 score are historical;
  they must not be presented as FDB-v3 results.

Immediate gates are a clean FDB dependency installation, LiveKit credentials,
an ElevenLabs key with credits, the released benchmark audio, and a GPU-hosted
Ollama model. After those are ready, run the official 100-recording benchmark
before revising the demo or slides.

The retained implementation is on `codex/interruptible-runtime`, based on
`6408a266867f573d50d3d08132bf6272563e8c6f`.

## Implemented and tested

- Completed-turn acknowledgments, coalesced audio, capped nonrepeating generic
  fillers, interruption cancellation, current state snapshots on every action,
  clarification follow-ups, and planner context containing call states/errors.
- Corrected-state speech before tool dispatch: the official harness does not
  retain snapshots attached to tool/cancel actions, so this makes the accepted
  correction observable before a final response.
- Shared local Ollama planning/vision, multilingual Whisper base CPU int8,
  computed 512-dimensional CLIP image embeddings, session-scoped frame reuse,
  embedding source validation, native worker ownership, and stale-output rejection.
- Schema-constrained output, manifest-constrained tool names, one bounded proposal
  repair, compact context with an explicit size guard, and a validated fallback
  for Ollama's misrouted JSON response field. See LOCAL_MODELS.md for limits.
- Explicit model download/readiness commands, dependency lock, Docker Compose
  setup, trace replay, editable review deck and captioned recorded-runtime demo.

## Test and source evidence

Python 3.11.16: **89 tests passed in 10.843 seconds** on 2026-09-24. Initial baseline was 70/71;
its 300 ms test-only harness tail was host-sensitive. That test now uses 3000 ms
with its assertions preserved. Official scenarios retain the original 6000 ms
harness tail and 120-second cap. No scorer or official scenario was edited.

All 34 vendored kit files match the supplied ZIP byte-for-byte. Git's Windows
checkout initially converted text line endings; `.gitattributes` now preserves
original kit bytes. Details: `artifacts/kit-integrity.json`.

## Actual local inference and timing

Ollama 0.34.3, Qwen3-VL 2B Q4_K_M, faster-whisper 1.2.1, FastEmbed 0.8.1.
Exact checkpoint revisions, Ollama digest, and perception-file hashes are in
`.models/model-manifest.json`, also copied into verification evidence.

The final combined readiness probe started with approximately 727 MiB available
RAM on an 8 GB i5-1135G7 Windows laptop:

| Check | Measured result |
| --- | --- |
| Model/provider setup | 11.21 s, succeeded |
| Text greeting | 27.89 s, failed to return a usable final response |
| Audio | 3.94 s, returned an uncertain/misheard transcript |
| Vision description | exceeded 60 s, timed out |
| Independent CLIP encoder | 512 finite dimensions; 0.639 s inference |

Earlier isolated audio probes took about 3.1–3.4 s; combined probes ranged from
2.4–14.2 s as memory pressure changed. The simple spoken Boston correction was
understood, while noisy/repair speech remained uncertain. Readiness **failed**;
no hosted fallback was used. The model was unloaded from RAM after benchmarking.

## Unmodified public evaluation

Nine scenarios, three repetitions each, `time_scale=1`, original scenario windows,
original setup/wall caps. Weighted automated score: **49.5/100**; plain: **49.3**.
Text: **47.6**, audio: **55.3**, visual: **47.7**. Each scenario produced the same
score in its three repetitions. The local evaluator does not apply the additional
LLM quality multiplier described in the kit's SCORING.md.

| Scenario | Median automated score |
| --- | ---: |
| pub_01_text_simple | 38.5 |
| pub_02_text_interrupt | 52.9 |
| pub_03_text_chained_booking | 38.5 |
| pub_04_text_no_tool | 69.2 |
| pub_05_audio_asr_ambiguity | 53.8 |
| pub_06_audio_disfluency | 56.9 |
| pub_07_visual_port_lookup | 47.7 |
| pub_08_text_tool_failure | 38.5 |
| pub_09_text_unseen_tool | 47.7 |

The separate full public trace pass and ten generated cases (five interruptions,
seed 20260924; five unseen tools, seed 20260925) had zero agent/setup/protocol errors.
The generated cases were verified against their recorded seeds.

Across 47 local runtime sessions (27 scored runs, one contract probe, and 19 trace
runs), **no tool calls were dispatched within the scenario windows**. There were
59 immediate acknowledgments, maximum 73 ms. Zero accepted stale results and zero
duplicate writes were observed, but without calls those counts do not prove live
coordination under tool load. The cancellation 800 ms gate therefore has no live
sample; deterministic tests separately cover cancellation, races and writes.

The score comes from acknowledgments, safe behavior, clarification and negative
checkpoints; it must not be presented as successful task completion. Model
reasoning/vision speed and quality remain the primary blockers.

Evidence: `artifacts/samsung-local-evaluation.json`, `samsung-public-traces.json`,
`generated-*-traces.json`, `verification-summary.json`, and `local-traces/*.jsonl`.

## Packaging and remaining gates

- Locked clean Python installation passed with no dependency conflicts. The wheel
  runs its demo with Python's isolated mode, independently of the source checkout;
  see `artifacts/clean-setup.txt` and `clean-demo.txt`.
- Docker Compose configuration validates. Actual image build/run remains blocked:
  Docker Desktop startup hits a stale socket, and automatic approval review rejected
  its removal with "blocked by policy". No reset or workaround deletion was performed.
- Any previously generated 12-slide deck, queue-runtime replay, or review archive
  under `output/submission` is historical and must not be submitted. The updated
  deck source is limited to eight slides and awaits real FDB-v3 results; the final
  3–5 minute video must show a live FDB interruption and the working extension.
- Team identities, the exact presentation template, AI disclosure review/signature,
  and final submission details remain team inputs. The Theme 5 PDF in the supplied
  ZIP is DRM-protected, so it was not independently read. Earlier document summaries
  are historical; the executable kit is the directly verified contract.
- Before release: obtain enough local inference capacity, improve model quality,
  rerun readiness and timed evaluation until task completion and cancellation are
  evidenced, verify Docker on a working engine, and review the team materials.
  Web dashboards, persistent memory and speculative writes remain deferred.

No commit, push, final release tag, signature or submission was made by this task.
Earlier phase notes are archived in [HISTORY.md](HISTORY.md).
