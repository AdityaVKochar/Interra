# Definition of done

The updated participant guide makes FDB-v3, LiveKit, and a working extension the
submission contract. The old queue-kit checklist is retained in Git history and
its tests remain useful, but it no longer defines completion.

## FDB-v3 agent

- [x] LiveKit voice-agent entry point exists.
- [x] The 12 official tool signatures are exposed to the model.
- [x] Tool execution does not block the event loop.
- [x] Tool calls use the room identifier and benchmark telemetry format.
- [x] LiveKit Inference STT and TTS model IDs and voice are pinned by configuration.
- [x] LiveKit Inference LLM is the default; Ollama remains an optional backend.
- [ ] Clean environment installation of the FDB dependency profile passes.
- [x] LiveKit Cloud credentials and dispatch are validated by the 100-case run.
- [ ] Every released recording completes without agent or protocol crashes.

## Benchmark evidence

- [x] Official repository revision is pinned.
- [x] Reproduction runner can bootstrap the benchmark and published data.
- [x] Runner starts the agent, runs inference, and invokes all three evaluators.
- [x] A baseline run covers all 100 recordings and all result files are archived.
- [x] Official tool-selection report is saved.
- [ ] Semantic argument and response report is saved with the LLM judge enabled.
- [x] Strict pass-rate report is saved (baseline 31/100).
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
- [x] Camera input is connected to a separate LiveKit voice session
  (`python -m agent.extension_livekit start`). It does not join the benchmark tool set.
- [ ] The extension runs end to end with a real user interruption or correction.
- [ ] The extension appears in the final demo video.

## Documentation and submission

- [x] README identifies FDB-v3 as the current benchmark.
- [x] Exact environment-variable names are documented without secret values.
- [x] Hosted and local model responsibilities are documented honestly.
- [ ] Final hosted-LLM scores replace baseline and placeholder references.
- [ ] Demo video is three to five minutes and shows real behavior.
- [ ] Slide deck is no more than eight slides.
- [ ] Team identities and submission form are complete.
- [ ] The last uploaded submission is verified as the intended final version.

Only mark a box complete when a report, trace, test, or recorded run proves it.
