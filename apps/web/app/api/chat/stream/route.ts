// Same-origin SSE proxy so the browser sees a Next route (no CORS) while the
// backend streams the full lifecycle: classifier intent → compose events
// (director / agent_pass / convergence / done) or a single `reply` event for
// non-compose intents. Relays upstream.body as a ReadableStream so events reach
// the client as they happen instead of buffered at the end.

import { NextRequest } from "next/server";
import { Agent } from "undici";

import { upstreamHeaders } from "@/lib/upstreamHeaders";
import {
  INSTANCE_UNAVAILABLE_RETRY_DELAYS_MS,
  isRetryableInstanceUnavailable,
} from "@/lib/instanceUnavailable.mjs";

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

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) return reject(new DOMException("aborted", "AbortError"));
    const id = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(id);
      reject(new DOMException("aborted", "AbortError"));
    });
  });
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const requestInit = withDispatcher({
    method: "POST",
    headers: upstreamHeaders({ "content-type": "application/json" }),
    signal: req.signal,
    body: JSON.stringify(body),
  });

  try {
    for (let attempt = 0; ; attempt++) {
      const upstream = await fetch(`${API_BASE_URL}/chat/stream`, requestInit);
      if (!upstream.ok) {
        const text = await upstream.text();
        const retryable = isRetryableInstanceUnavailable(
          upstream.status,
          text,
          upstream.headers.get("content-type"),
        );
        if (retryable && attempt < INSTANCE_UNAVAILABLE_RETRY_DELAYS_MS.length) {
          await sleep(INSTANCE_UNAVAILABLE_RETRY_DELAYS_MS[attempt], req.signal);
          continue;
        }
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
    }
  } catch (err) {
    if (req.signal.aborted) {
      return new Response(null, { status: 499 });
    }
    const detail = err instanceof Error ? err.message : "unknown upstream error";
    return Response.json({ detail: `Backend unreachable: ${detail}` }, { status: 502 });
  }
}
