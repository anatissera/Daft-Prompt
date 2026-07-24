"use client";

/** Full-screen architecture graph (helmet sidebar button): the UNIFIED map —
 *  conceptual pipeline (tools, director commitments, instrument agents,
 *  enforcement, players) annotated with the hard LangGraph identities
 *  (do_* nodes, pydantic schemas, models per role) plus the LLM stack and
 *  streaming transport. Hand-laid-out SVG: dependency-free and theme-true.
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
        <svg viewBox={`0 0 ${viewW} ${viewH}`} preserveAspectRatio="xMidYMin meet" className="graph-svg" role="img" aria-label={title}>
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
  // ── column 0: user surface ────────────────────────────────────────────
  { id: "prompt", x: 20, y: 330, w: 150, h: 52, title: "PROMPT", lines: ["user request"], accent: SILVER, kind: "input" },
  { id: "answer", x: 20, y: 470, w: 150, h: 66, title: "ANSWER", lines: ["evidence or websearch", "+ 1 small LLM call"], accent: SILVER, kind: "q&a" },
  { id: "edit", x: 20, y: 600, w: 150, h: 80, title: "EDIT", lines: ["plan: transpose, swap,", "add, remove, tempo", "applied deterministically"], accent: OXBLOOD, kind: "llm plan + pure fn" },

  // ── column 1: router ─────────────────────────────────────────────────
  { id: "intent", x: 230, y: 322, w: 160, h: 80, title: "INTENT", lines: ["do_intent · graph node", "IntentDecision schema", "compose vs replicate"], kind: "llm call" },

  // ── column 2: tools (research + replicate source) ────────────────────
  { id: "bitmidi", x: 450, y: 40, w: 170, h: 94, title: "BITMIDI SEARCH", lines: ["do_replicate · graph node", "find the exact song", "similarity guard on hits", "corrupt-file fallback"], accent: OXBLOOD, kind: "tool · http api" },
  { id: "websearch", x: 450, y: 170, w: 170, h: 58, title: "WEB SEARCH", lines: ["DuckDuckGo hits"], accent: TEAL, kind: "tool · http (no MCP)" },
  { id: "excerpts", x: 450, y: 262, w: 170, h: 58, title: "PAGE EXCERPTS", lines: ["real production prose"], accent: TEAL, kind: "tool · http fetch" },
  { id: "corpus", x: 450, y: 354, w: 170, h: 66, title: "CORPUS", lines: ["Lakh exemplars", "Groove drum patterns"], accent: TEAL, kind: "tool · offline index" },
  { id: "evidence", x: 450, y: 470, w: 170, h: 80, title: "SONG EVIDENCE", lines: ["MusicBrainz resolve", "CifraClub/HookTheory", "key + section chords"], accent: TEAL, kind: "tool · scrapers" },

  // ── column 3: planning ───────────────────────────────────────────────
  { id: "import", x: 690, y: 48, w: 180, h: 66, title: "MIDI IMPORT", lines: ["verbatim tracks", "no re-generation"], accent: OXBLOOD, kind: "tool · parser" },
  { id: "director", x: 690, y: 270, w: 190, h: 116, title: "DIRECTOR", lines: ["do_skeleton → BandSkeleton", "style + canon instruments", "feel + grids + registers", "roster + chords + plan"], kind: "graph node · llm · m3" },

  // ── column 4: performance ────────────────────────────────────────────
  { id: "fills", x: 940, y: 280, w: 190, h: 96, title: "INSTRUMENT AGENTS", lines: ["do_fills → InstrumentFill ×N", "one per instrument × slice", "ThreadPool(16) workers"], kind: "graph node · llm ×N · m2.5" },
  { id: "fallbacks", x: 940, y: 446, w: 190, h: 82, title: "FALLBACK CHAIN", lines: ["rich → minimal schema", "LLM-seeded 1-bar loop", "deterministic pattern"], accent: SILVER, kind: "llm + deterministic" },

  // ── column 5: materialization ────────────────────────────────────────
  { id: "compose", x: 1190, y: 256, w: 185, h: 124, title: "COMPOSER", lines: ["do_compose · pure fn", "grid/density/register", "enforcement (binding)", "patch reconciliation", "drums + bass roots"], kind: "graph node · deterministic" },
  { id: "render", x: 1190, y: 446, w: 185, h: 66, title: "RENDER", lines: ["song.mid + MusicXML", "artifacts + SSE done"], kind: "deterministic" },
  { id: "player", x: 1190, y: 600, w: 185, h: 82, title: "PLAYER", lines: ["SF3 soundfont (sampled)", "Tone.js synths (native)", "per-agent mixer + roll"], accent: TEAL, kind: "frontend · web audio" },

  // ── bottom lane: shared plumbing ─────────────────────────────────────
  { id: "llmstack", x: 690, y: 600, w: 190, h: 96, title: "LLM STACK", lines: ["make_llm(role) → fallbacks", "ChatOpenAI · opencode.ai", "minimax-m3 / m2.5 (fills)", "pydantic structured output"], kind: "langchain · http" },
  { id: "stream", x: 940, y: 600, w: 190, h: 94, title: "STREAMING", lines: ['graph.stream("values")', "→ FastAPI SSE", "chat proxy · upload direct", "→ pipeline stepper + deck"], accent: SILVER, kind: "langgraph · transport" },
];

const AGENT_EDGES: EdgeSpec[] = [
  { from: "prompt", to: "intent" },
  // replicate branch (top)
  { from: "intent", to: "bitmidi", label: "replicate", fromSide: "top", toSide: "left" },
  { from: "bitmidi", to: "import" },
  { from: "import", to: "render", fromSide: "right", toSide: "top", dashed: true },
  // research fan
  { from: "intent", to: "websearch", label: "compose" },
  { from: "websearch", to: "excerpts", dashed: true },
  { from: "intent", to: "corpus" },
  { from: "intent", to: "evidence", fromSide: "bottom", toSide: "left" },
  { from: "websearch", to: "director" },
  { from: "excerpts", to: "director" },
  { from: "corpus", to: "director" },
  { from: "evidence", to: "director", fromSide: "right", toSide: "bottom" },
  // main pipeline
  { from: "director", to: "fills" },
  { from: "fills", to: "fallbacks", dashed: true, label: "on failure" },
  { from: "fallbacks", to: "fills", dashed: true },
  { from: "fills", to: "compose" },
  { from: "compose", to: "render" },
  { from: "render", to: "player" },
  // question + edit branches
  { from: "intent", to: "answer", label: "question", fromSide: "bottom", toSide: "top" },
  { from: "evidence", to: "answer", dashed: true },
  { from: "intent", to: "edit", label: "edit", fromSide: "left", toSide: "right" },
  { from: "edit", to: "render", dashed: true, fromSide: "bottom", toSide: "bottom" },
  // shared plumbing
  { from: "director", to: "llmstack", dashed: true, fromSide: "bottom", toSide: "top" },
  { from: "fills", to: "llmstack", dashed: true, fromSide: "left", toSide: "top" },
  { from: "llmstack", to: "stream", dashed: true },
  { from: "render", to: "stream", dashed: true, fromSide: "bottom", toSide: "right" },
];

export function AgentGraphView() {
  return (
    <Graph
      title="AGENT MAP"
      subtitle="El sistema completo: del prompt a la canción — nodos del LangGraph (do_*), herramientas, compromisos del director, agentes de instrumento, enforcement y el stack LLM/streaming."
      nodes={AGENT_NODES}
      edges={AGENT_EDGES}
      viewW={1440}
      viewH={710}
    />
  );
}
