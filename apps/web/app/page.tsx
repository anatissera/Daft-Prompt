"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import ChatComposer from "@/components/ChatComposer";
import { DaftHelmetIcon } from "@/components/icons";
import { AgentGraphView } from "@/components/PipelineGraphs";
import ChatThread, { type PipelineState, type PipelineStageIdx } from "@/components/ChatThread";
import type { ChatMessage } from "@/lib/chatTypes";
import type { AnalysisEvent, ReferenceProfile, SongState } from "@/lib/types";
import {
  chooseChatAction,
  createAnalysisMessage,
  createChordDiagramMessage,
  createCompositionMessage,
  createTextMessage,
} from "@/lib/chatActionAdapter.mjs";
import { deriveSessionTitle } from "@/lib/sessionTitle.mjs";
import { analyzeEndpoint, uploadTooLargeMessage } from "@/lib/apiBase.mjs";

type Intent = "answer_reference" | "song_question" | "edit_song" | "playable_chords" | "compose" | "compose_from_reference" | "clarify" | "off_topic";

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

interface PlayableChord {
  chord: string;
  notes: string[];
  midi_notes: number[];
}

interface PlayableChordSection {
  name: string;
  chords: PlayableChord[];
  confidence: number;
}

interface PlayableChords {
  instrument: "piano" | "guitar";
  source_label: string;
  confidence: number;
  sections: PlayableChordSection[];
}

interface ChatResponse {
  intent: Intent;
  reply: string;
  reference_id?: string | null;
  answer?: { answer: string; confidence?: string } | null;
  compose?: ChatComposeResult | null;
  playable_chords?: PlayableChords | null;
  clarification?: string | null;
  usage?: UsageInfo | null;
}

interface ChatDoneEvent {
  type: "done";
  job_id?: string;
  source?: string;
  song?: SongState & { header?: SongState["header"]; roster?: unknown[] };
  artifacts?: ChatArtifacts | null;
}

type ChatStreamEvent =
  | { type: "intent"; intent: Intent }
  | { type: "reply"; response: ChatResponse }
  | { type: "director"; source: string; header?: SongState["header"]; roster?: unknown[] }
  | { type: "agent_pass"; round: number; instrument_id: string; notes_summary?: string }
  | { type: "convergence"; round: number; converged: boolean }
  | ChatDoneEvent
  | { type: "error"; code: string; message: string; provider: string | null; model: string | null; partial: boolean };

export default function Home() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const messageIndexRef = useRef(1);
  const [prompt, setPrompt] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  // Main-panel view: chat, or the unified architecture graph (helmet button).
  const [view, setView] = useState<"chat" | "agents">("chat");
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
  const [pipeline, setPipeline] = useState<PipelineState | null>(null);
  const [promptQueue, setPromptQueue] = useState<string[]>([]);
  const [sessionTitle, setSessionTitle] = useState<string>("Untitled session");
  const sessionTitledRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  // Last composed job — lets the backend EDIT it on a later turn
  // ("swap the piano for a rhodes"). Reset with the session.
  const lastJobIdRef = useRef<string | null>(null);

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

  // Composes run for minutes over a live SSE stream. On phones the screen
  // times out mid-generation, the OS suspends the browser's network, the
  // stream dies AND the backend cancels the job on disconnect. A screen
  // wake lock while busy keeps the device awake for the duration; released
  // (and auto-released by the OS) as soon as work ends. Requires a secure
  // context — the tailscale-serve HTTPS endpoint qualifies.
  const wakeLockRef = useRef<{ release: () => Promise<void> } | null>(null);

  async function acquireWakeLock() {
    try {
      const wl = (navigator as Navigator & { wakeLock?: { request(type: "screen"): Promise<{ release(): Promise<void> }> } }).wakeLock;
      if (wl) wakeLockRef.current = await wl.request("screen");
    } catch { /* unsupported or denied — degrade silently */ }
  }

  function releaseWakeLock() {
    wakeLockRef.current?.release().catch(() => { /* noop */ });
    wakeLockRef.current = null;
  }

  // The OS drops wake locks when the tab is hidden; re-acquire when the
  // user returns while a compose is still running.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible" && busyStartedAt !== null && !wakeLockRef.current) {
        void acquireWakeLock();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [busyStartedAt]);

  function startWork(label: string) {
    setActiveWork(label);
    setBusyStartedAt(performance.now());
    void acquireWakeLock();
  }

  function stopWork() {
    setActiveWork(null);
    setBusyStartedAt(null);
    setPipeline(null);
    abortRef.current = null;
    releaseWakeLock();
  }

  function cancelWork() {
    if (abortRef.current) abortRef.current.abort();
    appendMessage(createTextMessage("assistant", "(cancelled)", nextMessageIndex()));
    stopWork();
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = prompt.trim();
    if (!text && !selectedFile) return;

    // If the studio is already working, queue the raw text (compose intent
    // only — file uploads never queue because attachments can't be
    // deferred). Enqueued prompts stack visibly above the composer and
    // drain automatically as previous jobs finish.
    if (busy) {
      if (!text) return;
      setPromptQueue((prev) => [...prev, text]);
      setPrompt("");
      return;
    }

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

  // Drain the queue whenever the studio goes idle. We pull the first entry,
  // append it as a user message, and fire chat() — this loop keeps running
  // until the queue empties because every chat() completion re-triggers the
  // effect via activeWork transitioning back to null.
  useEffect(() => {
    if (busy) return;
    if (promptQueue.length === 0) return;
    const [next, ...rest] = promptQueue;
    setPromptQueue(rest);
    appendMessage(createTextMessage("user", next, nextMessageIndex()));
    setError(null);
    void chat(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busy, promptQueue]);

  async function chat(message: string) {
    startWork("Thinking…");
    const controller = new AbortController();
    abortRef.current = controller;
    const startedAt = performance.now();

    // Real-time compose state accumulated from SSE events. When the backend
    // classifies the turn as a non-compose intent it emits a single `reply`
    // event and we skip the pipeline entirely.
    let intent: Intent | null = null;
    let replyResponse: ChatResponse | null = null;
    let doneEvent: (ChatDoneEvent) | null = null;
    let composeAgentEvents = 0;

    try {
      const res = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "content-type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          message,
          reference_id: referenceProfile?.reference_id ?? null,
          edit_job_id: lastJobIdRef.current,
        }),
      });
      if (!res.ok) throw new Error(await readApiError(res));
      if (!res.body) throw new Error("backend did not return a stream");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      readLoop: while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";
        for (const chunk of chunks) {
          const line = chunk.split("\n").find((entry) => entry.startsWith("data:"));
          if (!line) continue;
          const ev = JSON.parse(line.slice(5).trim()) as ChatStreamEvent;

          if (ev.type === "intent") {
            intent = ev.intent;
            if (ev.intent === "compose" || ev.intent === "compose_from_reference") {
              setPipeline({ stageIdx: 0, substep: null });
            }
          } else if (ev.type === "reply") {
            replyResponse = ev.response;
          } else if (ev.type === "director") {
            const header = ev.header;
            setActiveWork(
              header
                ? `Composing ${header.genre || "sketch"} · ${Math.round(header.tempo_bpm ?? 0)} BPM · ${header.key || "?"}`
                : "Composing…",
            );
            setPipeline({ stageIdx: 1, substep: "roster picked, instruments starting…" });
          } else if (ev.type === "agent_pass") {
            composeAgentEvents += 1;
            setPipeline({
              stageIdx: 1,
              substep: `${ev.instrument_id || "instrument"} composing (round ${ev.round ?? 1})…`,
            });
          } else if (ev.type === "convergence") {
            setPipeline({ stageIdx: 2, substep: "arbiter validating harmonic fit…" });
            // Arbiter finishes synchronously before render_artifacts runs; nudge
            // the visual to the rendering step so the UI doesn't sit on arbiter
            // for the full render span (which is silent from the backend side).
            setTimeout(() => {
              setPipeline((prev) =>
                prev && prev.stageIdx === 2
                  ? { stageIdx: 3, substep: "writing MIDI + score…" }
                  : prev,
              );
            }, 400);
          } else if (ev.type === "done") {
            doneEvent = ev;
            setError(null);
            setPipeline({ stageIdx: 3, substep: "done" });
          } else if (ev.type === "error") {
            throw new Error(ev.message || "backend error");
          }
        }
        if (controller.signal.aborted) break readLoop;
      }

      maybeTitleSession(message);
      const idx = nextMessageIndex();

      if (doneEvent && doneEvent.song && doneEvent.artifacts) {
        setError(null);
        lastJobIdRef.current = doneEvent.job_id ?? lastJobIdRef.current;
        const composeResponse = {
          job_id: doneEvent.job_id ?? "chat",
          source: (doneEvent.source ?? "director") as "director" | "canned",
          song: doneEvent.song,
          artifacts: doneEvent.artifacts,
        };
        const header = doneEvent.song?.header;
        const reply = header
          ? `Generated a ${header.genre || "sketch"} at ${Math.round(header.tempo_bpm ?? 0)} BPM in ${header.key || "?"} (${doneEvent.song?.roster?.length ?? 0} instruments, ${composeAgentEvents} agent passes).`
          : "Sketch ready.";
        const elapsed = performance.now() - startedAt;
        const meta = `${(elapsed / 1000).toFixed(1)}s · ${composeAgentEvents} agent passes`;
        const msg = createCompositionMessage(
          "assistant",
          reply,
          composeResponse,
          [],
          header,
          composeResponse.source,
          idx,
        );
        appendMessage({ ...msg, meta });
      } else if (replyResponse) {
        setError(null);
        const meta = formatMeta(replyResponse, performance.now() - startedAt);
        const msg = replyResponse.playable_chords
          ? createChordDiagramMessage("assistant", replyResponse.reply, replyResponse.playable_chords, idx)
          : createTextMessage("assistant", replyResponse.reply, idx);
        appendMessage({ ...msg, meta });
      } else if (intent) {
        // The stream ended without a terminal `done`/`reply` event. The usual
        // cause is the proxy's 300s ceiling cutting a compose that ran longer:
        // the backend keeps working and still renders its artifacts, so the run
        // is recoverable. Saying that beats the silent "(no response)" this
        // used to print, which read as if the model had nothing to say.
        const m =
          "The stream ended before the backend finished — a compose past the 300s proxy limit gets cut here. It may have completed server-side; try again.";
        setError(m);
        appendMessage(createTextMessage("assistant", `Chat failed: ${m}`, idx));
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
    // Checked before the request because the host rejects oversized uploads at
    // its edge, with an HTML error page we can't turn into a useful message.
    const tooLarge = uploadTooLargeMessage(file.size);
    if (tooLarge) {
      setError(tooLarge);
      appendMessage(createTextMessage("assistant", tooLarge, nextMessageIndex()));
      return;
    }

    startWork("Analyzing audio (tempo, key, energy, sections, chords)…");
    const controller = new AbortController();
    abortRef.current = controller;
    setReferenceProfile(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      // Straight to the backend when NEXT_PUBLIC_API_BASE_URL is set: a
      // serverless proxy caps bodies at 4.5 MB and would time out before stem
      // separation finishes. Falls back to the proxy route locally.
      const res = await fetch(analyzeEndpoint(process.env.NEXT_PUBLIC_API_BASE_URL), {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });
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
          }
        }
      }
      if (!profile) throw new Error("analysis stream ended without a profile");
      setReferenceProfile(profile);
      appendMessage(createAnalysisMessage("assistant", analysisReadyMessage(profile), profile, nextMessageIndex()));
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err) {
      if (controller.signal.aborted) return;
      const m = normalizeAnalysisError(err);
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
    setSessionTitle("Untitled session");
    sessionTitledRef.current = false;
    lastJobIdRef.current = null;
    setView("chat");
  }

  return (
    <main className="app-shell">
      <aside className="app-sidebar" aria-label="Sessions">
        <div className="sidebar-brand-block">
          <span className="sidebar-brand">DAFT PROMPT</span>
          <span className="sidebar-tagline">MULTI-AGENT STUDIO</span>
        </div>

        <div className="sidebar-actions">
          <button
            type="button"
            className="sidebar-square"
            onClick={resetConversation}
            title="New session"
            aria-label="New session"
          >
            <span className="sidebar-new-plus" aria-hidden="true">+</span>
          </button>
          <button
            type="button"
            className={`sidebar-square sidebar-square-icon${view === "agents" ? " sidebar-square-active" : ""}`}
            onClick={() => setView((v) => (v === "agents" ? "chat" : "agents"))}
            title="Agent map"
            aria-label="Agent map"
            aria-pressed={view === "agents"}
          >
            <DaftHelmetIcon size={26} />
          </button>
        </div>

        <div className="sidebar-section">
          <span className="sidebar-section-title">Recent sessions</span>
          <div className="sidebar-recent-list">
            <button type="button" className="sidebar-recent" onClick={() => setView("chat")}>
              <span className="sidebar-recent-title">{sessionTitle}</span>
              <span className="sidebar-recent-meta">NOW · LIVE</span>
            </button>
          </div>
        </div>

        {referenceProfile ? (
          <div className="sidebar-section">
            <span className="sidebar-section-title">Reference loaded</span>
            <span className="sidebar-item sidebar-item-active">{referenceProfile.source.label}</span>
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
            <span className="app-topbar-title">
              {view === "agents" ? "Architecture" : sessionTitle}
            </span>
          </div>
          <span className="app-topbar-meta">
            {view === "chat" ? "TWILIGHT · OUTPUT MIDI" : "SYSTEM VIEW · CHAT PAUSED"}
          </span>
        </header>
        {view === "agents" ? (
          <AgentGraphView />
        ) : (
          <>
            <ChatThread messages={messages} busyLabel={activeWork} busyElapsedMs={busy ? busyElapsedMs : undefined} onCancel={busy ? cancelWork : undefined} pipeline={pipeline} />
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
              queuedPrompts={promptQueue}
              onCancelQueued={(i) => setPromptQueue((prev) => prev.filter((_, idx) => idx !== i))}
            />
          </>
        )}
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

function analysisReadyMessage(profile: ReferenceProfile) {
  const audio = profile.audio;
  if (!audio) return "Analysis finished, but no audio profile was returned.";
  const tempoValue = audio.tempo?.primary_bpm ?? audio.tempo_bpm;
  const tempo = tempoValue == null ? "unknown tempo" : `likely ${Math.round(tempoValue)} BPM`;
  const keyValue = audio.harmony?.key?.primary?.key ?? audio.key;
  const key = keyValue ? `likely key ${keyValue}` : "unknown key";
  return `Analysis ready for ${profile.source.label}: ${tempo}, ${key}.`;
}
