"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import ChatComposer from "@/components/ChatComposer";
import ChatThread from "@/components/ChatThread";
import type { ChatMessage } from "@/lib/chatTypes";
import type { AnalysisEvent, ChordChartRow, MelodyProfile, ReferenceProfile, SongState, TabExcerpt } from "@/lib/types";
import { getAnalysisReadyMessage } from "@/lib/referenceProfileView.mjs";
import {
  createAnalysisProgress,
  updateAnalysisProgress,
  type AnalysisStageState,
} from "@/lib/analysisProgress.mjs";
import {
  buildChatRequestPayload,
  buildConversationContext,
  chooseChatAction,
  createAnalysisMessage,
  createCompositionMessage,
  createChordMessage,
  createMelodyMessage,
  createTabMessage,
  createTextMessage,
  referenceMemoryFromChatResponse,
} from "@/lib/chatActionAdapter.mjs";
import { deriveSessionTitle } from "@/lib/sessionTitle.mjs";

type Intent = "answer_reference" | "compose" | "compose_from_reference" | "clarify" | "off_topic";

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
  clarification?: string | null;
  usage?: UsageInfo | null;
  error?: { message?: string; code?: string; provider?: string | null; model?: string | null } | null;
}

const localAudioAnalysisEnabled = process.env.NEXT_PUBLIC_ENABLE_LOCAL_AUDIO_ANALYSIS === "true";

export default function Home() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const messageIndexRef = useRef(1);
  const [prompt, setPrompt] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([
    createTextMessage(
      "assistant",
      localAudioAnalysisEnabled
        ? "Daft Prompt — multi-agent music studio. Ask me to compose a sketch (\"slow blues in F minor\"), upload audio to analyze, or ask about a loaded reference."
        : "Daft Prompt — multi-agent music studio. Ask me to compose a sketch (\"slow blues in F minor\"), explore music theory, or research a song when web research is enabled.",
      0,
    ),
  ]);
  const [referenceProfile, setReferenceProfile] = useState<ReferenceProfile | null>(null);
  const [activeReference, setActiveReference] = useState<{ referenceId: string; label: string } | null>(null);
  const [currentSong, setCurrentSong] = useState<SongState | null>(null);
  const [activeWork, setActiveWork] = useState<string | null>(null);
  const [busyStartedAt, setBusyStartedAt] = useState<number | null>(null);
  const [busyElapsedMs, setBusyElapsedMs] = useState<number>(0);
  const [analysisProgress, setAnalysisProgress] = useState<AnalysisStageState[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sessionTitle, setSessionTitle] = useState<string>("Untitled session");
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

  function startWork(label: string) {
    setActiveWork(label);
    setBusyStartedAt(performance.now());
  }

  function stopWork() {
    setActiveWork(null);
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
      hasSelectedFile: selectedFile !== null,
    });
    const attachedText = selectedFile ? `${action.messageText} Attached: ${selectedFile.name}` : action.messageText;

    appendMessage(createTextMessage("user", attachedText, nextMessageIndex()));
    setPrompt("");
    setError(null);

    if (action.type === "analyze") {
      if (!selectedFile) return;
      await analyzeReference(selectedFile);
      return;
    }
    await chat(action.messageText);
  }

  async function chat(message: string) {
    startWork("Thinking…");
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
        })),
      });
      if (!res.ok) throw new Error(await readApiError(res));
      const data = (await res.json()) as ChatResponse;
      const meta = formatMeta(data, performance.now() - startedAt);
      const idx = nextMessageIndex();
      // Title the session from the first user message (client-side, no LLM).
      maybeTitleSession(message);
      const rememberedReference = referenceMemoryFromChatResponse(data, message);
      if (rememberedReference) setActiveReference(rememberedReference);
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

  async function analyzeReference(file: File) {
    startWork("Analyzing audio (tempo, key, energy, sections, chords)…");
    setAnalysisProgress(createAnalysisProgress());
    const controller = new AbortController();
    abortRef.current = controller;
    setReferenceProfile(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch("/api/references/analyze", { method: "POST", body: formData, signal: controller.signal });
      if (!res.ok) throw new Error(await readApiError(res));
      if (!res.body) throw new Error("backend did not return an analysis stream");

      let profile: ReferenceProfile | null = null;
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";
        for (const chunk of chunks) {
          const line = chunk.split("\n").find((entry) => entry.startsWith("data:"));
          if (!line) continue;
          const event = JSON.parse(line.slice(5).trim()) as AnalysisEvent;
          if (event.type === "done") {
            profile = event.profile;
          } else if (event.type === "error") {
            throw new Error(event.message);
          } else {
            setActiveWork(event.message);
            setAnalysisProgress((current) => (
              current ? updateAnalysisProgress(current, event) : current
            ));
          }
        }
      }
      if (!profile) throw new Error("analysis stream ended without a profile");
      setReferenceProfile(profile);
      setActiveReference({ referenceId: profile.reference_id, label: profile.source.label });
      appendMessage(createAnalysisMessage("assistant", getAnalysisReadyMessage(profile), profile, nextMessageIndex()));
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err) {
      if (controller.signal.aborted) return;
      const m = normalizeAnalysisError(err);
      setError(m);
      appendMessage(createTextMessage("assistant", `I could not analyze that file: ${m}`, nextMessageIndex()));
    } finally {
      setAnalysisProgress(null);
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
          <span>STUDIO LIVE · 8 AGENTS IDLE</span>
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
        <ChatThread messages={messages} busyLabel={activeWork} busyElapsedMs={busy ? busyElapsedMs : undefined} onCancel={busy ? cancelWork : undefined} analysisProgress={analysisProgress} />
        {error ? (
          <p className="error-banner" role="alert">{error}</p>
        ) : null}
        <ChatComposer
          busy={busy}
          audioAttachmentEnabled={localAudioAnalysisEnabled}
          prompt={prompt}
          selectedFileName={selectedFile?.name ?? null}
          fileInputRef={fileInputRef}
          onPromptChange={setPrompt}
          onFileChange={setSelectedFile}
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

function normalizeAnalysisError(err: unknown) {
  const message = err instanceof Error ? err.message : "unknown analysis error";
  const normalized = message.toLowerCase();
  if (
    normalized.includes("load failed") ||
    normalized.includes("body timeout") ||
    normalized.includes("terminated") ||
    normalized.includes("networkerror")
  ) {
    return (
      "analysis timed out while the backend was still working. "
      + "Long songs can take several minutes during stem separation; try again after this update or use a shorter excerpt."
    );
  }
  return message;
}
