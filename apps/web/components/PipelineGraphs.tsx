"use client";

export type PipelineGraphMode = "agent" | "langgraph";

interface PipelineNode {
  title: string;
  kind: string;
  detail: string;
  meta?: string;
}

interface PipelineLane {
  label: string;
  nodes: PipelineNode[];
}

interface PipelineGraphSpec {
  title: string;
  subtitle: string;
  lanes: PipelineLane[];
}

const AGENT_GRAPH: PipelineGraphSpec = {
  title: "Agent Map",
  subtitle: "Conceptual path from chat prompt to sourced answer, playable view, or generated MIDI song.",
  lanes: [
    {
      label: "Conversation",
      nodes: [
        {
          title: "User prompt",
          kind: "input",
          detail: "Song question, playable tab/key request, artist style prompt, composition, or edit.",
          meta: "chat-first surface",
        },
        {
          title: "Chat router",
          kind: "application",
          detail: "Chooses evidence lookup, artist profiling, playable rendering, composition, or SongState edit.",
          meta: "ChatMusic + ChatAgent",
        },
        {
          title: "Session context",
          kind: "memory",
          detail: "Carries current SongKnowledgeProfile, ArtistStyleProfile, generated song, and compact conversation notes.",
        },
      ],
    },
    {
      label: "Public Evidence",
      nodes: [
        {
          title: "Songsterr connector",
          kind: "port adapter",
          detail: "Primary tab, tuning, part, and metadata evidence when available.",
          meta: "source attributed",
        },
        {
          title: "Tab/chord/meta pages",
          kind: "port adapter",
          detail: "Supplemental chords, sections, credits, album facts, and conflicts.",
          meta: "confidence kept visible",
        },
        {
          title: "Evidence fusion",
          kind: "application",
          detail: "Projects EvidenceClaim, PlayablePart, ToneProfile, and uncertainty into provider-agnostic profiles.",
          meta: "SongKnowledgeProfile",
        },
        {
          title: "Artist style builder",
          kind: "application",
          detail: "Resolves artist, selects representative tab-available songs, aggregates style traits and sources.",
          meta: "ArtistStyleProfile",
        },
      ],
    },
    {
      label: "Band + Output",
      nodes: [
        {
          title: "CompositionBrief",
          kind: "domain",
          detail: "Transforms chat instructions plus song, artist, album, genre, and playable preservation evidence into band guidance.",
        },
        {
          title: "Director",
          kind: "LLM node",
          detail: "Sets header, roster, semantic patches, and composition groups for the dynamic band.",
          meta: "DirectorOutput",
        },
        {
          title: "Instrument agents",
          kind: "LLM batch",
          detail: "Guitar, bass, keys, synths, or requested roles negotiate through shared SongState; drums use deterministic patterns and transition fills.",
          meta: "InstrumentTurnOutput + drum skills",
        },
        {
          title: "Arbiter + renderers",
          kind: "deterministic + LLM",
          detail: "Finalizes negotiation, renders MIDI/MusicXML, tabs, piano keys, and piano roll views.",
          meta: "source notes stay attached",
        },
      ],
    },
  ],
};

const LANGGRAPH_GRAPH: PipelineGraphSpec = {
  title: "LangGraph Architecture",
  subtitle: "Implementation path through Next.js, FastAPI, structured tool routing, and the band StateGraph.",
  lanes: [
    {
      label: "HTTP Boundary",
      nodes: [
        {
          title: "Next /api/chat",
          kind: "proxy route",
          detail: "Forwards message, current song, compact conversation context, and artist_style_profiles.",
        },
        {
          title: "FastAPI /chat",
          kind: "thin route",
          detail: "Validates ChatRequest, invokes ChatMusic, then attaches generated artifact URLs when needed.",
        },
        {
          title: "FastAPI streams",
          kind: "SSE",
          detail: "/compose/stream and research streams emit progress while use cases keep business logic.",
        },
      ],
    },
    {
      label: "Router + Tools",
      nodes: [
        {
          title: "ChatMusic gates",
          kind: "application",
          detail: "Handles obvious tab/key requests, artist profile reuse, and generated SongState edits deterministically.",
        },
        {
          title: "ChatAgentDecision",
          kind: "structured output",
          detail: "LLM classifier selects research_song, get_tab_excerpt, answer_profile, request_composition, or clarify.",
        },
        {
          title: "Music tools",
          kind: "application API",
          detail: "Tool calls stay behind use cases and ports; scrapers never leak into domain or agents.",
        },
      ],
    },
    {
      label: "Band StateGraph",
      nodes: [
        {
          title: "StateGraph(BandState)",
          kind: "LangGraph",
          detail: "START -> director -> instruments with conditional convergence edges.",
        },
        {
          title: "Instrument subgraph",
          kind: "parallel batch",
          detail: "Dispatches instrument_turn nodes for the current composition group.",
        },
        {
          title: "Convergence edges",
          kind: "conditional",
          detail: "Routes to batch_next_round, advance_batch, or arbiter based on shared negotiation state.",
        },
        {
          title: "Arbiter END",
          kind: "LangGraph node",
          detail: "Resolves pending requests and returns canonical SongState for render projections.",
        },
      ],
    },
    {
      label: "LLM Stack",
      nodes: [
        {
          title: "make_llm(role)",
          kind: "provider factory",
          detail: "Builds role-specific model plan and wraps it in FallbackChatModel.",
        },
        {
          title: "with_structured_output",
          kind: "schema binding",
          detail: "Binds ChatAgentDecision, DirectorOutput, InstrumentOutput, InstrumentRevisionOutput, and ArbiterOutput.",
        },
        {
          title: "Recovery parser",
          kind: "fallback",
          detail: "Attempts raw chat recovery before surfacing provider/model error details.",
        },
      ],
    },
  ],
};

const GRAPH_BY_MODE: Record<PipelineGraphMode, PipelineGraphSpec> = {
  agent: AGENT_GRAPH,
  langgraph: LANGGRAPH_GRAPH,
};

interface PipelineGraphsProps {
  mode: PipelineGraphMode;
  onClose: () => void;
}

export default function PipelineGraphs({ mode, onClose }: PipelineGraphsProps) {
  const graph = GRAPH_BY_MODE[mode];

  return (
    <div className="pipeline-graph-overlay" role="presentation">
      <section
        className="pipeline-graph-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="pipeline-graph-title"
      >
        <header className="pipeline-graph-header">
          <div>
            <p className="pipeline-graph-eyebrow">{mode === "agent" ? "AG" : "LC"}</p>
            <h2 id="pipeline-graph-title">{graph.title}</h2>
            <p>{graph.subtitle}</p>
          </div>
          <button
            type="button"
            className="pipeline-graph-close"
            aria-label="Close pipeline diagram"
            title="Close"
            onClick={onClose}
          >
            x
          </button>
        </header>

        <div className="pipeline-graph-grid">
          {graph.lanes.map((lane) => (
            <section className="pipeline-graph-lane" key={lane.label} aria-label={lane.label}>
              <h3>{lane.label}</h3>
              <ol>
                {lane.nodes.map((node) => (
                  <li className="pipeline-graph-node" key={`${lane.label}-${node.title}`}>
                    <span className="pipeline-graph-kind">{node.kind}</span>
                    <strong>{node.title}</strong>
                    <span>{node.detail}</span>
                    {node.meta ? <small>{node.meta}</small> : null}
                  </li>
                ))}
              </ol>
            </section>
          ))}
        </div>
      </section>
    </div>
  );
}
