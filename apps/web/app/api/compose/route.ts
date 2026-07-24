// Server-side proxy so the browser never holds the backend URL directly and the
// /compose call is same-origin (no CORS). Artifact URLs in the response point at
// the backend, which the browser fetches directly (backend allows CORS).
//
// Relays the backend's SSE stream straight through as `upstream.body` — a
// ReadableStream — instead of buffering with `.text()`, so events reach the
// client as the negotiation progresses rather than all at once at the end.
import { NextRequest } from "next/server";

import { upstreamHeaders } from "@/lib/upstreamHeaders";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const upstream = await fetch(`${API_BASE_URL}/compose/stream`, {
    method: "POST",
    headers: upstreamHeaders({ "content-type": "application/json" }),
    body: JSON.stringify(body),
  });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "text/event-stream",
      "cache-control": "no-cache",
    },
  });
}
