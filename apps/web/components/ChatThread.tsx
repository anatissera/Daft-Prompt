"use client";

import { useCallback, useEffect, useLayoutEffect, useRef } from "react";
import type { ChatMessage } from "@/lib/chatTypes";
import AnalysisResultBlock from "@/components/AnalysisResultBlock";
import TabExcerptBlock from "@/components/TabExcerptBlock";
import MelodyPreviewBlock from "@/components/MelodyPreviewBlock";
import ChordChartBlock from "@/components/ChordChartBlock";
import GeneratedSongBlock from "@/components/GeneratedSongBlock";
import Typewriter from "@/components/Typewriter";
import AnalysisProgressChecklist from "@/components/AnalysisProgressChecklist";
import type { AnalysisStageState } from "@/lib/analysisProgress.mjs";
import { WORKFLOW_STAGES, activeWorkflowStage, type ChatWorkflow } from "@/lib/workflowProgress.mjs";
import { isNearConversationBottom } from "@/lib/chatAutoFollow.mjs";

interface ChatThreadProps {
  messages: ChatMessage[];
  busyLabel: string | null;
  busyElapsedMs?: number;
  onCancel?: () => void;
  analysisProgress?: AnalysisStageState[] | null;
  workflow?: ChatWorkflow | null;
}

// Rough timeline of the compose pipeline. We can't show this list until the
// classifier on the server has decided the prompt is in scope (music) — until
// then the request might bounce back as off-topic in < 1s and we'd flash a
// fake list of stages. Wait until the classifier window has clearly passed
// AND the busy label is the "Thinking…" one (analyze uses its own label).
export default function ChatThread({ messages, busyLabel, busyElapsedMs, onCancel, analysisProgress, workflow }: ChatThreadProps) {
  const threadRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const followingRef = useRef(true);
  const previousMessageCountRef = useRef(messages.length);
  const elapsedSec = (busyElapsedMs ?? 0) / 1000;
  const stages = workflow ? WORKFLOW_STAGES[workflow] : [];
  const activeIdx = activeWorkflowStage(elapsedSec, stages.length);
  const scrollToLatest = useCallback(() => {
    const thread = threadRef.current;
    if (!thread) return;
    thread.scrollTop = thread.scrollHeight;
  }, []);

  useLayoutEffect(() => {
    const lastMessage = messages[messages.length - 1];
    const userSent = messages.length > previousMessageCountRef.current && lastMessage?.role === "user";
    previousMessageCountRef.current = messages.length;
    if (userSent) followingRef.current = true;
    if (followingRef.current) scrollToLatest();
  }, [messages, busyLabel, scrollToLatest]);

  useEffect(() => {
    const content = contentRef.current;
    if (!content || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      if (followingRef.current) scrollToLatest();
    });
    observer.observe(content);
    return () => observer.disconnect();
  }, [scrollToLatest]);

  function handleScroll() {
    const thread = threadRef.current;
    if (!thread) return;
    followingRef.current = isNearConversationBottom(thread);
  }

  return (
    <div ref={threadRef} className="chat-thread" data-testid="chat-thread" onScroll={handleScroll} aria-live="polite">
      <div ref={contentRef} className="chat-thread-content">
      {messages.map((message) => (
        <article key={message.id} className={`chat-message chat-message-${message.role}`}>
          <span className="chat-role">{message.role}</span>
          <p>
            <span className="bubble-sparkle" aria-hidden="true">✦</span>
            {message.role === "assistant"
              ? <Typewriter text={message.text} />
              : message.text}
          </p>
          {message.meta ? <span className="chat-meta">{message.meta}</span> : null}
          {message.kind === "analysis" ? <AnalysisResultBlock profile={message.profile} /> : null}
          {message.kind === "tab" ? <TabExcerptBlock excerpt={message.excerpt} /> : null}
          {message.kind === "melody" ? <MelodyPreviewBlock melody={message.melody} /> : null}
          {message.kind === "chords" ? <ChordChartBlock rows={message.rows} /> : null}
          {message.kind === "composition" ? <GeneratedSongBlock message={message} /> : null}
        </article>
      ))}
      {busyLabel ? (
        <article className="chat-message chat-message-system">
          <span className="chat-role">working</span>
          <div className="busy-block">
            <p className="busy-header">
              <span className="sound-wave" aria-hidden="true">
                <span /><span /><span /><span /><span />
                <span /><span /><span /><span /><span />
                <span /><span /><span /><span /><span />
              </span>
              {busyLabel}
              {typeof busyElapsedMs === "number" ? (
                <span className="chat-meta-inline"> · {(busyElapsedMs / 1000).toFixed(1)}s</span>
              ) : null}
              {onCancel ? (
                <button type="button" className="cancel-button" onClick={onCancel}>
                  Stop
                </button>
              ) : null}
            </p>
            {analysisProgress ? (
              <AnalysisProgressChecklist stages={analysisProgress} />
            ) : null}
            {stages.length > 0 && !analysisProgress ? (
              <ol className="pipeline-steps">
                {stages.map((label, idx) => {
                  const state =
                    idx < activeIdx ? "done" : idx === activeIdx ? "active" : "pending";
                  return (
                    <li key={label} className={`pipeline-step pipeline-step-${state}`}>
                      <span className="pipeline-step-marker" aria-hidden="true">
                        {state === "done" ? "✓" : state === "active" ? "›" : "·"}
                      </span>
                      <span className="pipeline-step-label">{label}</span>
                    </li>
                  );
                })}
              </ol>
            ) : null}
          </div>
        </article>
      ) : null}
      <div className="chat-scroll-anchor" data-testid="chat-scroll-anchor" aria-hidden="true" />
      </div>
    </div>
  );
}
