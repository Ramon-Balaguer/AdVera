import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, describeError, ApiError } from "../../api";
import { formatTimestamp, STATUS_LABELS } from "../../format";
import { clearNotesDraft } from "../meeting/MeetingNotes";
import { TagPicker } from "../tags/TagPicker";

export function MeetingsPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [newTags, setNewTags] = useState<string[]>([]);
  const [tagFilter, setTagFilter] = useState("");
  // Several meetings can be selected and deleted together, after an explicit confirmation.
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirming, setConfirming] = useState(false);
  // Deleting several meetings is irreversible: it is confirmed by solving a sum (operator
  // request), so it cannot happen by a stray click.
  const [challenge, setChallenge] = useState<[number, number]>([0, 0]);
  const [answer, setAnswer] = useState("");
  const [deleting, setDeleting] = useState<{ done: number; total: number } | null>(null);
  const [failures, setFailures] = useState<string[]>([]);
  const allBox = useRef<HTMLInputElement>(null);
  const tags = useQuery({ queryKey: ["tags"], queryFn: api.listTags });
  const meetings = useQuery({ queryKey: ["meetings"], queryFn: api.listMeetings });
  const create = useMutation({
    mutationFn: (value: string) => api.createMeeting(value, newTags),
    onSuccess: (meeting) => {
      void queryClient.invalidateQueries({ queryKey: ["meetings"] });
      void queryClient.invalidateQueries({ queryKey: ["tags"] });
      void queryClient.invalidateQueries({ queryKey: ["concept-graph"] });
      navigate(`/meetings/${meeting.id}`);
    },
  });

  const visible = (meetings.data ?? []).filter(
    (meeting) => !tagFilter || meeting.tags.some((tag) => tag.concept_id === tagFilter),
  );
  const chosen = visible.filter((meeting) => selected.has(meeting.id));
  // Only what is on screen can be selected: changing the filter clears the selection.
  useEffect(() => {
    setSelected(new Set());
    setConfirming(false);
  }, [tagFilter]);
  useEffect(() => {
    if (allBox.current) allBox.current.indeterminate = chosen.length > 0 && chosen.length < visible.length;
  }, [chosen.length, visible.length]);

  const toggle = (id: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const toggleAll = () =>
    setSelected(chosen.length === visible.length ? new Set() : new Set(visible.map((meeting) => meeting.id)));

  const deleteSelected = async () => {
    setConfirming(false);
    setFailures([]);
    const failed: string[] = [];
    const kept = new Set<string>();
    setDeleting({ done: 0, total: chosen.length });
    for (const [index, meeting] of chosen.entries()) {
      try {
        await api.deleteMeeting(meeting.id);
        clearNotesDraft(meeting.id);
      } catch (error) {
        kept.add(meeting.id);
        failed.push(`${meeting.title}: ${describeError(error instanceof ApiError ? error.code : null)}`);
      }
      setDeleting({ done: index + 1, total: chosen.length });
    }
    setDeleting(null);
    setSelected(kept); // what could not be deleted stays selected
    setFailures(failed);
    void queryClient.invalidateQueries({ queryKey: ["meetings"] });
    void queryClient.invalidateQueries({ queryKey: ["tags"] });
    void queryClient.invalidateQueries({ queryKey: ["concept-graph"] });
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (title.trim()) create.mutate(title.trim());
  };

  return (
    <section>
      <h1>Reuniones</h1>
      <form className="new-meeting" onSubmit={submit}>
        <div className="row">
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
        </div>
        <TagPicker
          value={newTags}
          onChange={setNewTags}
          options={tags.data ?? []}
          allowNew
          label="Etiquetas de la nueva reunión"
          placeholder="Etiquetas: proyectos, empresas, personas, conceptos…"
        />
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
          <select
            value={tagFilter}
            onChange={(event) => setTagFilter(event.target.value)}
            aria-label="Filtrar la lista por etiqueta"
          >
            <option value="">Todas</option>
            {tags.data!.map((tag) => (
              <option key={tag.concept_id} value={tag.concept_id}>
                {tag.label} ({tag.meetings})
              </option>
            ))}
          </select>
        </label>
      )}
      {chosen.length > 0 && (
        <div className="row bulk-actions" role="region" aria-label="Acciones sobre las reuniones seleccionadas">
          <span>
            {chosen.length === 1 ? "1 reunión seleccionada" : `${chosen.length} reuniones seleccionadas`}
          </span>
          {deleting ? (
            <span role="status">
              Borrando {deleting.done} de {deleting.total}…
            </span>
          ) : confirming ? (
            <>
              <span>Se borrarán con su audio, transcripción y memoria. No se puede deshacer.</span>
              <label>
                Para confirmar, ¿cuánto es {challenge[0]} + {challenge[1]}?{" "}
                <input
                  className="challenge"
                  inputMode="numeric"
                  autoComplete="off"
                  value={answer}
                  onChange={(event) => setAnswer(event.target.value.replace(/\D/g, ""))}
                />
              </label>
              <button
                type="button"
                className="danger"
                disabled={Number(answer) !== challenge[0] + challenge[1]}
                onClick={() => void deleteSelected()}
              >
                Confirmar borrado
              </button>
              <button type="button" onClick={() => setConfirming(false)}>
                Cancelar
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                className="danger"
                onClick={() => {
                  const pick = () => 2 + Math.floor(Math.random() * 8); // 2..9: easy, but deliberate
                  setChallenge([pick(), pick()]);
                  setAnswer("");
                  setConfirming(true);
                }}
              >
                Borrar seleccionadas
              </button>
              <button type="button" onClick={() => setSelected(new Set())}>
                Quitar selección
              </button>
            </>
          )}
        </div>
      )}
      {failures.length > 0 && (
        <div role="alert">
          <p>No se pudieron borrar:</p>
          <ul>
            {failures.map((failure) => (
              <li key={failure}>{failure}</li>
            ))}
          </ul>
        </div>
      )}
      {meetings.data && meetings.data.length > 0 && (
        <table className="meetings">
          <thead>
            <tr>
              <th className="select">
                <input
                  ref={allBox}
                  type="checkbox"
                  aria-label="Seleccionar todas las reuniones visibles"
                  checked={visible.length > 0 && chosen.length === visible.length}
                  disabled={deleting !== null}
                  onChange={toggleAll}
                />
              </th>
              <th>Título</th>
              <th>Estado</th>
              <th>Duración</th>
              <th>Idiomas</th>
              <th>Asistentes</th>
              <th>Etiquetas</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((meeting) => (
              <tr key={meeting.id} className={selected.has(meeting.id) ? "selected" : undefined}>
                <td className="select">
                  <input
                    type="checkbox"
                    aria-label={`Seleccionar ${meeting.title}`}
                    checked={selected.has(meeting.id)}
                    disabled={deleting !== null}
                    onChange={() => toggle(meeting.id)}
                  />
                </td>
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
