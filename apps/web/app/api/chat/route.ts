// Server-side proxy to the backend's intent-routing /chat endpoint.
// Same-origin so the browser never holds the backend URL directly.
import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const upstream = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const text = await upstream.text();
  return new Response(text, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
    },
  });
}
