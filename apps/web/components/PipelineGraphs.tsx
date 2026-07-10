"use client";

/** Full-screen graph views toggled from the sidebar square buttons:
 *  - AgentGraphView  (helmet): the conceptual pipeline — every component the
 *    agent has at its disposal from prompt to rendered song (tools, composer,
 *    fallbacks, players).
 *  - LangGraphView   (LC): the hard LangChain/LangGraph architecture — the
 *    actual StateGraph nodes, conditional edges, LLM stack and streaming.
 *  Both are hand-laid-out SVGs so they stay dependency-free and theme-true.
 */

interface NodeSpec {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  title: string;
  lines?: string[];
  accent?: string; // chip fill color
  /** What this thing IS: "llm call", "tool · http", "langgraph node", … —
   *  rendered as a floating type tag over the chip's top-left corner. */
  kind?: string;
}

interface EdgeSpec {
  from: string;
  to: string;
  label?: string;
  dashed?: boolean;
  /** Explicit anchor sides so edges leave/enter where it reads best. */
  fromSide?: "left" | "right" | "top" | "bottom";
  toSide?: "left" | "right" | "top" | "bottom";
}

const GOLD = "#f3c45a";
const SILVER = "#c9cdd8";
const OXBLOOD = "#c96a5a";
const TEAL = "#6ac9b8";

function anchor(n: NodeSpec, side: "left" | "right" | "top" | "bottom"): [number, number] {
  switch (side) {
    case "left": return [n.x, n.y + n.h / 2];
    case "right": return [n.x + n.w, n.y + n.h / 2];
    case "top": return [n.x + n.w / 2, n.y];
    case "bottom": return [n.x + n.w / 2, n.y + n.h];
  }
}

function autoSides(a: NodeSpec, b: NodeSpec): ["left" | "right" | "top" | "bottom", "left" | "right" | "top" | "bottom"] {
  const dx = (b.x + b.w / 2) - (a.x + a.w / 2);
  const dy = (b.y + b.h / 2) - (a.y + a.h / 2);
  if (Math.abs(dx) >= Math.abs(dy)) return dx > 0 ? ["right", "left"] : ["left", "right"];
  return dy > 0 ? ["bottom", "top"] : ["top", "bottom"];
}

function Graph({ title, subtitle, nodes, edges, viewW, viewH }: {
  title: string;
  subtitle: string;
  nodes: NodeSpec[];
  edges: EdgeSpec[];
  viewW: number;
  viewH: number;
}) {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  return (
    <div className="graph-view">
      <div className="graph-view-header">
        <h2 className="graph-view-title">{title}</h2>
        <p className="graph-view-subtitle">{subtitle}</p>
      </div>
      <div className="graph-view-canvas">
        <svg viewBox={`0 0 ${viewW} ${viewH}`} className="graph-svg" role="img" aria-label={title}>
          <defs>
            <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 8 4 L 0 8 z" fill={GOLD} />
            </marker>
            <marker id="arrow-dim" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 8 4 L 0 8 z" fill="rgba(201,205,216,0.55)" />
            </marker>
          </defs>
          {edges.map((e, i) => {
            const a = byId.get(e.from);
            const b = byId.get(e.to);
            if (!a || !b) return null;
            const [sa, sb] = e.fromSide && e.toSide ? [e.fromSide, e.toSide] : autoSides(a, b);
            const [x1, y1] = anchor(a, e.fromSide ?? sa);
            const [x2, y2] = anchor(b, e.toSide ?? sb);
            const mx = (x1 + x2) / 2;
            const my = (y1 + y2) / 2;
            // Gentle orthogonal-ish curve: pull the control points along the
            // exit/entry axes so lines flow instead of cutting across nodes.
            const horizontalExit = sa === "left" || sa === "right";
            const c1x = horizontalExit ? mx : x1;
            const c1y = horizontalExit ? y1 : my;
            const c2x = horizontalExit ? mx : x2;
            const c2y = horizontalExit ? y2 : my;
            return (
              <g key={i}>
                <path
                  d={`M ${x1} ${y1} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${x2} ${y2}`}
                  fill="none"
                  stroke={e.dashed ? "rgba(201,205,216,0.55)" : GOLD}
                  strokeWidth={1.4}
                  strokeDasharray={e.dashed ? "5 4" : undefined}
                  markerEnd={e.dashed ? "url(#arrow-dim)" : "url(#arrow)"}
                  opacity={e.dashed ? 0.8 : 0.9}
                />
                {e.label ? (
                  <text x={mx} y={my - 6} textAnchor="middle" className="graph-edge-label">{e.label}</text>
                ) : null}
              </g>
            );
          })}
          {nodes.map((n) => (
            <g key={n.id}>
              {/* Solid color chips with dark text, floating directly on the
                  page background. */}
              <rect
                x={n.x} y={n.y} width={n.w} height={n.h} rx={10}
                fill={n.accent ?? GOLD}
                stroke="rgba(0,0,0,0.45)"
                strokeWidth={1}
              />
              <text x={n.x + n.w / 2} y={n.y + 21} textAnchor="middle" className="graph-node-title" fill="#14120c">
                {n.title}
              </text>
              {(n.lines ?? []).map((line, i) => (
                <text key={i} x={n.x + n.w / 2} y={n.y + 38 + i * 14} textAnchor="middle" className="graph-node-line" fill="rgba(0,0,0,0.66)">
                  {line}
                </text>
              ))}
              {n.kind ? (
                <g>
                  <rect
                    x={n.x + 6}
                    y={n.y - 9}
                    width={n.kind.length * 5.6 + 12}
                    height={15}
                    rx={7.5}
                    fill="#0b0c10"
                    stroke={n.accent ?? GOLD}
                    strokeWidth={0.8}
                  />
                  <text
                    x={n.x + 12}
                    y={n.y + 2}
                    className="graph-node-kind"
                    fill={n.accent ?? GOLD}
                  >
                    {n.kind}
                  </text>
                </g>
              ) : null}
            </g>
          ))}
        </svg>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helmet view: the agent + composer + tools, prompt → song.
// ---------------------------------------------------------------------------

const AGENT_NODES: NodeSpec[] = [
  { id: "prompt", x: 20, y: 320, w: 120, h: 52, title: "PROMPT", lines: ["user request"], accent: SILVER, kind: "input" },
  { id: "intent", x: 190, y: 320, w: 150, h: 66, title: "INTENT", lines: ["compose vs replicate", "LLM classifier"], kind: "llm call" },

  // replicate branch (top)
  { id: "bitmidi", x: 400, y: 60, w: 160, h: 66, title: "BITMIDI SEARCH", lines: ["find the exact song", "download .mid"], accent: OXBLOOD, kind: "tool · http api" },
  { id: "import", x: 620, y: 60, w: 150, h: 66, title: "MIDI IMPORT", lines: ["verbatim tracks", "no re-generation"], accent: OXBLOOD, kind: "tool · parser" },

  // research tools
  { id: "websearch", x: 400, y: 190, w: 160, h: 58, title: "WEB SEARCH", lines: ["DuckDuckGo hits"], accent: TEAL, kind: "tool · http (no MCP)" },
  { id: "excerpts", x: 400, y: 280, w: 160, h: 58, title: "PAGE EXCERPTS", lines: ["real production prose"], accent: TEAL, kind: "tool · http fetch" },
  { id: "corpus", x: 400, y: 370, w: 160, h: 66, title: "CORPUS", lines: ["Lakh exemplars", "Groove drum patterns"], accent: TEAL, kind: "tool · offline index" },

  // director
  { id: "director", x: 640, y: 240, w: 190, h: 116, title: "DIRECTOR", lines: ["style summary", "canonical instruments", "rhythmic feel", "roster + chords + form"], kind: "llm call · minimax-m3" },

  // fills
  { id: "fills", x: 900, y: 240, w: 190, h: 96, title: "INSTRUMENT AGENTS", lines: ["one per instrument", "× section slice", "16 parallel workers"], kind: "llm calls ×N · m2.5" },
  { id: "fallbacks", x: 900, y: 400, w: 190, h: 82, title: "FALLBACK CHAIN", lines: ["rich → minimal schema", "LLM-seeded 1-bar loop", "deterministic pattern"], accent: SILVER, kind: "llm + deterministic" },

  // compose + render
  { id: "compose", x: 1160, y: 240, w: 180, h: 96, title: "COMPOSER", lines: ["patch resolution", "drum synthesis", "bass on chord roots"], kind: "deterministic" },
  { id: "render", x: 1160, y: 400, w: 180, h: 66, title: "RENDER", lines: ["song.mid + MusicXML", "artifacts + SSE done"], kind: "deterministic" },
  { id: "player", x: 900, y: 540, w: 190, h: 82, title: "PLAYER", lines: ["SF3 soundfont (sampled)", "Tone.js synths (native)", "per-agent mixer"], accent: TEAL, kind: "frontend · web audio" },
];

const AGENT_EDGES: EdgeSpec[] = [
  { from: "prompt", to: "intent" },
  { from: "intent", to: "bitmidi", label: "replicate", fromSide: "top", toSide: "left" },
  { from: "bitmidi", to: "import" },
  { from: "import", to: "render", fromSide: "right", toSide: "top", dashed: true },
  { from: "intent", to: "websearch", label: "compose" },
  { from: "intent", to: "corpus" },
  { from: "websearch", to: "excerpts", dashed: true },
  { from: "websearch", to: "director" },
  { from: "excerpts", to: "director" },
  { from: "corpus", to: "director" },
  { from: "director", to: "fills" },
  { from: "fills", to: "fallbacks", dashed: true, label: "on failure" },
  { from: "fallbacks", to: "fills", dashed: true },
  { from: "fills", to: "compose" },
  { from: "compose", to: "render" },
  { from: "render", to: "player" },
];

export function AgentGraphView() {
  return (
    <Graph
      title="AGENT MAP"
      subtitle="Todo lo que el agente tiene a disposición desde el prompt hasta la canción — herramientas, director, agentes de instrumento y compositor."
      nodes={AGENT_NODES}
      edges={AGENT_EDGES}
      viewW={1380}
      viewH={660}
    />
  );
}

// ---------------------------------------------------------------------------
// LC view: the hard LangChain / LangGraph architecture.
// ---------------------------------------------------------------------------

const LC_NODES: NodeSpec[] = [
  // StateGraph lane
  { id: "start", x: 20, y: 90, w: 100, h: 46, title: "START", accent: SILVER, kind: "entry point" },
  { id: "do_intent", x: 170, y: 80, w: 150, h: 62, title: "do_intent", lines: ["IntentDecision", "conditional edges"], kind: "graph node · llm" },
  { id: "do_replicate", x: 380, y: 20, w: 160, h: 56, title: "do_replicate", lines: ["Bitmidi → import"], accent: OXBLOOD, kind: "graph node · tools" },
  { id: "do_research", x: 380, y: 110, w: 160, h: 56, title: "do_research", lines: ["no LLM — pure tools"], accent: TEAL, kind: "graph node · tools" },
  { id: "do_skeleton", x: 600, y: 110, w: 160, h: 62, title: "do_skeleton", lines: ["BandSkeleton", "retry on parse-None"], kind: "graph node · llm" },
  { id: "do_fills", x: 820, y: 110, w: 160, h: 62, title: "do_fills", lines: ["InstrumentFill × N", "ThreadPool(16)"], kind: "graph node · llm ×N" },
  { id: "do_compose", x: 1040, y: 110, w: 160, h: 56, title: "do_compose", lines: ["BandSpec → SongState"], kind: "graph node · pure fn" },
  { id: "end", x: 1260, y: 116, w: 90, h: 46, title: "END", accent: SILVER, kind: "terminal" },

  // LLM infrastructure lane
  { id: "make_llm", x: 170, y: 300, w: 160, h: 62, title: "make_llm(role)", lines: ["director / instrument", "role-scoped models"], kind: "factory · python" },
  { id: "fallback", x: 400, y: 300, w: 180, h: 62, title: "FallbackChatModel", lines: ["provider chain", "cancel-aware httpx"], kind: "langchain wrapper" },
  { id: "chatopenai", x: 650, y: 300, w: 190, h: 76, title: "ChatOpenAI", lines: ["opencode.ai gateway", "minimax-m3 (director)", "minimax-m2.5 (fills)"], kind: "langchain client · http" },
  { id: "structured", x: 910, y: 300, w: 210, h: 76, title: "with_structured_output", lines: ["pydantic schemas:", "IntentDecision · BandSkeleton", "InstrumentFill · _MinimalFill"], kind: "langchain api · pydantic" },

  // streaming lane
  { id: "stream", x: 170, y: 470, w: 200, h: 62, title: 'graph.stream("values")', lines: ["progress event per node"], accent: TEAL, kind: "langgraph api" },
  { id: "fastapi", x: 440, y: 470, w: 170, h: 62, title: "FastAPI SSE", lines: ["/chat/stream", "CancelToken per request"], accent: TEAL, kind: "backend endpoint" },
  { id: "nextproxy", x: 680, y: 470, w: 170, h: 62, title: "Next.js proxy", lines: ["same-origin SSE relay", "no undici timeouts"], accent: TEAL, kind: "frontend route" },
  { id: "ui", x: 920, y: 470, w: 150, h: 56, title: "UI", lines: ["pipeline stepper", "song deck"], accent: SILVER, kind: "react" },
];

const LC_EDGES: EdgeSpec[] = [
  { from: "start", to: "do_intent" },
  { from: "do_intent", to: "do_replicate", label: "replicate" },
  { from: "do_intent", to: "do_research", label: "compose" },
  { from: "do_replicate", to: "do_research", label: "miss", dashed: true },
  { from: "do_replicate", to: "end", fromSide: "right", toSide: "top", dashed: true, label: "hit" },
  { from: "do_research", to: "do_skeleton" },
  { from: "do_skeleton", to: "do_fills" },
  { from: "do_fills", to: "do_compose" },
  { from: "do_compose", to: "end" },

  { from: "do_intent", to: "make_llm", dashed: true, fromSide: "bottom", toSide: "top" },
  { from: "do_skeleton", to: "chatopenai", dashed: true, fromSide: "bottom", toSide: "top" },
  { from: "do_fills", to: "structured", dashed: true, fromSide: "bottom", toSide: "top" },
  { from: "make_llm", to: "fallback" },
  { from: "fallback", to: "chatopenai" },
  { from: "chatopenai", to: "structured" },

  { from: "stream", to: "fastapi" },
  { from: "fastapi", to: "nextproxy" },
  { from: "nextproxy", to: "ui" },
  { from: "make_llm", to: "stream", dashed: true, fromSide: "bottom", toSide: "top" },
];

export function LangGraphView() {
  return (
    <Graph
      title="LANGGRAPH ARCHITECTURE"
      subtitle="La arquitectura dura: StateGraph con edges condicionales, stack LLM con structured output pydantic, y el camino de streaming hasta la UI."
      nodes={LC_NODES}
      edges={LC_EDGES}
      viewW={1380}
      viewH={570}
    />
  );
}
