// /api/title — asks the local LLM for a 2-5 word title for the conversation
// based on the user's first message. Reasoning disabled, tight token cap,
// JSON object output so we don't have to scrub markdown.

import { NextRequest } from "next/server";
import { Agent } from "undici";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

const LLM_BASE_URL = process.env.LLM_BASE_URL ?? "http://localhost:8080";
const LLM_MODEL = process.env.LLM_MODEL ?? "local";

const dispatcher = new Agent({ headersTimeout: 0, bodyTimeout: 0, connectTimeout: 5_000 });

const SYSTEM = `/no_think Pick a short title (2-5 words, Title Case, no quotes, no punctuation) that captures the user's request for a music sketch. Reply ONLY as JSON: {"title": "<title>"}. Examples:
user: "compose a slow blues in F minor" -> {"title": "Slow Blues in F Minor"}
user: "make me a flute song" -> {"title": "Solo Flute Sketch"}
user: "funky bassline 110 bpm" -> {"title": "Funky Bassline 110"}`;

export async function POST(req: NextRequest) {
  const body = await req.json();
  const message = typeof body?.message === "string" ? body.message : "";
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12_000);
  try {
    const res = await fetch(`${LLM_BASE_URL}/v1/chat/completions`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      signal: controller.signal,
      // @ts-expect-error undici-only field
      dispatcher,
      body: JSON.stringify({
        model: LLM_MODEL,
        temperature: 0.4,
        max_tokens: 60,
        response_format: { type: "json_object" },
        chat_template_kwargs: { enable_thinking: false },
        messages: [
          { role: "system", content: SYSTEM },
          { role: "user", content: message },
        ],
      }),
    });
    if (!res.ok) return Response.json({ title: null });
    const data = await res.json();
    const content: string | undefined = data?.choices?.[0]?.message?.content;
    if (!content) return Response.json({ title: null });
    const start = content.indexOf("{");
    const end = content.lastIndexOf("}");
    if (start < 0 || end <= start) return Response.json({ title: null });
    const parsed = JSON.parse(content.slice(start, end + 1));
    const title = typeof parsed?.title === "string" ? parsed.title.trim().slice(0, 60) : null;
    return Response.json({ title: title || null });
  } catch {
    return Response.json({ title: null });
  } finally {
    clearTimeout(timer);
  }
}
