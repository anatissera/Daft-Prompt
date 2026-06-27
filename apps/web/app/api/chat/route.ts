// /api/chat — single hop per turn:
//   1) Ask the local LLM (OpenAI-compatible) to classify the message as music-
//      related or not, AND draft an off-topic reply if not. JSON output.
//   2) If music → forward to backend /chat (real intent routing + compose).
//      Else  → return the LLM's apology as a synthetic ChatResponse.
//
// Same-origin proxy, browser never holds backend or LLM URLs.

import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";
const LLM_BASE_URL = process.env.LLM_BASE_URL ?? "http://localhost:8080";
const LLM_MODEL = process.env.LLM_MODEL ?? "local";

const CLASSIFIER_TIMEOUT_MS = 8000;
const CLASSIFIER_SYSTEM = `/no_think You are the strict gatekeeper of a music-composition assistant.
The assistant can do ONLY three things:
  (a) compose a short MIDI song sketch (genres, instruments, tempo, key, etc.)
  (b) analyze an uploaded audio file (extract tempo/key/sections/chords)
  (c) answer musical questions about a reference the user already shared

Set "music": true ONLY if the user is asking the assistant to do (a), (b), or (c) directly.
Set "music": false for EVERYTHING else, even if the word "music" appears. Examples that are FALSE:
  - "code me an html page about music" (coding, not music task)
  - "tell me about Beethoven's life" (history/trivia, not composition/analysis)
  - "write lyrics" (text, not a MIDI sketch)
  - "what's a good Spotify playlist?" (recommendation, not a task we do)
  - any conversation, greeting, math, code, recipe, weather, etc.

Reply ONLY with a single JSON object, no prose, no markdown:
{"music": true} when in scope.
{"music": false, "reply": "<short friendly message in the user's language. Say you only handle music *tasks* and list the 3 things you can do (compose a sketch / analyze audio / answer about a reference). Tailor 1 example to what they asked for if relevant.>"} when out of scope.

Examples:
user: "hola" -> {"music": false, "reply": "¡Hola! Solo puedo (1) componer un sketch corto, (2) analizar un audio que subas, o (3) responder sobre una referencia ya cargada. Probá \\"componé un blues lento\\"."}
user: "compose a slow blues" -> {"music": true}
user: "what chords are in this track?" -> {"music": true}
user: "code me an html page about music" -> {"music": false, "reply": "I don't write code — I'm a music-composition assistant. I can (1) compose a short MIDI sketch, (2) analyze an audio file you upload, or (3) answer questions about a loaded reference."}
user: "what's the weather?" -> {"music": false, "reply": "I only handle music tasks: compose a sketch, analyze audio, or answer about a reference. Try \\"compose a funky bassline\\"."}`;

export async function POST(req: NextRequest) {
  const body = await req.json();
  const message = typeof body?.message === "string" ? body.message : "";
  const referenceId = body?.reference_id ?? null;

  // If a reference is loaded, skip the gate — those messages can be analysis Qs.
  if (!referenceId) {
    const verdict = await classify(message);
    // If the classifier failed/timed out, treat as off-topic by default — better
    // to ask the user to rephrase than to fire up a multi-minute compose run.
    if (!verdict) {
      return Response.json({
        intent: "off_topic",
        reply: "I couldn't classify your message and won't risk firing the composer. Try \"compose a slow blues\" or upload an audio file to analyze.",
        reference_id: null,
      });
    }
    if (verdict.music === false) {
      return Response.json({
        intent: "off_topic",
        reply: verdict.reply ?? "I only help with music. Try composing, analyzing audio, or asking about a reference.",
        reference_id: null,
      });
    }
  }

  try {
    const upstream = await fetch(`${API_BASE_URL}/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      signal: req.signal,
      body: JSON.stringify({ message, reference_id: referenceId }),
    });
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

interface Verdict { music: boolean; reply?: string }

async function classify(message: string): Promise<Verdict | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CLASSIFIER_TIMEOUT_MS);
  try {
    const res = await fetch(`${LLM_BASE_URL}/v1/chat/completions`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        model: LLM_MODEL,
        temperature: 0,
        max_tokens: 220,
        response_format: { type: "json_object" },
        chat_template_kwargs: { enable_thinking: false },
        messages: [
          { role: "system", content: CLASSIFIER_SYSTEM },
          { role: "user", content: message },
        ],
      }),
    });
    if (!res.ok) return null;
    const data = await res.json();
    const content: string | undefined = data?.choices?.[0]?.message?.content;
    if (!content) return null;
    const json = extractJson(content);
    if (!json) return null;
    const parsed = JSON.parse(json) as Partial<Verdict>;
    if (typeof parsed?.music !== "boolean") return null;
    return { music: parsed.music, reply: typeof parsed.reply === "string" ? parsed.reply : undefined };
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

function extractJson(text: string): string | null {
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start < 0 || end <= start) return null;
  return text.slice(start, end + 1);
}
