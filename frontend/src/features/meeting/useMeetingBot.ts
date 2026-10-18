import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { api, type BotSession, BOT_LIVE_STATUSES } from "../../api";

// Meeting bot (ADR 0026), with the same role as useAgentCapture: send the bot, follow its
// status and make it leave. The backend owns the lifecycle; the page only polls it. While the
// bot is in the call nothing streams to the browser: the audio arrives when it leaves.

const isLive = (bot: BotSession | null | undefined) =>
  Boolean(bot && (BOT_LIVE_STATUSES as readonly string[]).includes(bot.status));

export function useMeetingBot(meetingId: string, onChanged: () => void) {
  const queryClient = useQueryClient();
  const capabilities = useQuery({
    queryKey: ["meeting-bot-capabilities"],
    queryFn: api.botCapabilities,
    refetchInterval: 30_000,
  });
  const configured = Boolean(capabilities.data?.configured);
  const session = useQuery({
    queryKey: ["meeting-bot", meetingId],
    queryFn: () => api.getBot(meetingId),
    enabled: configured,
    // Every few seconds while the bot is in the call or its recording is being ingested.
    refetchInterval: (query) => (query.state.data?.active ? 3_000 : false),
  });

  const settle = (bot: BotSession) => {
    queryClient.setQueryData(["meeting-bot", meetingId], bot);
    onChanged();
  };
  const start = useMutation({ mutationFn: (meetUrl: string) => api.startBot(meetingId, meetUrl), onSuccess: settle });
  const stop = useMutation({ mutationFn: () => api.stopBot(meetingId), onSuccess: settle });

  const bot = session.data ?? null;
  // The meeting itself changes when the bot leaves (processing) or fails (scheduled again).
  const seen = useRef<string | null>(null);
  const changed = useRef(onChanged);
  changed.current = onChanged;
  useEffect(() => {
    if (!bot) return;
    if (seen.current !== null && seen.current !== bot.status) changed.current();
    seen.current = bot.status;
  }, [bot?.status]);

  return {
    capabilities: capabilities.data,
    bot,
    /** The bot owns the meeting: no other source may record it. */
    owns: Boolean(bot?.active),
    inCall: isLive(bot),
    start,
    stop,
  };
}
