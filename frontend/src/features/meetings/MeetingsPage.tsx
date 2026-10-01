import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, describeError, ApiError } from "../../api";
import { formatTimestamp, STATUS_LABELS } from "../../format";

export function MeetingsPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const tags = useQuery({ queryKey: ["tags"], queryFn: api.listTags });
  const meetings = useQuery({ queryKey: ["meetings"], queryFn: api.listMeetings });
  const create = useMutation({
    mutationFn: (value: string) => api.createMeeting(value),
    onSuccess: (meeting) => {
      void queryClient.invalidateQueries({ queryKey: ["meetings"] });
      navigate(`/meetings/${meeting.id}`);
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (title.trim()) create.mutate(title.trim());
  };

  return (
    <section>
      <h1>Reuniones</h1>
      <form className="row" onSubmit={submit}>
        <label className="grow">
          <span className="visually-hidden">Título de la nueva reunión</span>
          <input
            value={title}
            maxLength={200}
            placeholder="Título de la nueva reunión"
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
        <button type="submit" disabled={!title.trim() || create.isPending}>
          Crear reunión
        </button>
      </form>
      {create.isError && (
        <p role="alert">
          {describeError(create.error instanceof ApiError ? create.error.code : null)}
        </p>
      )}

      {meetings.isPending && <p>Cargando reuniones…</p>}
      {meetings.isError && <p role="alert">No se pudieron cargar las reuniones.</p>}
      {meetings.data?.length === 0 && <p>Todavía no hay reuniones.</p>}
      {(tags.data?.length ?? 0) > 0 && (
        <label className="row">
          <span>Etiqueta</span>
          <select value={tagFilter} onChange={(event) => setTagFilter(event.target.value)}>
            <option value="">Todas</option>
            {tags.data!.map((tag) => (
              <option key={tag.concept_id} value={tag.concept_id}>
                {tag.label} ({tag.meetings})
              </option>
            ))}
          </select>
        </label>
      )}
      {meetings.data && meetings.data.length > 0 && (
        <table className="meetings">
          <thead>
            <tr>
              <th>Título</th>
              <th>Estado</th>
              <th>Duración</th>
              <th>Idiomas</th>
              <th>Asistentes</th>
              <th>Etiquetas</th>
            </tr>
          </thead>
          <tbody>
            {meetings.data
              .filter((meeting) => !tagFilter || meeting.tags.some((tag) => tag.concept_id === tagFilter))
              .map((meeting) => (
              <tr key={meeting.id}>
                <td>
                  <Link to={`/meetings/${meeting.id}`}>{meeting.title}</Link>
                </td>
                <td>{STATUS_LABELS[meeting.status]}</td>
                <td>{meeting.duration === null ? "—" : formatTimestamp(meeting.duration)}</td>
                <td>{meeting.primary_language.join(", ") || "—"}</td>
                <td>{meeting.attendee_count ?? "—"}</td>
                <td>{meeting.tags.map((tag) => tag.label).join(", ") || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
