import { useQuery, useQueryClient } from "@tanstack/react-query";
import { EditorSelection } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import CodeMirror, { type ReactCodeMirrorRef } from "@uiw/react-codemirror";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api, ApiError, describeError } from "../../api";
import i18n from "../../i18n";
import { noteBlocks } from "../notes/blocks";
import { format, notesExtensions, type SegmentOption } from "../notes/editor";

const ANALYSIS = ["queued", "waiting_transcript", "llm_not_configured", "unchanged"] as const;
const analysisMessage = (analysis: string | null | undefined) =>
  i18n.t(`analysis.${(ANALYSIS as readonly string[]).includes(analysis ?? "") ? (analysis as (typeof ANALYSIS)[number]) : "unchanged"}`);

const draftKey = (meetingId: string) => `advera.notes.${meetingId}`;

function readDraft(meetingId: string): string | null {
  try {
    return window.localStorage.getItem(draftKey(meetingId));
  } catch {
    return null;
  }
}

/** Forget the unsaved notes of a meeting that was deleted. */
export function clearNotesDraft(meetingId: string) {
  writeDraft(meetingId, null);
}

function writeDraft(meetingId: string, content: string | null) {
  try {
    if (content === null) window.localStorage.removeItem(draftKey(meetingId));
    else window.localStorage.setItem(draftKey(meetingId), content);
  } catch {
    // The browser may refuse storage; the notes are still saved with the button.
  }
}

// Notes taken during or after the meeting (ADR 0020). They are saved with the button, which
// queues the text analysis again; an unsaved draft survives a reload in this browser.
export function MeetingNotes({ meetingId, focusBlock }: { meetingId: string; focusBlock: string | null }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const editor = useRef<ReactCodeMirrorRef>(null);
  const notes = useQuery({ queryKey: ["notes", meetingId], queryFn: () => api.getNotes(meetingId) });
  const meetings = useQuery({ queryKey: ["meetings"], queryFn: api.listMeetings });
  const [content, setContent] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const saved = notes.data?.content ?? "";
  const value = content ?? saved;
  const dirty = content !== null && content !== saved;
  const latest = useRef(value);
  latest.current = value;

  // A draft left unsaved in this browser comes back after a reload (once, on first load:
  // a later refetch must not re-apply it).
  const draftChecked = useRef(false);
  useEffect(() => {
    if (!notes.data || draftChecked.current) return;
    draftChecked.current = true;
    const draft = readDraft(meetingId);
    if (draft !== null && draft !== notes.data.content) {
      setContent(draft);
      setStatus(i18n.t("notes.draftRecovered"));
    }
  }, [notes.data, meetingId]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  // Data for @references, read through refs so the editor extensions are built once.
  const titles = useRef<Map<string, string> | null>(null);
  titles.current = meetings.data ? new Map(meetings.data.map((m) => [m.id, m.title])) : null;
  const others = useRef<{ id: string; title: string }[]>([]);
  others.current = (meetings.data ?? []).filter((m) => m.id !== meetingId).map((m) => ({ id: m.id, title: m.title }));
  const extensions = useMemo(
    () =>
      notesExtensions(
        { titles: () => titles.current, open: (href) => navigate(href) },
        {
          meetings: () => others.current,
          segments: async (id): Promise<SegmentOption[]> => {
            const transcript = await queryClient.fetchQuery({
              queryKey: ["transcript", id],
              queryFn: () => api.getTranscript(id),
              staleTime: 60_000,
            });
            return (transcript?.segments ?? []).map((segment, index) => ({
              id: segment.id,
              index: index + 1,
              start: segment.start,
              who: segment.person ?? segment.speaker ?? "?",
              text: segment.text,
            }));
          },
        },
      ),
    [navigate, queryClient],
  );

  // /meetings/{id}?note=note-003 (a cited note) selects that block and brings it into view.
  useEffect(() => {
    const view = editor.current?.view;
    if (!focusBlock || !view || !notes.data) return;
    const block = noteBlocks(view.state.doc.toString()).find((item) => item.id === focusBlock);
    if (!block) return;
    view.dispatch({
      selection: EditorSelection.range(block.from, block.to),
      effects: EditorView.scrollIntoView(block.from, { y: "center" }),
    });
    document.getElementById("notes")?.scrollIntoView({ block: "start" });
  }, [focusBlock, notes.data]);

  const save = async () => {
    setSaving(true);
    setError(null);
    const sent = value;
    try {
      const result = await api.saveNotes(meetingId, sent);
      queryClient.setQueryData(["notes", meetingId], result);
      setStatus(analysisMessage(result.analysis));
      if (latest.current === sent) {
        setContent(null);
        writeDraft(meetingId, null);
        editor.current?.view?.contentDOM.blur(); // signs hidden: the notes read clean
      }
      // Otherwise the user kept typing while saving: that text stays, unsaved, with its draft.
      void queryClient.invalidateQueries({ queryKey: ["brain", meetingId] });
    } catch (failure) {
      setError(describeError(failure instanceof ApiError ? failure.code : null));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="notes" id="notes" aria-label={t("notes.title")}>
      <div className="row notes-heading">
        <h2>{t("notes.title")}</h2>
        <div className="notes-toolbar" role="toolbar" aria-label={t("notes.format")}>
          {(
            [
              ["h1", t("notes.heading"), "H"],
              ["bold", t("notes.bold"), "B"],
              ["italic", t("notes.italic"), "I"],
              ["strike", t("notes.strike"), "S"],
              ["list", t("notes.list"), "•"],
            ] as const
          ).map(([kind, label, glyph]) => (
            <button
              key={kind}
              type="button"
              aria-label={label}
              title={label}
              className={`format-${kind}`}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => editor.current?.view && format(editor.current.view, kind)}
            >
              {glyph}
            </button>
          ))}
        </div>
        <button type="button" onClick={() => void save()} disabled={!dirty || saving}>
          {saving ? t("common.saving") : t("common.save")}
        </button>
      </div>
      {notes.isPending ? (
        <p role="status">{t("notes.loading")}</p>
      ) : notes.isError ? (
        <p role="alert">{t("notes.loadError")}</p>
      ) : (
        <div data-testid="notes-editor" className="notes-editor">
          <CodeMirror
            ref={editor}
            value={value}
            extensions={extensions}
            basicSetup={{ lineNumbers: false, foldGutter: false, highlightActiveLine: false }}
            placeholder={t("notes.placeholder")}
            onChange={(next) => {
              setContent(next);
              writeDraft(meetingId, next);
              setStatus(null);
            }}
            aria-label={t("notes.editorLabel")}
          />
        </div>
      )}
      {dirty && <p className="hint">{t("notes.unsaved")}</p>}
      {status && <p role="status">{status}</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
