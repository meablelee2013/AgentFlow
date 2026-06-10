import { useState, useRef, useEffect } from "react";
import { Send, Loader2, GitFork, BarChart3, CheckCircle2, XCircle, Clock, ChevronDown } from "lucide-react";

interface SubtaskInfo {
  id: string;
  description: string;
  executor: string;
  input: Record<string, unknown>;
  expected_output: string;
  status: "pending" | "running" | "completed" | "failed";
  result: unknown;
  error: string | null;
  duration_ms: number;
}

interface TraceInfo {
  execution_id?: string;
  total: number;
  completed: number;
  failed: number;
  total_duration_ms: number;
  subtasks?: SubtaskInfo[];
  aggregated_output?: string;
}

interface DecomposeResult {
  goal: string;
  subtasks: SubtaskInfo[];
  aggregated_output: string;
  execution_trace: TraceInfo | null;
  enabled_capabilities: string[];
  error?: string;
}

function SubtaskCard({ st }: { st: SubtaskInfo }) {
  const [expanded, setExpanded] = useState(false);
  const done = st.status === "completed";
  const fail = st.status === "failed";
  const running = st.status === "running";

  return (
    <div className={`border rounded-xl overflow-hidden transition-all ${
      done ? "border-emerald-200 bg-emerald-50/30" :
      fail ? "border-red-200 bg-red-50/30" :
      "border-border bg-white"
    }`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50/50 transition-colors"
      >
        <span className="shrink-0">
          {done ? <CheckCircle2 size={16} className="text-emerald-500" /> :
           fail ? <XCircle size={16} className="text-red-400" /> :
           running ? <Loader2 size={16} className="text-blue-400 animate-spin" /> :
           <Clock size={16} className="text-gray-300" />}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-ink truncate">{st.description}</p>
          <p className="text-[10px] text-gray-400 font-mono">{st.executor}</p>
        </div>
        <span className="text-[10px] text-gray-400 font-mono shrink-0">{st.duration_ms}ms</span>
        <ChevronDown size={12} className={`text-gray-300 transition-transform ${expanded ? "rotate-180" : ""}`} />
      </button>

      {expanded && (
        <div className="border-t border-border px-4 py-3 space-y-2 text-[10px]">
          <div>
            <span className="font-semibold text-gray-400 uppercase tracking-wider">Input</span>
            <pre className="mt-1 p-2 bg-gray-100 rounded font-mono text-gray-600 whitespace-pre-wrap break-all max-h-24 overflow-y-auto">
              {JSON.stringify(st.input, null, 2)}
            </pre>
          </div>
          {st.expected_output && (
            <div>
              <span className="font-semibold text-gray-400 uppercase tracking-wider">Expected</span>
              <p className="text-gray-500 mt-0.5">{st.expected_output}</p>
            </div>
          )}
          {st.result != null && (
            <div>
              <span className="font-semibold text-gray-400 uppercase tracking-wider">Result</span>
              <pre className="mt-1 p-2 bg-gray-100 rounded font-mono text-gray-600 whitespace-pre-wrap break-all max-h-48 overflow-y-auto">
                {typeof st.result === "string" ? st.result : JSON.stringify(st.result, null, 2)}
              </pre>
            </div>
          )}
          {st.error && (
            <div>
              <span className="font-semibold text-red-400 uppercase tracking-wider">Error</span>
              <p className="text-red-500 mt-0.5">{st.error}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function DecomposeTestChat() {
  const [goal, setGoal] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<DecomposeResult | null>(null);
  const [history, setHistory] = useState<DecomposeResult[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [result, history]);

  const handleSubmit = async () => {
    const trimmed = goal.trim();
    if (!trimmed || running) return;

    setRunning(true);
    setResult(null);

    try {
      const resp = await fetch("/api/v1/workflows/test-decompose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal: trimmed }),
      });
      const data: DecomposeResult = await resp.json();
      setResult(data);
      setHistory(prev => [data, ...prev]);
    } catch (e: unknown) {
      setResult({
        goal: trimmed,
        error: String(e),
        subtasks: [],
        aggregated_output: "",
        execution_trace: null,
        enabled_capabilities: [],
      });
    }
    setRunning(false);
    setGoal("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Current display data
  const current = result;
  const trace = current?.execution_trace;
  const hasError = !!current?.error;

  return (
    <div className="flex flex-col h-full max-w-4xl mx-auto">
      {/* Header */}
      <div className="px-6 py-4 border-b border-border bg-white shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-amber-100 flex items-center justify-center">
            <GitFork size={18} className="text-amber-600" />
          </div>
          <div>
            <h1 className="text-base font-bold text-ink">Decompose Test Playground</h1>
            <p className="text-xs text-gray-400">
              Type a complex goal — the system will decompose, fan-out, and aggregate automatically
            </p>
          </div>
        </div>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {/* Empty state */}
        {!current && history.length === 0 && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center max-w-md">
              <GitFork size={48} className="text-gray-200 mx-auto mb-4" />
              <h2 className="text-lg font-semibold text-ink/50 mb-2">Task Decomposition Tester</h2>
              <p className="text-sm text-gray-400">
                Try: "Research Tesla's Q1 2025 performance and compare with BYD"<br />
                or "Analyze the impact of AI on healthcare and write a summary"
              </p>
            </div>
          </div>
        )}

        {/* History results (collapsed) */}
        {history.length > 0 && !current && (
          <div className="text-center text-sm text-gray-400 py-8">
            ✓ {history.length} test(s) completed. Enter a new goal below.
          </div>
        )}

        {/* Current result */}
        {current && (
          <div className="space-y-4 animate-in fade-in">
            {/* Goal bubble */}
            <div className="flex justify-end">
              <div className="max-w-[80%] bg-ink text-white px-4 py-3 rounded-2xl rounded-br-md">
                <p className="text-xs font-medium opacity-60 mb-0.5">Goal</p>
                <p className="text-sm">{current.goal}</p>
              </div>
            </div>

            {/* Error */}
            {hasError && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4">
                <p className="text-sm text-red-600 font-medium">❌ {current.error}</p>
              </div>
            )}

            {/* Enabled capabilities */}
            {current.enabled_capabilities?.length > 0 && (
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] text-gray-400 font-mono uppercase">Capabilities:</span>
                {current.enabled_capabilities.map(cap => (
                  <span key={cap} className="text-[10px] bg-gray-100 px-2 py-0.5 rounded font-mono text-gray-500">{cap}</span>
                ))}
              </div>
            )}

            {/* Decomposition plan */}
            {current.subtasks.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <GitFork size={14} className="text-amber-500" />
                  <span className="text-xs font-semibold text-ink">
                    Decomposed into {current.subtasks.length} subtasks
                  </span>
                  {trace && (
                    <span className="text-[10px] text-gray-400 font-mono ml-auto">
                      {trace.completed}/{trace.total} completed · {trace.total_duration_ms}ms
                    </span>
                  )}
                </div>
                <div className="space-y-2">
                  {current.subtasks.map(st => (
                    <SubtaskCard key={st.id} st={st} />
                  ))}
                </div>
              </div>
            )}

            {/* Aggregated output */}
            {current.aggregated_output && (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <BarChart3 size={14} className="text-emerald-500" />
                  <span className="text-xs font-semibold text-ink">Aggregated Report</span>
                </div>
                <div className="bg-white border border-border rounded-xl p-5 prose prose-sm max-w-none">
                  <div className="text-sm leading-relaxed text-ink/80 whitespace-pre-wrap">
                    {current.aggregated_output}
                  </div>
                </div>
              </div>
            )}

            {/* Execution trace summary */}
            {trace && (
              <div className="bg-gray-50 border border-border rounded-xl p-4 flex items-center gap-4 text-xs">
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 size={12} className="text-emerald-500" />
                  <span className="font-mono text-emerald-600">{trace.completed}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <XCircle size={12} className="text-red-400" />
                  <span className="font-mono text-red-500">{trace.failed}</span>
                </div>
                <div className="flex items-center gap-1.5 ml-auto">
                  <Clock size={12} className="text-gray-400" />
                  <span className="font-mono text-gray-500">{trace.total_duration_ms}ms total</span>
                </div>
              </div>
            )}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="px-6 py-4 border-t border-border bg-white shrink-0">
        <div className="flex gap-2">
          <textarea
            value={goal}
            onChange={e => setGoal(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={running}
            placeholder="Enter a complex goal to decompose..."
            rows={2}
            className="flex-1 px-4 py-3 text-sm border border-border rounded-xl bg-warm
                       focus:outline-none focus:ring-2 focus:ring-amber-200 resize-none
                       placeholder:text-gray-300 disabled:opacity-50"
          />
          <button
            onClick={handleSubmit}
            disabled={running || !goal.trim()}
            className="shrink-0 w-12 h-12 rounded-xl bg-ink text-white flex items-center justify-center
                       hover:bg-slate-hover disabled:opacity-30 transition-colors self-end"
          >
            {running ? <Loader2 size={18} className="animate-spin" /> : <Send size={16} />}
          </button>
        </div>
      </div>
    </div>
  );
}
