import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import { z } from "zod";

import { MeetingPage } from "./features/meeting/MeetingPage";
import { MeetingsPage } from "./features/meetings/MeetingsPage";
import { BrainPage } from "./features/brain/BrainPage";
import { TimelinePage } from "./features/brain/TimelinePage";
import { SettingsPage } from "./features/settings/SettingsPage";
import { setLanguage } from "./i18n";
import { Logo } from "./Logo";

const languageSchema = z.object({ llm_output_language: z.string() });

// Navigation icons: plain strokes in the current colour, 20px.
const ICONS = {
  meetings: "M4 12h2M8 8v8M12 5v14M16 9v6M20 11v2",
  // Two hemispheres joined by the midline, with a fold in each.
  brain:
    "M12 5v13.2M12 5C10.8 3.8 8.6 3.8 7.6 5.2C6 5.2 5 6.6 5.4 8C4.2 8.8 4 10.6 5 11.6C4.2 12.8 4.6 14.6 5.9 15.2C6 16.9 7.6 18 9.2 17.6C10 18.6 11.4 18.8 12 18.2M12 5C13.2 3.8 15.4 3.8 16.4 5.2C18 5.2 19 6.6 18.6 8C19.8 8.8 20 10.6 19 11.6C19.8 12.8 19.4 14.6 18.1 15.2C18 16.9 16.4 18 14.8 17.6C14 18.6 12.6 18.8 12 18.2M8.4 9.6C9.5 9.5 10.5 10 11 11M15.6 9.6C14.5 9.5 13.5 10 13 11",
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
          <NavLink to="/brain">
            <NavIcon path={ICONS.brain} />
            {t("nav.brain")}
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
          <Route path="/brain" element={<BrainPage />} />
          <Route path="/brain/timeline/:conceptId" element={<TimelinePage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<p>{t("nav.notFound")}</p>} />
        </Routes>
      </main>
    </div>
  );
}
