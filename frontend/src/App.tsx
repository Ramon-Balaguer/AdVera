import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import { z } from "zod";

import { MeetingPage } from "./features/meeting/MeetingPage";
import { MeetingsPage } from "./features/meetings/MeetingsPage";
import { MemoryPage } from "./features/memory/MemoryPage";
import { TimelinePage } from "./features/memory/TimelinePage";
import { SettingsPage } from "./features/settings/SettingsPage";
import { setLanguage } from "./i18n";
import { Logo } from "./Logo";

const languageSchema = z.object({ llm_output_language: z.string() });

// Navigation icons: plain strokes in the current colour, 20px.
const ICONS = {
  meetings: "M4 12h2M8 8v8M12 5v14M16 9v6M20 11v2",
  memory:
    "M12 4a3 3 0 1 0 0 6a3 3 0 1 0 0-6M5 15a2.5 2.5 0 1 0 0 5a2.5 2.5 0 1 0 0-5M19 15a2.5 2.5 0 1 0 0 5a2.5 2.5 0 1 0 0-5M10.5 9.5L6.5 15.5M13.5 9.5L17.5 15.5M7.5 17.5h9",
  settings: "M4 7h10M18 7h2M4 17h4M12 17h8M16 5v4M10 15v4",
};

function NavIcon({ path }: { path: string }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
      <path d={path} />
    </svg>
  );
}

export function App() {
  const { t } = useTranslation();
  // The interface speaks the language chosen in Settings (English until it is known).
  const settings = useQuery({
    queryKey: ["interface-language"],
    queryFn: async () => languageSchema.parse(await (await fetch("/api/settings")).json()),
    retry: false,
  });
  useEffect(() => {
    if (settings.data) setLanguage(settings.data.llm_output_language);
  }, [settings.data]);

  return (
    <div className="shell">
      <aside className="sidebar">
        <NavLink to="/meetings" className="brand" aria-label="AdVera">
          <Logo size={32} />
          <span className="brand-name">AdVera</span>
        </NavLink>
        <nav className="sidebar-nav" aria-label={t("nav.sections")}>
          <NavLink to="/meetings">
            <NavIcon path={ICONS.meetings} />
            {t("nav.meetings")}
          </NavLink>
          <NavLink to="/memory">
            <NavIcon path={ICONS.memory} />
            {t("nav.memory")}
          </NavLink>
          <NavLink to="/settings">
            <NavIcon path={ICONS.settings} />
            {t("nav.settings")}
          </NavLink>
        </nav>
      </aside>
      <main>
        <Routes>
          <Route path="/" element={<Navigate to="/meetings" replace />} />
          <Route path="/meetings" element={<MeetingsPage />} />
          <Route path="/meetings/:meetingId" element={<MeetingPage />} />
          <Route path="/memory" element={<MemoryPage />} />
          <Route path="/memory/timeline/:conceptId" element={<TimelinePage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<p>{t("nav.notFound")}</p>} />
        </Routes>
      </main>
    </div>
  );
}
