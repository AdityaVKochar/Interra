# Definition of done

The updated participant guide makes FDB-v3, LiveKit, and a working extension the
submission contract. The old queue-kit checklist is retained in Git history and
its tests remain useful, but it no longer defines completion.

## FDB-v3 agent

- [x] LiveKit voice-agent entry point exists.
- [x] The 12 official tool signatures are exposed to the model.
- [x] Tool execution does not block the event loop.
- [x] Tool calls use the room identifier and benchmark telemetry format.
- [x] ElevenLabs Scribe v2 Realtime is configured with disfluencies preserved.
- [x] ElevenLabs TTS model and voice are explicitly pinned by configuration.
- [x] Ollama is available as the local tool-calling LLM backend.
- [ ] Clean environment installation of the FDB dependency profile passes.
- [ ] LiveKit Cloud credentials and dispatch are validated end to end.
- [ ] Every released recording completes without agent or protocol crashes.

## Benchmark evidence

- [x] Official repository revision is pinned.
- [x] Reproduction runner can bootstrap the benchmark and published data.
- [x] Runner starts the agent, runs inference, and invokes all three evaluators.
- [ ] Best run covers all 100 recordings.
- [ ] Tool-selection F1 report is saved.
- [ ] Semantic argument and response report is saved with the LLM judge enabled.
- [ ] Strict pass-rate report is saved.
- [ ] First-response, tool-call, and task-completion latency report is saved.
- [ ] Seeds, model versions, provider configuration, and run logs are archived.
- [ ] Reproduction is verified on a clean machine.

## Interruption and correction behavior

- [x] Existing deterministic tests cover cancellation, stale results, corrections,
  duplicate writes, and timing races.
- [x] FDB STT preserves fillers, false starts, and self-corrections.
- [ ] A real FDB recording proves the latest correction reaches tool arguments.
- [ ] A real live interruption stops obsolete speech and work.
- [ ] Multi-step tool chains use returned identifiers rather than guessed values.
- [ ] No benchmark scenario is hard-coded, memorized, or used for fine-tuning.
- [ ] No scenario state is cached across conversations.

## Extension use case

- [x] Camera-assisted device troubleshooting is selected.
- [x] Image observations, embeddings, provenance, and stale-result rejection exist
  in the retained runtime.
- [ ] Camera input is connected to the LiveKit voice session.
- [ ] The extension runs end to end with a real user interruption or correction.
- [ ] The extension appears in the final demo video.

## Documentation and submission

- [x] README identifies FDB-v3 as the current benchmark.
- [x] Exact environment-variable names are documented without secret values.
- [x] Hosted and local model responsibilities are documented honestly.
- [ ] Final benchmark scores replace all placeholder or legacy score references.
- [ ] Demo video is three to five minutes and shows real behavior.
- [ ] Slide deck is no more than eight slides.
- [ ] Team identities and submission form are complete.
- [ ] The last uploaded submission is verified as the intended final version.

Only mark a box complete when a report, trace, test, or recorded run proves it.
