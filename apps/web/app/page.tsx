"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import ChatComposer from "@/components/ChatComposer";
import ChatThread from "@/components/ChatThread";
import type { ChatMessage } from "@/lib/chatTypes";
import type { ArtistStyleProfile, ChordChartRow, MelodyProfile, ReferenceProfile, SongState, TabExcerpt } from "@/lib/types";
import {
  buildChatRequestPayload,
  buildConversationContext,
  chooseChatAction,
  createCompositionMessage,
  createChordMessage,
  createMelodyMessage,
  createTabMessage,
  createTextMessage,
  referenceMemoryFromChatResponse,
} from "@/lib/chatActionAdapter.mjs";
import { deriveSessionTitle } from "@/lib/sessionTitle.mjs";
import { classifyChatWorkflow, workflowBusyLabel, type ChatWorkflow } from "@/lib/workflowProgress.mjs";

type Intent = "answer_reference" | "compose" | "compose_from_reference" | "artist_style" | "clarify" | "off_topic";

interface UsageInfo {
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  calls?: number;
  elapsed_seconds?: number;
}

interface ChatArtifacts {
  midi: string;
  musicxml: string;
}

interface ChatComposeResult {
  song: SongState;
  source: string;
  artifacts?: ChatArtifacts | null;
  reference_transfer_intent?: Record<string, unknown> | null;
  instrument_requests_summary?: Record<string, unknown>[];
  literal_applications?: Record<string, unknown>[];
  uncertainty_notes?: string[];
  warnings?: string[];
}

interface ChatResponse {
  intent: Intent;
  reply: string;
  reference_id?: string | null;
  reference_label?: string | null;
  answer?: { answer: string; confidence?: string } | null;
  tab_excerpt?: TabExcerpt | null;
  chord_chart?: ChordChartRow[];
  melody_preview?: MelodyProfile | null;
  compose?: ChatComposeResult | null;
  artist_style_profiles?: ArtistStyleProfile[];
  clarification?: string | null;
  usage?: UsageInfo | null;
  error?: { message?: string; code?: string; provider?: string | null; model?: string | null } | null;
  diagnostics?: Record<string, unknown>;
}

export default function Home() {
  const messageIndexRef = useRef(1);
  const [prompt, setPrompt] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([
    createTextMessage(
      "assistant",
      "Daft Prompt — multi-agent music studio. Ask me about a song, request playable tabs or keys, build an artist style profile, or compose a MIDI sketch.",
      0,
    ),
  ]);
  const [referenceProfile, setReferenceProfile] = useState<ReferenceProfile | null>(null);
  const [activeReference, setActiveReference] = useState<{ referenceId: string; label: string } | null>(null);
  const [currentSong, setCurrentSong] = useState<SongState | null>(null);
  const [artistStyleProfiles, setArtistStyleProfiles] = useState<ArtistStyleProfile[]>([]);
  const [activeWork, setActiveWork] = useState<string | null>(null);
  const [activeWorkflow, setActiveWorkflow] = useState<ChatWorkflow | null>(null);
  const [busyStartedAt, setBusyStartedAt] = useState<number | null>(null);
  const [busyElapsedMs, setBusyElapsedMs] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [sessionTitle, setSessionTitle] = useState<string>("Untitled session");
  const [buildIds, setBuildIds] = useState<{ frontend: string; backend: string } | null>(null);
  const sessionTitledRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  function maybeTitleSession(firstUserMessage: string) {
    if (sessionTitledRef.current) return;
    sessionTitledRef.current = true;
    const title = deriveSessionTitle(firstUserMessage);
    if (title) setSessionTitle(title);
  }

  const busy = activeWork !== null;

  useEffect(() => {
    if (busyStartedAt === null) {
      setBusyElapsedMs(0);
      return;
    }
    const id = setInterval(() => setBusyElapsedMs(performance.now() - busyStartedAt), 100);
    return () => clearInterval(id);
  }, [busyStartedAt]);

  useEffect(() => {
    if (process.env.NODE_ENV === "production") return;
    fetch("/api/build", { cache: "no-store" })
      .then((response) => response.json())
      .then((value: { frontend?: string; backend?: string }) => {
        if (value.frontend && value.backend) setBuildIds({ frontend: value.frontend, backend: value.backend });
      })
      .catch(() => undefined);
  }, []);

  function startWork(label: string, workflow: ChatWorkflow | null = null) {
    setActiveWork(label);
    setActiveWorkflow(workflow);
    setBusyStartedAt(performance.now());
  }

  function stopWork() {
    setActiveWork(null);
    setActiveWorkflow(null);
    setBusyStartedAt(null);
    abortRef.current = null;
  }

  function cancelWork() {
    if (abortRef.current) abortRef.current.abort();
    appendMessage(createTextMessage("assistant", "(cancelled)", nextMessageIndex()));
    stopWork();
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;

    const action = chooseChatAction({
      prompt,
    });

    appendMessage(createTextMessage("user", action.messageText, nextMessageIndex()));
    setPrompt("");
    setError(null);

    await chat(action.messageText);
  }

  async function chat(message: string) {
    const workflow = classifyChatWorkflow(message, { hasCurrentSong: currentSong !== null });
    startWork(workflowBusyLabel(workflow), workflow);
    const controller = new AbortController();
    abortRef.current = controller;
    const startedAt = performance.now();
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify(buildChatRequestPayload({
          message,
          activeReferenceId: activeReference?.referenceId ?? referenceProfile?.reference_id ?? null,
          currentSong,
          conversationContext: buildConversationContext(messages),
          artistStyleProfiles,
        })),
      });
      if (!res.ok) throw new Error(await readApiError(res));
      const data = (await res.json()) as ChatResponse;
      if (process.env.NODE_ENV !== "production" && data.diagnostics) {
        console.info("[chat-audit]", JSON.stringify(data.diagnostics));
      }
      const meta = formatMeta(data, performance.now() - startedAt);
      const idx = nextMessageIndex();
      // Title the session from the first user message (client-side, no LLM).
      maybeTitleSession(message);
      const rememberedReference = referenceMemoryFromChatResponse(data, message);
      if (rememberedReference) setActiveReference(rememberedReference);
      if (data.artist_style_profiles?.length) setArtistStyleProfiles(data.artist_style_profiles);
      if (data.tab_excerpt) {
        appendMessage({ ...createTabMessage("assistant", data.reply, data.tab_excerpt, idx), meta });
      } else if (data.melody_preview) {
        appendMessage({ ...createMelodyMessage("assistant", data.reply, data.melody_preview, idx), meta });
      } else if (data.chord_chart?.length) {
        appendMessage({ ...createChordMessage("assistant", data.reply, data.chord_chart, idx), meta });
      } else if (data.compose && data.compose.artifacts) {
        const composeResponse = {
          job_id: "chat",
          source: data.compose.source as "director" | "canned",
          song: data.compose.song,
          artifacts: data.compose.artifacts,
        };
        const msg = createCompositionMessage(
          "assistant",
          data.reply,
          composeResponse,
          [],
          data.compose.song.header,
          composeResponse.source,
          idx,
        );
        setCurrentSong(data.compose.song);
        appendMessage({ ...msg, meta });
      } else {
        const msg = createTextMessage("assistant", data.reply, idx);
        appendMessage({ ...msg, meta });
      }
    } catch (err) {
      if (controller.signal.aborted) return;
      const m = err instanceof Error ? err.message : "unknown chat error";
      setError(m);
      appendMessage(createTextMessage("assistant", `Chat failed: ${m}`, nextMessageIndex()));
    } finally {
      if (!controller.signal.aborted) stopWork();
    }
  }

  function appendMessage(m: ChatMessage) { setMessages((prev) => [...prev, m]); }

  function nextMessageIndex() {
    const next = messageIndexRef.current;
    messageIndexRef.current += 1;
    return next;
  }

  function resetConversation() {
    setMessages(messages.slice(0, 1));
    setError(null);
    setReferenceProfile(null);
    setActiveReference(null);
    setCurrentSong(null);
    setSessionTitle("Untitled session");
    sessionTitledRef.current = false;
  }

  return (
    <main className="app-shell">
      <aside className="app-sidebar" aria-label="Sessions">
        <div className="sidebar-brand-block">
          <span className="sidebar-brand">DAFT PROMPT</span>
          <span className="sidebar-tagline">MULTI-AGENT STUDIO</span>
        </div>

        <button type="button" className="sidebar-new" onClick={resetConversation}>
          <span className="sidebar-new-plus" aria-hidden="true">+</span>
          New session
        </button>

        <div className="sidebar-section">
          <span className="sidebar-section-title">Recent sessions</span>
          <div className="sidebar-recent-list">
            <button type="button" className="sidebar-recent">
              <span className="sidebar-recent-title">{sessionTitle}</span>
              <span className="sidebar-recent-meta">NOW · LIVE</span>
            </button>
          </div>
        </div>

        {referenceProfile || activeReference ? (
          <div className="sidebar-section">
            <span className="sidebar-section-title">Reference loaded</span>
            <span className="sidebar-item sidebar-item-active">
              {referenceProfile?.source.label ?? activeReference?.label}
            </span>
          </div>
        ) : null}

        <div className="sidebar-footer">
          <span className="sidebar-model-dot" aria-hidden="true" />
          <span>
            STUDIO LIVE · 8 AGENTS IDLE
            {buildIds ? ` · WEB ${buildIds.frontend.slice(0, 7)} · API ${buildIds.backend.slice(0, 7)}` : ""}
          </span>
        </div>
      </aside>

      <section className="app-main" aria-label="Conversation">
        <header className="app-topbar">
          <div className="app-topbar-left">
            <span className="app-topbar-dot" aria-hidden="true" />
            <span className="app-topbar-title">{sessionTitle}</span>
          </div>
          <span className="app-topbar-meta">TWILIGHT · OUTPUT MIDI</span>
        </header>
        <ChatThread messages={messages} busyLabel={activeWork} busyElapsedMs={busy ? busyElapsedMs : undefined} onCancel={busy ? cancelWork : undefined} workflow={activeWorkflow} />
        {error ? (
          <p className="error-banner" role="alert">{error}</p>
        ) : null}
        <ChatComposer
          busy={busy}
          prompt={prompt}
          onPromptChange={setPrompt}
          onSubmit={submit}
        />
      </section>
    </main>
  );
}

async function readApiError(response: Response) {
  try {
    const body = (await response.json()) as { detail?: unknown; error?: { message?: unknown } };
    if (typeof body.detail === "string") return body.detail;
    if (body.error && typeof body.error.message === "string") return body.error.message;
    return `backend error ${response.status}`;
  } catch {
    return `backend error ${response.status}`;
  }
}

function formatMeta(data: ChatResponse, elapsedMs: number): string {
  const seconds = elapsedMs / 1000;
  const usage = data.usage;
  if (usage && (usage.output_tokens || usage.total_tokens || usage.calls)) {
    const elapsedReal = usage.elapsed_seconds ?? seconds;
    const out = usage.output_tokens ?? 0;
    const total = usage.total_tokens ?? 0;
    const calls = usage.calls ?? 0;
    const tps = out > 0 ? out / Math.max(elapsedReal, 0.01) : 0;
    const tpsLabel = tps > 0 ? ` · ${tps.toFixed(1)} tok/s` : "";
    const callsLabel = calls ? ` · ${calls} llm call${calls === 1 ? "" : "s"}` : "";
    return `${elapsedReal.toFixed(1)}s · ${out} out / ${total} total tokens${tpsLabel}${callsLabel}`;
  }
  const approxTokens = Math.max(1, Math.round(data.reply.length / 4));
  const tps = approxTokens / Math.max(seconds, 0.01);
  return `${seconds.toFixed(1)}s · ~${approxTokens} tok · ~${tps.toFixed(1)} tok/s (estimate)`;
}
