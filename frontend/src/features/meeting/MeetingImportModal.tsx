import { type DragEvent, useRef, useState } from "react";

import { ApiError, describeError, uploadMedia } from "../../api";

type Phase =
  | { kind: "idle" }
  | { kind: "uploading"; fraction: number }
  | { kind: "extracting" }
  | { kind: "error"; code: string };

const ACCEPT = "audio/*,video/*,.wav,.mp3,.m4a,.aac,.ogg,.oga,.opus,.flac,.wma,.mp4,.mov,.mkv,.avi,.m4v,.webm";

// meeting-media-import.md: one file, picker or drag-and-drop, upload then extraction states.
export function MeetingImportModal({
  meetingId,
  onClose,
  onImported,
}: {
  meetingId: string;
  onClose: () => void;
  onImported: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const busy = phase.kind === "uploading" || phase.kind === "extracting";

  const start = async () => {
    if (!file) return;
    setPhase({ kind: "uploading", fraction: 0 });
    try {
      await uploadMedia(meetingId, file, (fraction) =>
        setPhase(fraction >= 1 ? { kind: "extracting" } : { kind: "uploading", fraction }),
      );
      onImported();
    } catch (error) {
      setPhase({ kind: "error", code: error instanceof ApiError ? error.code : "NETWORK_ERROR" });
    }
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    if (busy) return;
    const dropped = event.dataTransfer.files[0];
    if (dropped) {
      setFile(dropped);
      setPhase({ kind: "idle" });
    }
  };

  return (
    <div className="modal-backdrop">
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="import-title">
        <h2 id="import-title">Importar audio o vídeo</h2>
        <div
          className={`dropzone${dragging ? " dragging" : ""}`}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <p>{file ? file.name : "Arrastra aquí un archivo o selecciónalo."}</p>
          <button type="button" disabled={busy} onClick={() => inputRef.current?.click()}>
            Seleccionar archivo
          </button>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            hidden
            data-testid="import-file"
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setPhase({ kind: "idle" });
            }}
          />
        </div>

        <div role="status" aria-live="polite">
          {phase.kind === "uploading" && (
            <>
              <p>Subiendo… {Math.round(phase.fraction * 100)} %</p>
              <progress value={phase.fraction} max={1} />
            </>
          )}
          {phase.kind === "extracting" && <p>Extrayendo y verificando el audio…</p>}
        </div>
        {phase.kind === "error" && <p role="alert">{describeError(phase.code)}</p>}

        <div className="row end">
          <button type="button" onClick={onClose} disabled={busy}>
            Cancelar
          </button>
          <button type="button" onClick={start} disabled={!file || busy}>
            {phase.kind === "error" ? "Reintentar" : "Importar"}
          </button>
        </div>
      </div>
    </div>
  );
}
