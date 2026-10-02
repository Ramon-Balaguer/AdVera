import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import { ca } from "./ca";
import { en } from "./en";
import { es } from "./es";

// The interface language is the one in Settings (interface-language-and-llm-response-language.md):
// English, Spanish or Catalan, English by default. Data (transcripts, titles, notes) is never
// translated; Brain and Memory answers follow the same setting.
export const LANGUAGES = ["en", "es", "ca"] as const;
export type Language = (typeof LANGUAGES)[number];

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, es: { translation: es }, ca: { translation: ca } },
  lng: "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false }, // React escapes
});
document.documentElement.lang = "en";

export function setLanguage(language: string) {
  const next = (LANGUAGES as readonly string[]).includes(language) ? language : "en";
  if (i18n.language !== next) void i18n.changeLanguage(next);
  document.documentElement.lang = next;
}

/** The locale for dates and numbers of the current language. */
export const locale = () => ({ en: "en-GB", es: "es-ES", ca: "ca-ES" })[i18n.language as Language] ?? "en-GB";

export default i18n;
