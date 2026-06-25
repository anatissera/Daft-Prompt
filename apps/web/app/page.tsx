"use client";

import { useRef, useState, type FormEvent } from "react";
import ChatComposer from "@/components/ChatComposer";
import ChatThread from "@/components/ChatThread";
import type { ChatMessage, FeedEvent } from "@/lib/chatTypes";
import type { AnalysisEvent, ComposeEvent, ComposeResponse, Header, ReferenceProfile } from "@/lib/types";
import { answerReferenceQuestion } from "@/lib/referenceProfileView.mjs";
import {
  chooseChatAction,
  createAnalysisMessage,
  createCompositionMessage,
  createTextMessage,
} from "@/lib/chatActionAdapter.mjs";

export default function Home() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const messageIndexRef = useRef(1);
  const [prompt, setPrompt] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([
    createTextMessage(
      "assistant",
      "Tell me what you want to make or understand. You can attach a local song for analysis, ask about a current reference, or compose from a plain-language prompt.",
      0,
    ),
  ]);
  const [referenceProfile, setReferenceProfile] = useState<ReferenceProfile | null>(null);
  const [activeWork, setActiveWork] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const busy = activeWork !== null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;

    const action = chooseChatAction({
      prompt,
      hasSelectedFile: selectedFile !== null,
      hasReferenceProfile: referenceProfile !== null,
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

    if (action.type === "answer_reference") {
      if (!referenceProfile) return;
      appendMessage(createTextMessage("assistant", answerReferenceQuestion(action.messageText, referenceProfile), nextMessageIndex()));
      return;
    }

    await compose(action.messageText);
  }

  async function analyzeReference(file: File) {
    setActiveWork("File accepted. Extracting tempo, key, energy, sections, and probable chords...");
    setReferenceProfile(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch("/api/references/analyze", {
        method: "POST",
        body: formData,
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
      const message = err instanceof Error ? err.message : "unknown analysis error";
      setError(message);
      appendMessage(createTextMessage("assistant", `I could not analyze that file: ${message}`, nextMessageIndex()));
    } finally {
      setActiveWork(null);
    }
  }

  async function compose(style: string) {
    setActiveWork("Director is choosing the arrangement...");
    const feed: FeedEvent[] = [];
    let header: Header | null = null;
    let source: ComposeResponse["source"] | null = null;

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
          const line = chunk.split("\n").find((entry) => entry.startsWith("data:"));
          if (!line) continue;
          const event = JSON.parse(line.slice(5).trim()) as ComposeEvent;
          if (event.type === "director") {
            source = event.source;
            header = event.header;
            setActiveWork(`Director picked ${event.header.genre} at ${event.header.tempo_bpm} BPM. Agents are composing...`);
          } else if (event.type === "agent_pass" || event.type === "convergence" || event.type === "error") {
            feed.push(event);
            setActiveWork(event.type === "agent_pass" ? `${event.instrument_id} wrote a part...` : "Agents are resolving the arrangement...");
            if (event.type === "error") {
              setError(event.message);
            }
          } else if (event.type === "done") {
            appendMessage(
              createCompositionMessage(
                "assistant",
                `Generated a ${event.song.header.genre} sketch at ${event.song.header.tempo_bpm} BPM.`,
                event,
                feed.slice(),
                header,
                source,
                nextMessageIndex(),
              ),
            );
          }
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "unknown composition error";
      setError(message);
      appendMessage(createTextMessage("assistant", `Composition failed: ${message}`, nextMessageIndex()));
    } finally {
      setActiveWork(null);
    }
  }

  function appendMessage(message: ChatMessage) {
    setMessages((prev) => [...prev, message]);
  }

  function nextMessageIndex() {
    const next = messageIndexRef.current;
    messageIndexRef.current += 1;
    return next;
  }

  return (
    <main className="chat-workspace">
      <section className="chat-hero" aria-label="LLMinem chat workspace">
        <p className="hero-eyebrow">
          <span className="hero-eyebrow-dot" aria-hidden="true" />
          Conversational studio
        </p>
        <h1 className="hero-title">LLMinem</h1>
        <p className="hero-subtitle">Analyze a local song, ask musical questions, or compose a new sketch from the same chat.</p>
      </section>

      <section className="chat-panel" aria-label="Conversation">
        <ChatThread messages={messages} busyLabel={activeWork} />
        {error ? (
          <p className="error-banner" role="alert">
            {error}
          </p>
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
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : `backend error ${response.status}`;
  } catch {
    return `backend error ${response.status}`;
  }
}

function analysisReadyMessage(profile: ReferenceProfile) {
  const audio = profile.audio;
  if (!audio) return "Analysis finished, but no audio profile was returned.";

  const tempoValue = audio.tempo?.primary_bpm ?? audio.tempo_bpm;
  const tempo = tempoValue === null || tempoValue === undefined ? "unknown tempo" : `likely ${Math.round(tempoValue)} BPM`;
  const keyValue = audio.harmony?.key?.primary?.key ?? audio.key;
  const key = keyValue ? `likely key ${keyValue}` : "unknown key";
  return `Analysis ready for ${profile.source.label}: ${tempo}, ${key}, with probable chords and A/B/C structure below.`;
}
