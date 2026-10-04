# Feature: Rebuild synchronized playback of every track
Status: complete
Last updated: 2026-09-30

## Objective

Play every stored track of a meeting together, so that microphone and system audio are heard on the same timeline. Before this change the meeting page had one independent `<audio controls>` per track: each started, paused and sought on its own, and a click on a segment moved only that segment's track.

## Scope

Taken from `dual-track-playback-live-metrics.md` ("plays both tracks together", "synchronized playback controls for both tracks"):

- One transport for all tracks: play/pause, clock (`mm:ss / mm:ss`) and one position bar.
- The longest track is the master clock. Every 250 ms the others are moved back onto it when they drift more than 80 ms; a shorter track that already ended stays silent.
- A click on any transcript segment moves every track to the segment start and plays all of them. The `?t=` deep link from Brain citations moves every track without playing.
- A seek requested before the audio metadata loads is applied as soon as every track has it.
- Per-track mute and volume, so one side can be isolated without losing synchronization.
- Tracks stay separate files on separate audio endpoints (ADR 0005); nothing is mixed on the server or in the browser.

Out of scope: the playback position line over stored waveforms from the same historical record. The rebuild has no stored-audio waveform yet (`rebuild-live-capture-waveforms.md`).

## Acceptance criteria

1. A segment click leaves both tracks playing, within 0.3 s of each other, at or after the segment start.
2. A forced 1.5 s drift on one track is corrected while playing.
3. One pause stops every track; the position bar moves every track.
4. Muting one track does not mute the other.
5. Existing flows keep working: the import E2E plays from a segment, and the Brain citation opens the meeting at the cited second.

## Implementation state

Implemented.

## Files changed

- `frontend/src/features/meeting/SyncedPlayer.tsx` (new), `frontend/src/features/meeting/MeetingPage.tsx`, `frontend/src/styles.css`
- `frontend/tests/e2e/synced-playback.spec.ts` (new)

## Validation

- `npm run build` passes.
- Playwright: 14/14, including the new spec with two synthetic WAV tracks (30 s and 26 s tones, range requests served), which covers criteria 1–4; the import and Brain specs cover criterion 5.

## Risks

Browsers adjust `currentTime` to the nearest decodable position, so a correction can leave up to a few tens of milliseconds of offset; 80 ms keeps correction audible only when drift is real. Autoplay policies can refuse `play()` without a user gesture; a segment click is a gesture, the deep link does not auto-play.

## Next action

None.
