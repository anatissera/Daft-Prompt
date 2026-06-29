"use client";

import { useRef, useState, type FormEvent } from "react";
import ChatComposer from "@/components/ChatComposer";
import ChatThread from "@/components/ChatThread";
import type { ChatMessage, FeedEvent } from "@/lib/chatTypes";
import type { AnalysisEvent, ComposeEvent, ComposeResponse, Header, ReferenceProfile } from "@/lib/types";
import { answerReferenceQuestion, getAnalysisReadyMessage } from "@/lib/referenceProfileView.mjs";
import {
  createAnalysisProgress,
  updateAnalysisProgress,
  type AnalysisStageState,
} from "@/lib/analysisProgress.mjs";
import {
  chooseChatAction,
  createAnalysisMessage,
  createCompositionMessage,
  createTextMessage,
} from "@/lib/chatActionAdapter.mjs";

export default function Home() {
  const messageIndexRef = useRef(1);
  const [prompt, setPrompt] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([
    createTextMessage(
      "assistant",
      "Tell me what song you want to understand, or ask me to compose with traits from songs you name.",
      0,
    ),
  ]);
  const [referenceProfile, setReferenceProfile] = useState<ReferenceProfile | null>(null);
  const [activeWork, setActiveWork] = useState<string | null>(null);
  const [analysisProgress, setAnalysisProgress] = useState<AnalysisStageState[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const busy = activeWork !== null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;

    const action = chooseChatAction({
      prompt,
      hasReferenceProfile: referenceProfile !== null,
    });

    appendMessage(createTextMessage("user", action.messageText, nextMessageIndex()));
    setPrompt("");
    setError(null);

    if (action.type === "research") {
      await researchReference(action.messageText);
      return;
    }

    if (action.type === "answer_reference") {
      if (!referenceProfile) return;
      appendMessage(createTextMessage("assistant", answerReferenceQuestion(action.messageText, referenceProfile), nextMessageIndex()));
      return;
    }

    await compose(action.messageText);
  }

  async function researchReference(query: string) {
    setActiveWork("Searching public music sources...");
    setAnalysisProgress(createAnalysisProgress());
    setReferenceProfile(null);
    try {
      const res = await fetch("/api/references/research", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ query }),
      });
      if (!res.ok) throw new Error(await readApiError(res));
      if (!res.body) throw new Error("backend did not return a research stream");

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
      if (!profile) throw new Error("research stream ended without a profile");
      setReferenceProfile(profile);
      appendMessage(createAnalysisMessage("assistant", getAnalysisReadyMessage(profile), profile, nextMessageIndex()));
    } catch (err) {
      const message = normalizeAnalysisError(err);
      setError(message);
      appendMessage(createTextMessage("assistant", `I could not research that song: ${message}`, nextMessageIndex()));
    } finally {
      setActiveWork(null);
      setAnalysisProgress(null);
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
      <section className="chat-hero" aria-label="Daft Prompt chat workspace">
        <p className="hero-eyebrow">
          <span className="hero-eyebrow-dot" aria-hidden="true" />
          Digital Studio // AI Music Lab
        </p>
        <h1 className="hero-title" aria-label="Daft Prompt">
          <span className="logo-wrapper">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/daft-prompt-logo.png"
              alt="Daft Prompt"
              className="logo-image"
              width={340}
              height={340}
            />
            <span className="logo-shimmer" aria-hidden="true" />
          </span>
        </h1>
        <p className="hero-subtitle">Research songs, ask musical questions, or compose a new sketch from reference traits — all from the same chat.</p>
      </section>

      <section className="chat-panel" aria-label="Conversation">
        <ChatThread
          messages={messages}
          busyLabel={activeWork}
          analysisProgress={analysisProgress}
        />
        {error ? (
          <p className="error-banner" role="alert">
            {error}
          </p>
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
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : `backend error ${response.status}`;
  } catch {
    return `backend error ${response.status}`;
  }
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
      + "Some sources can block or stall research; try again with a more specific artist and title."
    );
  }
  return message;
}
