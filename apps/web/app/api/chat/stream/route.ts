// Same-origin SSE proxy so the browser sees a Next route (no CORS) while the
// backend streams the full lifecycle: classifier intent → compose events
// (director / agent_pass / convergence / done) or a single `reply` event for
// non-compose intents. Relays upstream.body as a ReadableStream so events reach
// the client as they happen instead of buffered at the end.

import { NextRequest } from "next/server";
import { Agent } from "undici";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

// Local Qwen composes can run for many minutes; don't let undici's default
// header/body timeouts cut the stream short.
const noTimeoutDispatcher = new Agent({
  headersTimeout: 0,
  bodyTimeout: 0,
  connectTimeout: 10_000,
});

function withDispatcher<T extends RequestInit>(init: T): T {
  return { ...init, dispatcher: noTimeoutDispatcher } as unknown as T;
}

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  const body = await req.json();
  try {
    const upstream = await fetch(
      `${API_BASE_URL}/chat/stream`,
      withDispatcher({
        method: "POST",
        headers: { "content-type": "application/json" },
        signal: req.signal,
        body: JSON.stringify(body),
      }),
    );
    if (!upstream.ok) {
      const text = await upstream.text();
      return new Response(text || JSON.stringify({ detail: `backend error ${upstream.status}` }), {
        status: upstream.status,
        headers: {
          "content-type": upstream.headers.get("content-type") ?? "application/json",
          "cache-control": "no-cache",
        },
      });
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "content-type": upstream.headers.get("content-type") ?? "text/event-stream",
        "cache-control": "no-cache",
      },
    });
  } catch (err) {
    if (req.signal.aborted) {
      return new Response(null, { status: 499 });
    }
    const detail = err instanceof Error ? err.message : "unknown upstream error";
    return Response.json({ detail: `Backend unreachable: ${detail}` }, { status: 502 });
  }
}
