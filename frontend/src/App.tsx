import { Link, Navigate, Route, Routes } from "react-router-dom";

import { MeetingPage } from "./features/meeting/MeetingPage";
import { MeetingsPage } from "./features/meetings/MeetingsPage";
import { MemoryPage } from "./features/memory/MemoryPage";
import { TimelinePage } from "./features/memory/TimelinePage";
import { SettingsPage } from "./features/settings/SettingsPage";

export function App() {
  return (
    <div className="shell">
      <nav className="topbar">
        <Link to="/meetings" className="brand">
          AdVera
        </Link>
        <Link to="/meetings">Reuniones</Link>
        <Link to="/memory">Memoria</Link>
        <Link to="/settings">Ajustes</Link>
      </nav>
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
