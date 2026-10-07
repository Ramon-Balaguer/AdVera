# Feature: Whisper hallucinations at the start of a track
Status: complete
Last updated: 2026-10-06

## Objective
Stop the definitive transcript from opening with phrases Whisper-family models invent over noise or silence ("Thanks for watching!"), which appeared repeatedly at the start of system tracks.

## Scope
- A fixed list of known hallucinated phrases in English, Spanish and Catalan (including a lone "gracias", "thank you" or "gràcies", which noise also produces), compared after lowercasing and removing punctuation.
- Applied when a track's segments are normalized, so it covers every ASR provider.
- Only the opening of each track is cleaned: leading segments are dropped while they match the list; the first segment that does not match ends the cleaning.

## Acceptance criteria
- A track whose first segments are only listed phrases loses them and keeps its own segment numbering from `00000`.
- The same phrase later in the track is kept, because it can be real speech; so is a sentence that merely contains one ("Gracias por venir").
- Applies to new transcriptions; existing transcripts are not rewritten (there is no reprocessing yet).

## States and failures
- A track made only of listed phrases ends up with no segments, as a silent track would.

## Data and provenance constraints
Dropped segments are not stored. No contract or schema change.

## Assumptions and open questions
- The list is deliberately short and literal; new phrases are added when they are observed.

## Decisions
- Filter by position (start of the track) rather than by phrase alone, as requested by the operator.
