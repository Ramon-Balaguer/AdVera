# Feature: Live meeting summary
Status: complete
Last updated: 2026-09-18

## Objective
Replace the live provisional transcript view with a periodic, clearly provisional summary so a meeting participant can follow the discussion without reading unstable ASR output in real time.

## Smallest useful increment
During an active capture, accumulate live ASR segments internally and periodically send a structured LLM summary containing topics, detected decisions, actions and open questions. Render that artifact in the `Live` tab with its update state and covered time range.

## Scope
- Rename `Live Provisional` to `Live`.
- Keep provisional segments as internal LLM input, not the primary live UI.
- Add configurable interval, minimum new segment count and LLM provider/model settings.
- Allow the user to force a refresh with all live segments accumulated so far.
- Emit summary, generating, unavailable and recoverable error events.
- Preserve the last valid summary when a later update fails.
- Keep definitive transcript unchanged and authoritative.
- Preserve meeting id, covered time range, input hash, provider/model and prompt contract version.

## Acceptance criteria
- The UI says `Live` and shows summary content instead of provisional cards.
- A summary is requested only after enough new live content and the configured interval.
- The `Actualizar` action forces a refresh with the accumulated live transcript and prevents concurrent requests.
- The summary contains only structured output, never chain-of-thought.
- Each summary is marked provisional and includes its generation time and covered range.
- LLM failure leaves the last valid summary visible and exposes a retryable error state.
- No summary infers speaker identity from microphone/system track labels.
- Definitive transcript remains available and is not overwritten by live summaries.
- Missing LLM configuration does not stop audio capture or live ASR.

## States and failures
No content, waiting for the next interval, generating, available, unchanged, unavailable, recoverable error, and final definitive handoff.

## Data and provenance constraints
The definitive transcript is the source of truth. Live summaries are derived and provisional. Store summary text and structured conclusions with meeting id, generation timestamp, covered range, input hash, provider, model and prompt contract version. Do not store prompts unnecessarily or chain-of-thought. Track source is metadata only; it is not speaker identity.

## Decisions
Use a hybrid incremental strategy: send new segments plus the previous structured summary, and compact periodically as context grows. Each response must return the complete accumulated state, and incomplete model output is rejected without replacing the last valid state. The first implementation uses an Ollama-compatible HTTP provider, disabled by default, so local capture remains usable without an LLM.

## Files changed
- `backend/app/config.py`
- `backend/app/contracts.py`
- `backend/app/live_summary.py`
- `backend/app/audio.py`
- `backend/tests/test_live_summary.py`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`

## Validation
- Backend source and focused test compile successfully with `python -m compileall`.
- Frontend `npm run build` passes in the frontend container.
- Browser snapshot confirms the `Live` tab and waiting state render without provisional cards.
- Backend pytest could not run because the API image does not include the `pytest` module.

## Risks and next action
Live summaries can be wrong because ASR is provisional. Keep the UI warning visible and regenerate the final summary from the definitive transcript in a later intelligence slice. The development Compose defaults to the provided Ollama endpoint and `ornith-1.5:35b`; override `LLM_PROVIDER`, `LLM_MODEL` or `LLM_BASE_URL` through the environment when deploying elsewhere. Validate with a completed meeting containing multiple speakers.
