// Server-side proxy so the browser never holds the backend URL directly and the
// /compose call is same-origin (no CORS). Artifact URLs in the response point at
// the backend, which the browser fetches directly (backend allows CORS).
import { NextRequest } from "next/server";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const upstream = await fetch(`${API_BASE_URL}/compose`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "content-type": "application/json" },
  });
}
