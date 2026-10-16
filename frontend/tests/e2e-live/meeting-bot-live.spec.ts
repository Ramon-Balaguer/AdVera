import { type APIRequestContext, expect, type Page, test } from "@playwright/test";

/*
 * Meeting bot against real calls (ADR 0026): AdVera sends the Vexa bot to a real Google Meet and
 * a real Microsoft Teams meeting, a person admits it and talks (and writes in the chat), the
 * test makes it leave and waits for the meeting to be `ready` with its transcript.
 *
 * It records real people, so it is skipped unless every participant agreed and
 * LIVE_CONSENT=yes is set. Run it against the stack started with the `bot` profile:
 *
 *   LIVE_CONSENT=yes ADVERA_LIVE_URL=http://localhost:15173 \
 *   LIVE_MEET_URL=https://meet.google.com/abc-defg-hij \
 *   LIVE_TEAMS_URL="https://teams.microsoft.com/meet/3812345678901?p=Ab12Cd" \
 *   npm run test:e2e:live
 *
 * LIVE_CALL_SECONDS     how long the bot stays in the call once admitted (default 60)
 * LIVE_ADMIT_SECONDS    how long to wait for the host to admit it (default 300)
 * LIVE_READY_SECONDS    how long the transcription may take (default 1200)
 * LIVE_EXPECT_NAMES=1   also require speakers named after the call (needs vexa_speaker_names)
 * LIVE_EXPECT_CHAT=1    also require chat messages (Vexa 0.12 keeps no Meet/Teams chat)
 */

const CONSENT = process.env.LIVE_CONSENT === "yes";
const CALL_SECONDS = Number(process.env.LIVE_CALL_SECONDS ?? 60);
const ADMIT_SECONDS = Number(process.env.LIVE_ADMIT_SECONDS ?? 300);
const READY_SECONDS = Number(process.env.LIVE_READY_SECONDS ?? 1200);

const CALLS = [
  { platform: "google_meet", name: "Google Meet", variable: "LIVE_MEET_URL", url: process.env.LIVE_MEET_URL },
  { platform: "teams", name: "Microsoft Teams", variable: "LIVE_TEAMS_URL", url: process.env.LIVE_TEAMS_URL },
] as const;

async function json(request: APIRequestContext, path: string) {
  const response = await request.get(path);
  return response.ok() ? response.json() : null;
}

async function botStatus(page: Page, meetingId: string): Promise<string> {
  const bot = await json(page.request, `/api/meetings/${meetingId}/bot`);
  return bot?.status ?? "none";
}

test.beforeAll(async ({ request }) => {
  test.skip(!CONSENT, "Records real people: set LIVE_CONSENT=yes once every participant agreed.");
  const capabilities = await json(request, "/api/meeting-bot/capabilities");
  expect(capabilities, "the AdVera API answers").not.toBeNull();
  expect(capabilities.configured, "Vexa is configured in Settings").toBe(true);
  expect(capabilities.available, "Vexa answers its health check").toBe(true);
});

for (const call of CALLS) {
  test(`the bot records a real ${call.name} call until the meeting is ready`, async ({ page }) => {
    test.skip(!CONSENT, "LIVE_CONSENT=yes is required");
    test.skip(!call.url, `set ${call.variable}`);

    const created = await page.request.post("/api/meetings", {
      data: { title: `Live E2E ${call.name} ${new Date().toISOString().slice(0, 16)}` },
    });
    expect(created.status()).toBe(201);
    const meetingId: string = (await created.json()).id;

    await page.goto(`/meetings/${meetingId}`);
    await page.getByTestId("bot-send").click();
    await page.getByTestId("bot-url").fill(call.url!);
    await page.getByTestId("bot-confirm").click();
    await expect(page.getByTestId("bot-state")).toContainText(call.name);

    const sent = await json(page.request, `/api/meetings/${meetingId}/bot`);
    console.log(`[live] admit "${sent.bot_name}" in ${call.name}`);
    await expect
      .poll(() => botStatus(page, meetingId), { timeout: ADMIT_SECONDS * 1000, intervals: [3000] })
      .toBe("active");
    console.log(`[live] in the call: talk (and write in the chat) for ${CALL_SECONDS} s`);
    await page.waitForTimeout(CALL_SECONDS * 1000);

    await page.getByTestId("bot-leave").click();
    await expect
      .poll(async () => (await json(page.request, `/api/meetings/${meetingId}`))?.status, {
        timeout: READY_SECONDS * 1000,
        intervals: [5000],
      })
      .toBe("ready");

    const bot = await json(page.request, `/api/meetings/${meetingId}/bot`);
    expect(bot.status).toBe("completed");
    expect(bot.platform).toBe(call.platform);
    const meeting = await json(page.request, `/api/meetings/${meetingId}`);
    expect(meeting.tracks).toEqual(["system"]);
    expect(meeting.duration).toBeGreaterThan(CALL_SECONDS / 2);
    const transcript = await json(page.request, `/api/meetings/${meetingId}/transcript`);
    expect(transcript.segments.length, "AdVera transcribed the call").toBeGreaterThan(0);

    if (process.env.LIVE_EXPECT_NAMES === "1") {
      const named = transcript.segments.filter((segment: { person: string | null }) => segment.person);
      expect(named.length, "speakers named after the people in the call").toBeGreaterThan(0);
    }
    if (process.env.LIVE_EXPECT_CHAT === "1") {
      const chat = await json(page.request, `/api/meetings/${meetingId}/chat`);
      expect(chat.length, "the call's chat was kept").toBeGreaterThan(0);
    }

    // The page shows the finished meeting: no bot controls left.
    await page.reload();
    await expect(page.getByTestId("bot-state")).toHaveCount(0);
  });
}
