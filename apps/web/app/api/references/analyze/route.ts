import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  const formData = await req.formData();
  const upstream = await fetch(`${API_BASE_URL}/references/analyze/stream`, {
    method: "POST",
    body: formData,
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "text/event-stream",
      "cache-control": "no-cache",
    },
  });
}
