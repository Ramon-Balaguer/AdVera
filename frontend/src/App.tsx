import { Navigate, NavLink, Route, Routes } from "react-router-dom";

import { MeetingPage } from "./features/meeting/MeetingPage";
import { MeetingsPage } from "./features/meetings/MeetingsPage";
import { MemoryPage } from "./features/memory/MemoryPage";
import { TimelinePage } from "./features/memory/TimelinePage";
import { SettingsPage } from "./features/settings/SettingsPage";
import { Logo } from "./Logo";

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
  return (
    <div className="shell">
      <aside className="sidebar">
        <NavLink to="/meetings" className="brand" aria-label="AdVera">
          <Logo size={32} />
          <span className="brand-name">AdVera</span>
        </NavLink>
        <nav className="sidebar-nav" aria-label="Secciones">
          <NavLink to="/meetings">
            <NavIcon path={ICONS.meetings} />
            Reuniones
          </NavLink>
          <NavLink to="/memory">
            <NavIcon path={ICONS.memory} />
            Memoria
          </NavLink>
          <NavLink to="/settings">
            <NavIcon path={ICONS.settings} />
            Ajustes
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
          <Route path="*" element={<p>Página no encontrada.</p>} />
        </Routes>
      </main>
    </div>
  );
}
