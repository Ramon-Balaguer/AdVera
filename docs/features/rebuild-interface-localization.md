# Feature: Rebuild interface in English, Spanish and Catalan
Status: complete
Last updated: 2026-10-02

## Objective

Every static text of the interface follows the language chosen in Settings, in English, Spanish or Catalan, with English by default. This completes the slice left open by `interface-language-and-llm-response-language.md` ("a shared translation catalog for all screens").

## Scope

In scope:
- One language setting for the interface and for Summary and Brain answers, as `interface-language-and-llm-response-language.md` defines: `en`, `es` or `ca`, default `en` (`llm_output_language`). Summary and Brain now also write in Catalan.
- `react-i18next` with one catalog per language (`frontend/src/i18n/{en,es,ca}.ts`): buttons, headings, labels, placeholders, `aria-label`s, tooltips, statuses, error messages, plurals and interpolated values. The Spanish and Catalan catalogs are typed against the English one and keys are typed (`CustomTypeOptions`), so a missing translation or an unknown key fails the build.
- The language is read from Settings when the app starts and applied at once when Settings are saved, with no reload; `<html lang>` follows it. Dates use the language's locale.
- Each language is offered in Settings in its own name (English, Español, Català).

Out of scope: translating data (transcripts, titles, notes, concept names); the startup screen shown before the API answers, which uses the default, English.

## Acceptance criteria

1. With English, Spanish or Catalan in Settings, every static text of every page is in that language.
2. Saving another language switches the interface at once.
3. Without a saved language the interface and Summary use English.
4. A missing translation is a build error.

## Implementation state

Implemented, tested and deployed. An installation that had saved Spanish keeps Spanish until the operator changes it in Settings.

## Decisions

- `react-i18next`, the industry standard, from the start (operator decision), instead of a hand-made module.
- The catalogs are generated from one translation table during this change, then maintained as files.
- Summary and Brain keep using the same setting (ADR 0009): `ca` adds Catalan output; the default changes from Spanish to English.

## Files changed

- `backend/app/{config,runtime_settings,settings_api,summary,brain_answer}.py`; tests `test_llm_settings.py`, `test_summary.py`
- `frontend/src/i18n/{index,en,es,ca}.ts`, `frontend/src/i18n/i18next.d.ts` (new); `frontend/src/{App,ApiHealthGate,main,api,format}.ts*`; every component under `frontend/src/features/`
- `frontend/tests/e2e/fixtures.ts` (new: the existing tests run in Spanish), `frontend/tests/e2e/{api-health-gate,summary-settings}.spec.ts`

## Validation

- `npm run build` (type-checked keys and catalogs); Playwright 49 passed, including switching to English when saving Settings and a page rendered in Catalan; backend 266 passed (Catalan prompt, English default, `ca` accepted).

## Risks

- New text added without a key shows untranslated; reviews should look for literal text in components.

## Next action

None.
