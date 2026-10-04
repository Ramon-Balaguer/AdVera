import { z } from "zod";

const frameSchema = z.object({ type: z.string() }).passthrough();
export type Frame = z.infer<typeof frameSchema> & Record<string, any>;

/** A WebSocket text frame as an object with a `type`, or null when it is anything else.
 * A malformed frame is ignored (and logged) instead of throwing inside `onmessage`. */
export function parseFrame(data: unknown): Frame | null {
  try {
    const parsed = frameSchema.safeParse(JSON.parse(String(data)));
    if (parsed.success) return parsed.data as Frame;
  } catch {
    // not JSON: handled below like any other unusable frame
  }
  console.warn("Ignoring a WebSocket frame that is not a typed JSON object");
  return null;
}
