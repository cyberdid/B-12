# Evidence matrix

No claim is classified as independently verified. Project-tested means scoped evidence; C07 is a negative test result, not successful validation.

| Claim | Source | Evidence | Verification status | Paper section |
|---|---|---|---|---|
| C01: Shared stores are separate from the model | src/b12/runtime.py:68 | runtime factory + scripted integration fixtures; focused-tests.xml; code inspection | Implemented and tested by the project | Architecture |
| C02: Immutable admitted request | src/b12/context.py:37 | 35 context tests passed; immutable payload, overflow and grouped eviction; code inspection | Implemented and tested by the project | Context |
| C03: Exact local profile assets | src/b12/model_profile.py:38 | ModelProfile asset verification; context tests; historical calibration metadata; code inspection | Implemented and tested by the project | Context |
| C04: Per-call deployment validation | src/b12/model.py:226 | OllamaModel source + existing integration/test_ollama_transport.py; not rerun in this selection; code inspection | Implemented and tested by the project | Context |
| C05: Turn lifecycle and model lock | src/b12/agent.py:634 | 56 passed / 1 failed in test_agent_loop; failure scoped to fixed character budget; code inspection | Implemented and tested by the project | Control |
| C06: Working notes live in turn state | src/b12/agent.py:1077 | 7 tests in test_turn_notes passed; notes survive trimming in persist turn; code inspection | Implemented and tested by the project | Context |
| C07: Long persist character budget test fails | tests/integration/test_agent_loop.py:1109 | focused-tests.txt and repeat-test.txt: 11364 characters versus <10000; root cause unresolved; code inspection | Implemented and tested by the project | New checks |
| C08: Evidence-tagged sessions | src/b12/sessions.py:59 | SessionStore source and tests/unit/test_sessions.py; indirect coverage through agent tests; code inspection | Implemented and tested by the project | Memory |
| C09: Document version invalidation | src/b12/retrieval.py:93 | 8 document evidence tests passed; revision change and invalidation; code inspection | Implemented and tested by the project | Memory |
| C10: Memory can become stale | src/b12/memory.py:540 | 8 document tests plus 2 goal checkpoint tests; staleness is not deletion; code inspection | Implemented and tested by the project | Memory |
| C11: Coordinated deletion with receipts | src/b12/purge.py:29 | purge coverage and snapshot purge tests passed; scripted provider; managed stores only; code inspection | Implemented and tested by the project | Memory |
| C12: Goal checkpoints track evidence | src/b12/goals.py:157 | 2 goal-checkpoint evidence tests passed; forget removes dependent checkpoint, staleness pauses goal; code inspection | Implemented and tested by the project | Autonomy |
| C13: Scheduler uses non-full-execution grants | src/b12/autonomy.py:86 | Scheduler.run_goal source; existing project autonomy tests, not a fresh autonomous model run; code inspection | Implemented and tested by the project | Autonomy |
| C14: Attention gates proposals | src/b12/attention.py:112 | 6 attention-policy tests passed; injected clock; no user usefulness study; code inspection | Implemented and tested by the project | Autonomy |
| C15: Evidence-backed reflection | src/b12/reflection.py:26 | Reflector source reviewed; no new reflection inference or usefulness evaluation; code inspection | Implemented but not experimentally validated | Autonomy |
| C16: Unknown outcomes distinct from failure | src/b12/tools/outcomes.py:59 | HandlerOutcome source and registry integration contracts; selected loop tests; code inspection | Implemented and tested by the project | Control |
| C17: Voice interruption code exists | src/b12/audio/duplex.py:26 | DuplexSession and pipeline source; no physical acoustic test performed; code inspection | Implemented but not experimentally validated | Voice |
| C18: Desktop is a client | src/b12/desktop/client.py:52 | DesktopApiClient source and open PR #2 scope; no new UI acceptance run; code inspection | Implemented but not experimentally validated | Desktop |
| C19: Persona is prompt context | src/b12/persona.py:13 | local persona source hash differs from HEAD; no human consistency evaluation; code inspection | Implemented but not experimentally validated | Portability |
| C20: Live model switching not implemented | src/b12/runtime.py:81 | runtime startup constructs one adapter; no implemented atomic live-switch manager; code inspection | Proposed architecture | Portability |
| C21: Cross-model behavioral continuity unmeasured | wiki/topics/models.md:8 | no cross-model benchmark artifacts in this revision; future experiment explicitly scoped; code inspection | Future work | Portability |
| C22: Historical 496/541 | wiki/topics/evals.md:39 | 650 raw outcome rows reaggregated; 496/541 at 4096; validation.json; code inspection | Implemented and tested by the project | Results |
| C23: Physical robot acceptance absent | wiki/project/requirements-audit.md:31 | requirements audit declares physical acceptance absent; not closed by software tests; code inspection | Future work | Validity |
| C24: Voice hardware acceptance incomplete | wiki/topics/voice.md:8 | voice documentation and source; synthetic diagnostics do not prove physical performance; code inspection | Implemented but not experimentally validated | Voice |
| C25: Typed dispatch rechecks current authority | src/b12/tools/registry.py:182 | execute source, EffectGuard and existing tests/unit/test_registry.py; registry-specific tests not rerun in this selection | Implemented and tested by the project | Architecture |
| C26: Provider prompt mismatch handling is asymmetric | src/b12/model.py:288 | greater-than-admitted is rejected; smaller count is logged; source inspection only for this distinction | Implemented but not experimentally validated | Architecture |
