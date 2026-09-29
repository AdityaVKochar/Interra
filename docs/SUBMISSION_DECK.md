# Submission deck source

The updated participant guide limits the final deck to eight slides. Team names
and measured FDB-v3 results must be completed by the submitters; placeholders
must not be presented as final.

## Slide 1 Interra

- Theme 05 Interruptible Real Time Agents
- Samsung PRISM GenAI Hackathon 2026
- Team and college details supplied by the team

## Slide 2 Problem and benchmark

- People hesitate, self-correct, and interrupt while an agent is working.
- FDB-v3 uses 100 recordings, 79 scenarios, 12 tools, and up to three chained calls.
- It scores tool selection, argument accuracy, strict pass rate, response quality,
  and latency.

## Slide 3 Architecture

- LiveKit carries full-duplex audio and interruption events.
- ElevenLabs Scribe v2 Realtime preserves disfluencies for correction handling.
- Ollama Qwen 3 performs tool selection and chained reasoning.
- ElevenLabs Turbo v2.5 streams concise speech.
- The official deterministic mock APIs ground responses.

## Slide 4 Correction and tool lifecycle

- Partial speech remains interruptible.
- The latest correction replaces obsolete values before tool dispatch.
- Dependent calls consume returned identifiers and values.
- Tool telemetry records the room, arguments, results, and timing.
- Retained runtime tests cover cancellation, stale-result rejection, and duplicate writes.

## Slide 5 FDB-v3 results

- Replace with the official best-run tool-selection F1.
- Replace with semantic argument and response accuracy.
- Replace with strict pass rate.
- Replace with median first-response, first-tool, and completion latency.
- Include provider/model versions, seed information, and report names.

Do not use the historical 49.5 queue-kit score on this slide.

## Slide 6 Extension use case

- Camera-assisted device troubleshooting.
- A frame is linked to the current conversation with source provenance.
- The user can correct the device, symptom, or intended action while analysis runs.
- Obsolete image/model results cannot complete the updated task.
- Replace this plan with measured end-to-end evidence before submission.

## Slide 7 Evidence and limitations

- Reproduction command and pinned FDB-v3 commit.
- Clean-machine result and crash count.
- Hosted speech depends on declared ElevenLabs credentials and service availability.
- Local Qwen quality and latency must be reported from the final GPU run.
- State any failed scenario categories honestly.

## Slide 8 Demonstration and next work

- Show one real FDB-v3 interruption or self-correction.
- Show the extension use case running end to end.
- Keep the video between three and five minutes.
- Finish with the single most important measured improvement still needed.
