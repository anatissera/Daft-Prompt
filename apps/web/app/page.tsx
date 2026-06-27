"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import ChatComposer from "@/components/ChatComposer";
import ChatThread from "@/components/ChatThread";
import type { ChatMessage } from "@/lib/chatTypes";
import type { ReferenceProfile, SongState } from "@/lib/types";
import {
  chooseChatAction,
  createAnalysisMessage,
  createCompositionMessage,
  createTextMessage,
} from "@/lib/chatActionAdapter.mjs";

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
}

interface ChatResponse {
  intent: Intent;
  reply: string;
  reference_id?: string | null;
  answer?: { answer: string; confidence?: string } | null;
  compose?: ChatComposeResult | null;
  clarification?: string | null;
  usage?: UsageInfo | null;
}

export default function Home() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const messageIndexRef = useRef(1);
  const [prompt, setPrompt] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([
    createTextMessage(
      "assistant",
      "Daft Prompt — multi-agent music studio. Ask me to compose a sketch (\"slow blues in F minor\"), upload audio to analyze, or ask about a loaded reference.",
      0,
    ),
  ]);
  const [referenceProfile, setReferenceProfile] = useState<ReferenceProfile | null>(null);
  const [activeWork, setActiveWork] = useState<string | null>(null);
  const [busyStartedAt, setBusyStartedAt] = useState<number | null>(null);
  const [busyElapsedMs, setBusyElapsedMs] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

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
        body: JSON.stringify({
          message,
          reference_id: referenceProfile?.reference_id ?? null,
        }),
      });
      if (!res.ok) throw new Error(await readApiError(res));
      const data = (await res.json()) as ChatResponse;
      const meta = formatMeta(data, performance.now() - startedAt);
      const idx = nextMessageIndex();
      if (data.compose && data.compose.artifacts) {
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
    const controller = new AbortController();
    abortRef.current = controller;
    setReferenceProfile(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch("/api/references/analyze", { method: "POST", body: formData, signal: controller.signal });
      if (!res.ok) throw new Error(await readApiError(res));

      const profile = (await res.json()) as ReferenceProfile;
      setReferenceProfile(profile);
      appendMessage(createAnalysisMessage("assistant", analysisReadyMessage(profile), profile, nextMessageIndex()));
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err) {
      if (controller.signal.aborted) return;
      const m = err instanceof Error ? err.message : "unknown analysis error";
      setError(m);
      appendMessage(createTextMessage("assistant", `I could not analyze that file: ${m}`, nextMessageIndex()));
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
  }

  return (
    <main className="app-shell">
      <aside className="app-sidebar" aria-label="Sessions">
        <div className="sidebar-header">
          <span className="sidebar-brand">Daft Prompt</span>
          <button type="button" className="sidebar-new" onClick={resetConversation}>+ New chat</button>
        </div>
        <nav className="sidebar-section" aria-label="Current session">
          <span className="sidebar-section-title">Current</span>
          <span className="sidebar-item sidebar-item-active">Untitled conversation</span>
        </nav>
        {referenceProfile ? (
          <div className="sidebar-section">
            <span className="sidebar-section-title">Reference</span>
            <span className="sidebar-item">{referenceProfile.source.label}</span>
          </div>
        ) : null}
        <div className="sidebar-footer">
          <span className="sidebar-model-dot" aria-hidden="true" />
          <span>backend · /chat</span>
        </div>
      </aside>

      <section className="app-main" aria-label="Conversation">
        <header className="app-topbar">
          <span className="app-topbar-title">Untitled conversation</span>
          <span className="app-topbar-meta">multi-agent · {referenceProfile ? "reference loaded" : "no reference"}</span>
        </header>
        <ChatThread messages={messages} busyLabel={activeWork} busyElapsedMs={busy ? busyElapsedMs : undefined} onCancel={busy ? cancelWork : undefined} />
        {error ? (
          <p className="error-banner" role="alert">{error}</p>
        ) : null}
        <ChatComposer
          busy={busy}
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

function analysisReadyMessage(profile: ReferenceProfile) {
  const audio = profile.audio;
  if (!audio) return "Analysis finished, but no audio profile was returned.";
  const tempo = audio.tempo_bpm == null ? "unknown tempo" : `likely ${Math.round(audio.tempo_bpm)} BPM`;
  const key = audio.key ? `likely key ${audio.key}` : "unknown key";
  return `Analysis ready for ${profile.source.label}: ${tempo}, ${key}.`;
}
