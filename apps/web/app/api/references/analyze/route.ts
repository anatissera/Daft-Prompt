// Development fallback for audio analysis. In production the browser posts
// straight to the backend (see lib/apiBase.mjs): a serverless function caps
// request bodies at 4.5 MB — 25 seconds of WAV — and caps its own duration
// below what CPU stem separation takes, so neither limit survives a real
// upload.
//
// Kept because it means `npm run dev` needs no NEXT_PUBLIC_API_BASE_URL and no
// CORS configuration on the backend.

import { NextRequest } from "next/server";
import { Agent } from "undici";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

// Analysis streams progress events, but Demucs can go quiet between them for
// longer than undici's default body timeout. Same dispatcher the chat stream
// route uses.
const noTimeoutDispatcher = new Agent({
  headersTimeout: 0,
  bodyTimeout: 0,
  connectTimeout: 10_000,
});

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  const formData = await req.formData();
  try {
    const upstream = await fetch(`${API_BASE_URL}/references/analyze/stream`, {
      method: "POST",
      body: formData,
      signal: req.signal,
      dispatcher: noTimeoutDispatcher,
    } as RequestInit);

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
