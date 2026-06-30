// /api/chat — same-origin proxy to the backend /chat. Intent classification
// (including off-topic refusal) lives in the backend graph's director node, so
// this route just forwards the turn; the browser never holds the backend URL.

import { NextRequest } from "next/server";
import { Agent } from "undici";

export const dynamic = "force-dynamic";
export const maxDuration = 1800; // 30 min cap for the Next route itself

// undici's default headersTimeout (5 min) kills slow LLM composes — disable.
// Connect timeout stays sensible so a dead backend fails fast.
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
  const message = typeof body?.message === "string" ? body.message : "";
  const referenceId = body?.reference_id ?? null;

  try {
    const upstream = await fetch(`${API_BASE_URL}/chat`, withDispatcher({
      method: "POST",
      headers: { "content-type": "application/json" },
      signal: req.signal,
      body: JSON.stringify({ message, reference_id: referenceId }),
    }));
    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch (err) {
    if (req.signal.aborted) {
      return Response.json({ intent: "off_topic", reply: "(cancelled)" }, { status: 499 });
    }
    const detail = err instanceof Error ? err.message : "unknown upstream error";
    return Response.json(
      { detail: `Backend unreachable: ${detail}` },
      { status: 502 },
    );
  }
}
