import { autocompletion, type Completion, type CompletionContext, type CompletionResult } from "@codemirror/autocomplete";
import { markdown, markdownLanguage } from "@codemirror/lang-markdown";
import { HighlightStyle, syntaxHighlighting, syntaxTree } from "@codemirror/language";
import { type Extension, RangeSetBuilder, StateEffect, StateField } from "@codemirror/state";
import {
  Decoration,
  type DecorationSet,
  EditorView,
  ViewPlugin,
  type ViewUpdate,
  WidgetType,
} from "@codemirror/view";
import { tags } from "@lezer/highlight";

import { referenceMarkdown } from "./blocks";

// Notes editor (ADR 0020): one Markdown editor that shows the formatting as you type — a
// heading is big, bold is bold — while the Markdown signs stay visible in grey. When the
// editor is not being edited (after saving, or on leaving it) the signs are hidden and the
// text reads clean; they come back on editing. The stored text is always plain Markdown.

const style = HighlightStyle.define([
  { tag: tags.heading1, fontSize: "1.6em", fontWeight: "700" },
  { tag: tags.heading2, fontSize: "1.35em", fontWeight: "700" },
  { tag: tags.heading3, fontSize: "1.15em", fontWeight: "700" },
  { tag: [tags.heading4, tags.heading5, tags.heading6], fontWeight: "700" },
  { tag: tags.strong, fontWeight: "700" },
  { tag: tags.emphasis, fontStyle: "italic" },
  { tag: tags.strikethrough, textDecoration: "line-through" },
  { tag: tags.monospace, fontFamily: "ui-monospace, monospace" },
  { tag: tags.quote, fontStyle: "italic" },
  { tag: [tags.processingInstruction, tags.meta], color: "#9ca3af" }, // the Markdown signs
]);

// Whether the editor is being edited: the signs are hidden while it is not.
const setEditing = StateEffect.define<boolean>();
const editingField = StateField.define<boolean>({
  create: () => false,
  update: (value, transaction) => {
    for (const effect of transaction.effects) if (effect.is(setEditing)) return effect.value;
    return value;
  },
});

const HIDDEN_MARKS = new Set(["HeaderMark", "EmphasisMark", "StrikethroughMark", "CodeMark"]);
const REFERENCE_ONE =
  /^\[@([^\]\n]{1,200})\]\(\/meetings\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:\?segment=([A-Za-z0-9_-]{1,50}))?\)$/;

export interface ReferenceHost {
  /** Known meetings by id (title), to show a reference to a deleted meeting as broken. */
  titles: () => Map<string, string> | null;
  open: (href: string) => void;
}

class ReferenceChip extends WidgetType {
  constructor(
    readonly label: string,
    readonly href: string,
    readonly broken: boolean,
    readonly host: ReferenceHost,
  ) {
    super();
  }
  eq(other: ReferenceChip) {
    return other.label === this.label && other.href === this.href && other.broken === this.broken;
  }
  toDOM() {
    const chip = document.createElement("a");
    chip.className = this.broken ? "note-ref broken" : "note-ref";
    chip.href = this.href;
    chip.textContent = this.broken ? `@${this.label} (reunión borrada)` : `@${this.label}`;
    chip.setAttribute("data-testid", "note-reference");
    chip.addEventListener("mousedown", (event) => {
      event.preventDefault();
      if (!this.broken) this.host.open(this.href);
    });
    return chip;
  }
  ignoreEvent() {
    return false;
  }
}

function decorations(view: EditorView, host: ReferenceHost): DecorationSet {
  const editing = view.state.field(editingField);
  const known = host.titles();
  const builder = new RangeSetBuilder<Decoration>();
  for (const { from, to } of view.visibleRanges) {
    syntaxTree(view.state).iterate({
      from,
      to,
      enter: (node) => {
        if (node.name === "Link") {
          const text = view.state.sliceDoc(node.from, node.to);
          const match = REFERENCE_ONE.exec(text);
          if (match) {
            const href = text.slice(text.indexOf("](") + 2, -1);
            const broken = known !== null && !known.has(match[2]);
            builder.add(
              node.from,
              node.to,
              Decoration.replace({ widget: new ReferenceChip(match[1], href, broken, host) }),
            );
            return false;
          }
        }
        if (!editing && HIDDEN_MARKS.has(node.name)) {
          let end = node.to;
          // "# Title": the space after the heading sign goes with it.
          if (node.name === "HeaderMark" && view.state.sliceDoc(end, end + 1) === " ") end += 1;
          if (end > node.from) builder.add(node.from, end, Decoration.replace({}));
        }
        return undefined;
      },
    });
  }
  return builder.finish();
}

function referencePlugin(host: ReferenceHost) {
  return ViewPlugin.fromClass(
    class {
      decorations: DecorationSet;
      constructor(view: EditorView) {
        this.decorations = decorations(view, host);
      }
      update(update: ViewUpdate) {
        const toggled = update.transactions.some((t) => t.effects.some((e) => e.is(setEditing)));
        if (update.docChanged || update.viewportChanged || toggled || update.selectionSet) {
          this.decorations = decorations(update.view, host);
        }
      }
    },
    {
      decorations: (plugin) => plugin.decorations,
      // A reference is one unit: the cursor jumps over it and Backspace deletes it whole.
      provide: (plugin) =>
        EditorView.atomicRanges.of((view) => view.plugin(plugin)?.decorations ?? Decoration.none),
    },
  );
}

export interface MeetingOption {
  id: string;
  title: string;
}
export interface SegmentOption {
  id: string;
  index: number;
  start: number;
  who: string;
  text: string;
}
export interface ReferenceSources {
  meetings: () => MeetingOption[];
  segments: (meetingId: string) => Promise<SegmentOption[]>;
}

export function plainKey(text: string) {
  return text
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

function clock(seconds: number) {
  const total = Math.floor(seconds);
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, "0")}`;
}

// "@guillem" offers meetings; right after a meeting reference, ":14" or ":copias" offers its
// segments (by number, time or words), and choosing one turns it into a segment reference.
function referenceCompletions(sources: ReferenceSources) {
  return async (context: CompletionContext): Promise<CompletionResult | null> => {
    // ":" must be followed directly by what to look for (":14", ":copias"): "…Guillem: we
    // decided" is prose, and an empty query lists nothing that Enter could take.
    const segmentAt = context.matchBefore(
      /\[@[^\]\n]{1,200}\]\(\/meetings\/[0-9a-f-]{36}\):[^\s\n][^\n]{0,59}$/,
    );
    if (segmentAt) {
      const [, label, meetingId, query] =
        /^\[@([^\]\n]+)\]\(\/meetings\/([0-9a-f-]{36})\):(.*)$/.exec(segmentAt.text) ?? [];
      if (!meetingId) return null;
      const wanted = plainKey(query.trim());
      const options = (await sources.segments(meetingId))
        .filter(
          (s) =>
            !wanted ||
            String(s.index).startsWith(wanted.replace(/^seg\s*/, "")) ||
            clock(s.start).startsWith(wanted) ||
            plainKey(`${s.who} ${s.text}`).includes(wanted),
        )
        .slice(0, 40)
        .map<Completion>((s) => ({
          label: `#${s.index} · ${clock(s.start)} · ${s.who}`,
          detail: s.text.length > 70 ? `${s.text.slice(0, 69)}…` : s.text,
          apply: referenceMarkdown(`${label} · ${clock(s.start)}`, meetingId, s.id),
        }));
      return { from: segmentAt.from, to: context.pos, options, filter: false };
    }
    const meetingAt = context.matchBefore(/@[^\s@[\]()]{0,40}(?: [^\s@[\]()]{1,40}){0,4}$/);
    if (!meetingAt) return null;
    const before = meetingAt.from === 0 ? "" : context.state.sliceDoc(meetingAt.from - 1, meetingAt.from);
    if (before && !/\s|\(/.test(before)) return null; // an e-mail, not a reference
    const wanted = plainKey(meetingAt.text.slice(1).trim());
    const options = sources
      .meetings()
      .filter((m) => !wanted || plainKey(m.title).includes(wanted))
      .slice(0, 30)
      .map<Completion>((m) => ({
        label: m.title,
        detail: "reunión",
        apply: referenceMarkdown(m.title, m.id),
      }));
    if (!options.length) return null;
    return { from: meetingAt.from, to: context.pos, options, filter: false };
  };
}

export function notesExtensions(host: ReferenceHost, sources: ReferenceSources): Extension[] {
  return [
    markdown({ base: markdownLanguage }),
    syntaxHighlighting(style),
    editingField,
    EditorView.focusChangeEffect.of((_state, focusing) => setEditing.of(focusing)),
    referencePlugin(host),
    autocompletion({ override: [referenceCompletions(sources)], activateOnTyping: true, icons: false }),
    EditorView.lineWrapping,
  ];
}

/** Wrap the selection with a Markdown sign (bold, italic, strike) or prefix its lines. */
export function format(view: EditorView, kind: "h1" | "bold" | "italic" | "strike" | "list") {
  const { from, to } = view.state.selection.main;
  if (kind === "h1" || kind === "list") {
    const line = view.state.doc.lineAt(from);
    const prefix = kind === "h1" ? "# " : "- ";
    const has = line.text.startsWith(prefix);
    view.dispatch({
      changes: has
        ? { from: line.from, to: line.from + prefix.length, insert: "" }
        : { from: line.from, insert: prefix },
    });
  } else {
    const sign = kind === "bold" ? "**" : kind === "italic" ? "*" : "~~";
    view.dispatch({
      changes: [
        { from, insert: sign },
        { from: to, insert: sign },
      ],
      selection: { anchor: from + sign.length, head: to + sign.length },
    });
  }
  view.focus();
}
