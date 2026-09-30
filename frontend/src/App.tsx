import { Link, Navigate, Route, Routes } from "react-router-dom";

import { MeetingPage } from "./features/meeting/MeetingPage";
import { MeetingsPage } from "./features/meetings/MeetingsPage";

export function App() {
  return (
    <div className="shell">
      <nav className="topbar">
        <Link to="/meetings" className="brand">
          AdVera
        </Link>
        <Link to="/meetings">Reuniones</Link>
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<Navigate to="/meetings" replace />} />
          <Route path="/meetings" element={<MeetingsPage />} />
          <Route path="/meetings/:meetingId" element={<MeetingPage />} />
          <Route path="*" element={<p>Página no encontrada.</p>} />
        </Routes>
      </main>
    </div>
  );
}
