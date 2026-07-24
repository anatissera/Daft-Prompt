// /api/chat — same-origin proxy to the backend /chat. Intent classification
// (including off-topic refusal) lives in the backend graph's director node, so
// this route just forwards the turn; the browser never holds the backend URL.

import { NextRequest } from "next/server";
import { Agent } from "undici";

import { upstreamHeaders } from "@/lib/upstreamHeaders";

export const dynamic = "force-dynamic";
// Vercel Hobby caps serverless maxDuration at 300s; a real compose runs ~85s so
// this is ample. (A value >300 makes the Vercel deploy fail to build.)
export const maxDuration = 300;

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
      headers: upstreamHeaders({ "content-type": "application/json" }),
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
