# Supplied material review and remaining submission work

Reviewed on 2026-09-23 against the actual local attachments.

## Runtime requirements now available

The participant ZIP supplies the Theme 05 protocol, dynamic tool definitions,
unmodified harness/scorer/evaluator, nine public scenarios, MP3 audio, and a PNG
frame. These supersede earlier assumptions that the evaluator was unavailable.
See `vendor/samsung_theme05/docs/PROTOCOL.md` and `TOOLS.md`.

Implemented `interra_submission:ParticipantAgent`, with optional asynchronous
setup and the required two-queue constructor. The adapter converts milliseconds
to internal seconds, generates session-local event IDs, recursively converts tool
schemas, preserves explicit call IDs, and moves final snapshots to the top level.
Only read-only tools receive a single automatic retry. `scenario_end` leaves the
agent running for the harness's tool-result grace period. Cancellation owns and
awaits the runtime, bridge tasks, media subprocesses, and HTTP client cleanup.

The kit's MP3 references are resolved relative to an explicit media root and
decoded with ffmpeg into the existing validated WAV provider contract. Consecutive
audio chunks are combined in order, and planning waits for end of turn. Missing
media requests clarification. References cannot escape the configured root.
Frames remain context for following text, with original observation provenance
and device hints. Explicit interruption clears the frame, invalidates old work,
and replans the interruption's supplied text. The local protocol retains its
existing stricter epoch behavior unless frame retention is explicitly enabled.

## Conflicts and decisions

- The earlier theme guide says WAV; the executable kit supplies MP3. Both work
  through the adapter; the core audio provider still receives WAV.
- The broad brochure mentions retrieving before turn end. The precise kit says
  waiting for `end_of_turn` is a safe baseline. This implementation waits.
- FAQ v4, Theme 5 Q33, says the scenario cap can be relaxed to 300 seconds.
  The supplied evaluator still defaults to 120 seconds. Keep that stricter
  executable default; setup remains capped at 300 seconds.
- The FAQ includes extensive Theme 02 REST/health/deeplink/cache instructions.
  Those do not apply to this Theme 05 queue agent.
- The kit permits shared model weights, but session state remains isolated.
  This implementation does not introduce shared mutable user state.

## Running the supplied evaluator

Install the project using the root README. ffmpeg must be on PATH, or set
`INTERRA_FFMPEG` to its executable. The Dockerfile installs ffmpeg.

Configure `INTERRA_MODEL` with an already installed Ollama model and optionally
`INTERRA_OLLAMA_URL`. `INTERRA_AUDIO_URL` and `INTERRA_VISION_URL` select services
implementing the documented WAV/PNG observation contracts. These services are
integration interfaces, not included ASR/vision models. Evaluation requires
reproducible local perception implementations or permitted direct model APIs;
do not host decision logic on a private remote server.

PowerShell, from the repository root:

```powershell
$env:INTERRA_MEDIA_ROOT = (Resolve-Path vendor/samsung_theme05).Path
.venv/Scripts/python scripts/run_samsung.py
.venv/Scripts/python vendor/samsung_theme05/eval_submission.py . --reps 3 --time-scale 1 --out artifacts/samsung-evaluation.json
```

The trace runner rejects missing model configuration by default. Use
`--allow-unconfigured` only to verify the safe fallback and harness wiring.
The official evaluator itself does not check model readiness, team placeholders,
or quality, so passing its import/contract stages is not submission readiness.

## Evidence and limits

No local model answered on ports 11434, 1234, or 8000, and no Interra model
configuration was present during this review. No model was downloaded or invented.
The official evaluator completed its import and contract stages and all nine
public scenarios at scale 1 with one repetition. The unconfigured fallback scored
48.9 weighted / 48.8 plain average; this mostly reflects acknowledgments and
safe clarification, **not demonstrated task completion**. Output is generated at
`artifacts/samsung-unconfigured-evaluation.json`.

Deterministic tests separately exercise the real runtime and official harness
with scripted reasoning: nested unseen tools, chained reads/writes, duplicate
write suppression, interruption replacement, stale results, grace-period results,
frame retention, chunked audio, malformed input, shutdown, and actual MP3 decoding.
They prove integration and coordination, not model quality or hidden-test scores.

## Submission materials

The supplied PowerPoint template contains 12 slides: team cover; theme; existing
solutions/gaps; solution/architecture; demo; tools; impact; innovation/results/
limitations; next steps; differentiation; checklist; thanks. The existing
`SUBMISSION_DECK.md` is content source, not a finished copy of that template.
The supplied disclosure form requests AI usage, purpose, feature origins, tools,
prompts, outputs/modifications, and a representative's declaration/signature.

Still needed from the team: college/team/member identities, repository link,
chosen and configured reasoning/ASR/vision models, live three-repetition results,
a finished template-based deck, a genuine video of at most five minutes, and a
reviewed/signed AI disclosure. AI-assisted implementation/testing/documentation
in this repository must be disclosed accurately; no signature or compliance
attestation has been fabricated. Replace the explicit team placeholder in
`submission.yaml` before submission.

The brochure/FAQ specify 25 September 2026 at 11:59 PM and final release tag
`PRISM_GENAI_HACKATHON_Y2026`. Those are document requirements, not authorization
to publish, push a tag, sign a form, or submit on the user's behalf. No release
has been marked final while model and submission-material requirements remain.
