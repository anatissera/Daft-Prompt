"use client";

import { useRef, useState, type FormEvent } from "react";
import dynamic from "next/dynamic";
import type { ComposeEvent, ComposeResponse, Header, ReferenceProfile, RosterItem } from "@/lib/types";
import NegotiationFeed from "@/components/NegotiationFeed";
import ReferenceContext from "@/components/ReferenceContext";
import RosterView from "@/components/RosterView";
import { answerReferenceQuestion, isReferenceQuestion } from "@/lib/referenceProfileView.mjs";

const ScoreViewer = dynamic(() => import("@/components/ScoreViewer"), { ssr: false });
const TrackMixer = dynamic(() => import("@/components/TrackMixer"), { ssr: false });

type FeedEvent = Extract<ComposeEvent, { type: "agent_pass" | "convergence" | "error" }>;

type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
};

export default function Home() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [prompt, setPrompt] = useState("Analyze this audio.");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      text: "Attach a local song to analyze it, or describe a style and I will compose a quick multi-agent sketch.",
    },
  ]);
  const [analyzing, setAnalyzing] = useState(false);
  const [composing, setComposing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [referenceProfile, setReferenceProfile] = useState<ReferenceProfile | null>(null);
  const [source, setSource] = useState<"director" | "canned" | null>(null);
  const [header, setHeader] = useState<Header | null>(null);
  const [roster, setRoster] = useState<RosterItem[]>([]);
  const [feed, setFeed] = useState<FeedEvent[]>([]);
  const [result, setResult] = useState<ComposeResponse | null>(null);

  const busy = analyzing || composing;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;

    const messageText = prompt.trim() || (selectedFile ? "Analyze this audio." : "Compose a short song.");
    appendMessage("user", selectedFile ? `${messageText} Attached: ${selectedFile.name}` : messageText);
    setError(null);

    if (selectedFile) {
      await analyzeReference(selectedFile, messageText);
      return;
    }

    if (referenceProfile && isReferenceQuestion(messageText)) {
      appendMessage("assistant", answerReferenceQuestion(messageText, referenceProfile));
      setError(null);
      return;
    }

    await compose(messageText);
  }

  async function analyzeReference(file: File, messageText: string) {
    setAnalyzing(true);
    setReferenceProfile(null);
    try {
      appendMessage("system", "File accepted. Analyzing local audio...");
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch("/api/references/analyze", {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error(await readApiError(res));

      const profile = (await res.json()) as ReferenceProfile;
      setReferenceProfile(profile);
      appendMessage("assistant", analysisReadyMessage(profile));
      setPrompt("What chords are probably in the chorus?");
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err) {
      const message = err instanceof Error ? err.message : "unknown analysis error";
      setError(message);
      appendMessage("assistant", `I could not analyze that file: ${message}`);
    } finally {
      setAnalyzing(false);
    }
  }

  async function compose(style: string) {
    setComposing(true);
    setSource(null);
    setHeader(null);
    setRoster([]);
    setFeed([]);
    setResult(null);

    try {
      const res = await fetch("/api/compose", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ style }),
      });
      if (!res.ok || !res.body) throw new Error(`backend error ${res.status}`);

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
          const line = chunk.split("\n").find((l) => l.startsWith("data:"));
          if (!line) continue;
          const event = JSON.parse(line.slice(5).trim()) as ComposeEvent;
          if (event.type === "director") {
            setSource(event.source);
            setHeader(event.header);
            setRoster(event.roster);
          } else if (event.type === "agent_pass" || event.type === "convergence" || event.type === "error") {
            setFeed((prev) => [...prev, event]);
            if (event.type === "error") {
              setError(event.message);
              appendMessage("assistant", event.message);
            }
          } else if (event.type === "done") {
            setResult(event);
            appendMessage("assistant", `Generated a ${event.song.header.genre} sketch at ${event.song.header.tempo_bpm} BPM.`);
          }
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "unknown composition error";
      setError(message);
      appendMessage("assistant", `Composition failed: ${message}`);
    } finally {
      setComposing(false);
    }
  }

  function appendMessage(role: ChatMessage["role"], text: string) {
    setMessages((prev) => [...prev, { id: `${role}-${Date.now()}-${prev.length}`, role, text }]);
  }

  return (
    <main className="workspace">
      <section className="chat-shell" aria-label="Conversation">
        <div className="workspace-heading">
          <p className="hero-eyebrow">
            <span className="hero-eyebrow-dot" aria-hidden="true" />
            Conversational studio
          </p>
          <h1 className="hero-title">LLMinem</h1>
          <p className="hero-subtitle">Analyze local songs, inspect the musical profile, or compose from a plain-language prompt.</p>
        </div>

        <div className="chat-thread">
          {messages.map((message) => (
            <article key={message.id} className={`chat-message chat-message-${message.role}`}>
              <span className="chat-role">{message.role}</span>
              <p>{message.text}</p>
            </article>
          ))}
          {busy ? (
            <article className="chat-message chat-message-system" aria-live="polite">
              <span className="chat-role">{analyzing ? "analysis" : "composition"}</span>
              <p>{analyzing ? "Analyzing audio profile and probable chords..." : "Agents are composing and negotiating..."}</p>
            </article>
          ) : null}
        </div>

        {error ? (
          <p className="error-banner" role="alert">
            {error}
          </p>
        ) : null}

        <form onSubmit={submit} className="chat-composer">
          <label htmlFor="prompt-input" className="sr-only">
            Message
          </label>
          <textarea
            id="prompt-input"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Analyze this audio, or compose a slow blues..."
            className="chat-input"
            rows={3}
          />
          <div className="composer-actions">
            <input
              ref={fileInputRef}
              id="audio-file"
              type="file"
              accept="audio/*,.mp3,.wav,.flac,.m4a,.ogg,.aiff,.aif"
              className="sr-only"
              onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
            />
            <label htmlFor="audio-file" className="attach-button">
              Attach audio
            </label>
            {selectedFile ? <span className="selected-file">{selectedFile.name}</span> : null}
            <button type="submit" disabled={busy} className="compose-button">
              {busy ? <span className="spinner" aria-hidden="true" /> : null}
              {analyzing ? "Analyzing..." : composing ? "Composing..." : selectedFile ? "Analyze" : "Send"}
            </button>
          </div>
        </form>

        {header ? (
          <section className="composition-results">
            <RosterView header={header} roster={roster} source={source ?? "canned"} />
            <NegotiationFeed events={feed} />

            {result && Object.keys(result.song.parts).length > 0 ? (
              <>
                <div className="card">
                  <h2 className="section-title">Playback</h2>
                  <TrackMixer song={result.song} />
                  <a className="artifact-link" href={result.artifacts.midi}>
                    Download full MIDI
                  </a>
                </div>

                <details className="card">
                  <summary className="details-summary">Score</summary>
                  <ScoreViewer musicXmlUrl={result.artifacts.musicxml} />
                </details>
              </>
            ) : result ? (
              <p className="empty-note">
                {result.song.errors.length > 0
                  ? "Composition stopped before any playable parts were produced."
                  : "No notes were composed for this song. Try composing again."}
              </p>
            ) : null}
          </section>
        ) : null}
      </section>

      <ReferenceContext profile={referenceProfile} analyzing={analyzing} selectedFileName={selectedFile?.name ?? null} />
    </main>
  );
}

async function readApiError(response: Response) {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : `backend error ${response.status}`;
  } catch {
    return `backend error ${response.status}`;
  }
}

function analysisReadyMessage(profile: ReferenceProfile) {
  const audio = profile.audio;
  if (!audio) return "Analysis finished, but no audio profile was returned.";

  const tempo = audio.tempo_bpm === null || audio.tempo_bpm === undefined ? "unknown tempo" : `likely ${Math.round(audio.tempo_bpm)} BPM`;
  const key = audio.key ? `likely key ${audio.key}` : "unknown key";
  return `Analysis ready for ${profile.source.label}: ${tempo}, ${key}, with probable chords in the context panel.`;
}
