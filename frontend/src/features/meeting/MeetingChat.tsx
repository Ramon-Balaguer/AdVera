import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api";
import { formatTimestamp } from "../../format";

/**
 * The chat of a call the meeting bot attended (ADR 0027). Like the notes, it is an annex of
 * the transcript: Summary and Brain cite its messages by id (`chat-001`), and a cited message
 * is highlighted here.
 */
export function MeetingChat({ meetingId, focus }: { meetingId: string; focus?: string | null }) {
  const { t } = useTranslation();
  const chat = useQuery({ queryKey: ["chat", meetingId], queryFn: () => api.getChat(meetingId) });

  useEffect(() => {
    if (focus) document.getElementById(`chat-${meetingId}-${focus}`)?.scrollIntoView({ block: "center" });
  }, [focus, meetingId, chat.data]);

  if (chat.isPending) return <p>{t("common.loading")}</p>;
  if (chat.isError) return <p role="alert">{t("meeting.chat.loadError")}</p>;
  if (chat.data.length === 0) return <p className="hint">{t("meeting.chat.empty")}</p>;
  return (
    <ol className="chat" aria-label={t("meeting.chat.region")}>
      {chat.data.map((message) => (
        <li
          key={message.id}
          id={`chat-${meetingId}-${message.id}`}
          className={message.id === focus ? "chat-message focused" : "chat-message"}
          data-testid="chat-message"
        >
          <span className="time">{message.offset_s === null ? "—" : formatTimestamp(message.offset_s)}</span>{" "}
          <strong>{message.sender}</strong>: {message.text}
        </li>
      ))}
    </ol>
  );
}
