# Local Companion Implementation Plan

> User-authorized implementation plan; execution and independent reviews completed in this task.

**Goal:** Deliver a double-click local companion with speech interruption, playback-confirmed context, scene memory, and Codex background tasks.

**Architecture:** Local FastAPI runtime, browser/Electron avatar surface, existing SiliconFlow providers, stdio Codex adapter. Keep generated speech drafts separate from persisted heard conversation, and admit only a short current utterance instead of a FIFO of replies. Memory and tasks persist in SQLite; secrets use Windows DPAPI.

**Tech Stack:** Python 3.12, FastAPI, httpx, SQLite, browser WebAudio, Electron, pytest and Playwright.

---

User authorized implementation and autonomous decisions while away. Execute and review batches without waiting for permission. No publishing or external messages.

## Upstream spike decision

Inspected N.E.K.O. commit e1fa3482509132532a242d841b98d55ba03d4c4b in .reference/neko. Its source already has interruption and playback gates, but text turn sinks, provider sessions and separate memory services require coordinated changes for playback-confirmed history. Its package pins Python 3.11 and includes the broad companion/agent/plugin dependency set. Do not claim its full runtime failed; it was not installed. For the first independently verifiable local slice, implement the narrow runtime here, using N.E.K.O./Neuro/LiveKit behavior as references, rather than importing the entire application or duplicating two active memory systems. This is a small original application, not a N.E.K.O. fork or a claim to have integrated its runtime.

## Tasks

1. `companion/store.py`, `tests/test_store.py`: persist user messages and only confirmed speech; scene/public filters, source-linked memories, correction/forget, task records. Test restart, scene separation, deletion and ordered idempotent playback commits.
2. `companion/speech.py`, `tests/test_speech.py`: short segment ledger; cancel drops unplayed suffix and rejects stale ACK; bounded merge/admission for incoming messages. Test interrupt before/during/after playback and burst input.
3. `companion/providers.py`, `companion/codex.py`: use verified HTTP providers and local app-server; narrow task events, cancel/resume and settings. Preserve secrets outside code/reports.
4. `companion/app.py`: local HTTP/WebSocket orchestration, background memory extraction, scene recall, synthetic-file ASR, settings and task controls. Actual next model context must contain no unplayed draft.
5. `web/`, `desktop/`: distinctive warm desktop pet surface, animated cat or user GIF/APNG, text input, microphone with VAD, short audio playback and ACK on actual completed segments, immediate Stop, memory/source panel and task panel. Electron compact pet mode and normal window.
6. `start.ps1`, `start.cmd`, `README.md`: hidden background local runtime, one-click launch and clear setup/errors. Browser fallback and OBS-compatible transparent overlay.
7. `tests/` + `probes/local_acceptance.py`: unit/integration regressions, real provider chat/TTS/ASR, synthetic microphone/browser playback interruption, fresh-process memory recall and Codex task. Report simulated audio/device boundaries honestly; capture visible UI and verify launcher.

## Verification gates

- First write and run failing core regression tests; then implement.
- `python -m pytest tests -q`: behavioral tests pass.
- `node --check web/app.js` and desktop syntax check.
- Real local app acceptance produces artifacts with actual request timings and sanitized contexts.
- Visual browser/Electron inspection verifies actual controls and absence of console errors.
- `git diff --check`, credential-pattern scan, local commit of tested source; no push.

## Status

- [x] Scope approved; upstream source inspected.
- [x] Store and speech ledger.
- [x] Runtime and model/task adapters.
- [x] Desktop UI and synthetic microphone pipeline.
- [x] Acceptance and runnable handoff; physical microphone/acoustic behavior remains unverified.
