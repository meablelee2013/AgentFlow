import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Loader2, GitFork, BarChart3, CheckCircle2, XCircle, Clock, ChevronDown, Brain, Zap, FileText } from "lucide-react";

// ── Types ──────────────────────────────────────────────────

type Phase = "idle" | "decomposing" | "executing" | "aggregating" | "done" | "error";

interface LiveSubtask {
  id: string;
  description: string;
  executor: string;
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
}

interface AggregatedData {
  aggregated_output: string;
  execution_trace: TraceInfo | null;
}

// ── Helpers ────────────────────────────────────────────────

function safeStringify(obj: unknown): string {
  try { return JSON.stringify(obj, null, 2); }
  catch { return String(obj); }
}

// ── Phase Banner ───────────────────────────────────────────

function PhaseBanner({ phase, subtaskCount }: { phase: Phase; subtaskCount: number }) {
  const configs: Record<Phase, { icon: typeof Brain; label: string; color: string; bg: string }> = {
    idle:    { icon: Brain,   label: "Ready",                 color: "text-gray-400",   bg: "bg-gray-50" },
    decomposing: { icon: Brain,  label: "Decomposing — analyzing goal...", color: "text-amber-600",  bg: "bg-amber-50" },
    executing:   { icon: Zap,    label: `Executing ${subtaskCount} subtasks in parallel...`, color: "text-blue-600", bg: "bg-blue-50" },
    aggregating: { icon: FileText, label: "Aggregating — synthesizing report...", color: "text-emerald-600", bg: "bg-emerald-50" },
    done:    { icon: CheckCircle2, label: "Complete",          color: "text-emerald-600", bg: "bg-emerald-50" },
    error:   { icon: XCircle, label: "Error",                 color: "text-red-600",    bg: "bg-red-50" },
  };

  const cfg = configs[phase];
  const Icon = cfg.icon;
  const spinning = phase === "decomposing" || phase === "executing" || phase === "aggregating";

  return (
    <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border transition-colors ${cfg.bg} ${phase === "error" ? "border-red-200" : "border-border"}`}>
      {spinning ? <Loader2 size={18} className={`${cfg.color} animate-spin`} /> :
       <Icon size={18} className={cfg.color} />}
      <span className={`text-sm font-medium ${cfg.color}`}>{cfg.label}</span>
    </div>
  );
}

// ── Subtask Card (live) ────────────────────────────────────

function SubtaskCard({ st, phase }: { st: LiveSubtask; phase: Phase }) {
  const [expanded, setExpanded] = useState(false);
  const done = st.status === "completed";
  const fail = st.status === "failed";
  const running = st.status === "running" || (st.status === "pending" && phase === "executing");

  return (
    <div className={`border rounded-xl overflow-hidden transition-all ${
      done ? "border-emerald-200 bg-emerald-50/20" :
      fail ? "border-red-200 bg-red-50/20" :
      running ? "border-blue-200 bg-blue-50/20 animate-pulse" :
      "border-border bg-white"
    }`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50/30 transition-colors"
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
        {st.duration_ms > 0 ? (
          <span className="text-[10px] text-gray-400 font-mono shrink-0">{st.duration_ms}ms</span>
        ) : running ? (
          <span className="text-[10px] text-blue-400 font-mono shrink-0">running...</span>
        ) : null}
        <ChevronDown size={12} className={`text-gray-300 transition-transform ${expanded ? "rotate-180" : ""}`} />
      </button>

      {expanded && (done || fail) && (
        <div className="border-t border-border px-4 py-3 space-y-2 text-[10px]">
          {st.result != null && (
            <div>
              <span className="font-semibold text-gray-400 uppercase tracking-wider">Result</span>
              <pre className="mt-1 p-2 bg-gray-100 rounded font-mono text-gray-600 whitespace-pre-wrap break-all max-h-48 overflow-y-auto">
                {typeof st.result === "string" ? st.result : safeStringify(st.result)}
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

// ── Aggregate Result ──────────────────────────────────────

function AggregateResult({ data }: { data: AggregatedData }) {
  const trace = data.execution_trace;

  return (
    <div className="space-y-4">
      {data.aggregated_output && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <BarChart3 size={14} className="text-emerald-500" />
            <span className="text-xs font-semibold text-ink">Aggregated Report</span>
          </div>
          <div className="bg-white border border-border rounded-xl p-5">
            <div className="text-sm leading-relaxed text-ink/80 whitespace-pre-wrap">
              {data.aggregated_output}
            </div>
          </div>
        </div>
      )}

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
          <span className="text-gray-300">|</span>
          <span className="text-gray-400 text-[11px]">
            {trace.total} subtasks total
          </span>
          <div className="flex items-center gap-1.5 ml-auto">
            <Clock size={12} className="text-gray-400" />
            <span className="font-mono text-gray-500">{trace.total_duration_ms}ms</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────

export function DecomposeTestChat() {
  const [goal, setGoal] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [phaseMessage, setPhaseMessage] = useState("");
  const [subtasks, setSubtasks] = useState<LiveSubtask[]>([]);
  const [aggregated, setAggregated] = useState<AggregatedData | null>(null);
  const [streamingText, setStreamingText] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [subtasks, aggregated, phase]);

  const reset = useCallback(() => {
    setPhase("idle");
    setPhaseMessage("");
    setSubtasks([]);
    setAggregated(null);
    setStreamingText("");
    setErrorMsg("");
  }, []);

  const handleSubmit = async () => {
    const trimmed = goal.trim();
    if (!trimmed || phase !== "idle" && phase !== "done" && phase !== "error") return;

    // Abort any in-flight request
    abortRef.current?.abort();

    reset();
    setGoal("");
    setPhase("decomposing");
    setPhaseMessage("Analyzing goal...");

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const resp = await fetch("/api/v1/workflows/test-decompose/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal: trimmed }),
        signal: controller.signal,
      });

      if (!resp.ok) {
        const errText = await resp.text().catch(() => "Unknown");
        setPhase("error");
        setErrorMsg(`Server error (${resp.status}): ${errText.slice(0, 300)}`);
        return;
      }

      const reader = resp.body?.getReader();
      if (!reader) {
        setPhase("error");
        setErrorMsg("No response body");
        return;
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE events from buffer
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";  // Keep incomplete line in buffer

        let currentEvent = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const dataStr = line.slice(6);
            try {
              const data = JSON.parse(dataStr);
              handleSSE(currentEvent, data);
            } catch { /* skip malformed JSON */ }
          }
          // Empty line = end of event
        }
      }
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      setPhase("error");
      setErrorMsg(e instanceof Error ? e.message : String(e));
    }
  };

  const handleSSE = (event: string, data: Record<string, unknown>) => {
    switch (event) {
      case "phase": {
        const p = data.phase as Phase;
        setPhase(p);
        setPhaseMessage(data.message as string || "");
        break;
      }
      case "decomposed": {
        const rawSubtasks = data.subtasks as Array<Record<string, unknown>> || [];
        setSubtasks(rawSubtasks.map(st => ({
          id: st.id as string,
          description: st.description as string,
          executor: st.executor as string,
          status: "pending" as const,
          result: null,
          error: null,
          duration_ms: 0,
        })));
        break;
      }
      case "subtask_start": {
        setSubtasks(prev => prev.map(st =>
          st.id === data.id ? { ...st, status: "running" as const } : st
        ));
        break;
      }
      case "subtask_done": {
        setSubtasks(prev => prev.map(st =>
          st.id === data.id ? {
            ...st,
            status: "completed" as const,
            result: data.result,
            duration_ms: data.duration_ms as number || 0,
          } : st
        ));
        break;
      }
      case "subtask_failed": {
        setSubtasks(prev => prev.map(st =>
          st.id === data.id ? {
            ...st,
            status: "failed" as const,
            error: data.error as string || null,
            duration_ms: data.duration_ms as number || 0,
          } : st
        ));
        break;
      }
      case "token": {
        setStreamingText(prev => prev + (data.text as string || ""));
        break;
      }
      case "aggregated": {
        setStreamingText("");  // Clear streaming, use final
        setAggregated({
          aggregated_output: data.aggregated_output as string || "",
          execution_trace: data.execution_trace as TraceInfo | null,
        });
        break;
      }
      case "error": {
        setPhase("error");
        setErrorMsg(data.message as string || "Unknown error");
        break;
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const isRunning = phase === "decomposing" || phase === "executing" || phase === "aggregating";
  const completedCount = subtasks.filter(s => s.status === "completed").length;
  const failedCount = subtasks.filter(s => s.status === "failed").length;

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
              Type a complex goal below — watch it decompose, execute, and aggregate in real-time
            </p>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {/* Idle state */}
        {phase === "idle" && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center max-w-md">
              <GitFork size={48} className="text-gray-200 mx-auto mb-4" />
              <h2 className="text-lg font-semibold text-ink/50 mb-2">Task Decomposition Tester</h2>
              <p className="text-sm text-gray-400 mb-4">
                Enter a complex goal and watch each step in real-time:
              </p>
              <div className="text-left space-y-2 text-xs text-gray-500">
                <div className="flex items-center gap-2"><Brain size={12} className="text-amber-400" /> 1. LLM analyzes and decomposes the goal</div>
                <div className="flex items-center gap-2"><Zap size={12} className="text-blue-400" /> 2. Subtasks execute in parallel with live status</div>
                <div className="flex items-center gap-2"><FileText size={12} className="text-emerald-400" /> 3. Results are aggregated into a final report</div>
              </div>
              <p className="text-xs text-gray-300 mt-4">
                Try: "对比分析特斯拉和比亚迪2025 Q1财报" or "Research quantum computing 2025 breakthroughs"
              </p>
            </div>
          </div>
        )}

        {/* Phase banner */}
        {phase !== "idle" && (
          <PhaseBanner phase={phase} subtaskCount={subtasks.length} />
        )}

        {/* Error */}
        {phase === "error" && errorMsg && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4">
            <p className="text-sm text-red-600 font-medium">❌ {errorMsg}</p>
          </div>
        )}

        {/* Goal bubble */}
        {goal && isRunning && (
          <div className="flex justify-end">
            <div className="max-w-[80%] bg-ink text-white px-4 py-3 rounded-2xl rounded-br-md">
              <p className="text-xs font-medium opacity-60 mb-0.5">Goal</p>
              <p className="text-sm">{goal}</p>
            </div>
          </div>
        )}

        {/* Subtask progress */}
        {subtasks.length > 0 && (
          <div>
            <div className="flex items-center gap-2 mb-3">
              <GitFork size={14} className="text-amber-500" />
              <span className="text-xs font-semibold text-ink">
                Subtasks
              </span>
              {isRunning && (
                <span className="text-[10px] text-gray-400 font-mono ml-auto">
                  {completedCount}/{subtasks.length} done
                  {failedCount > 0 && ` · ${failedCount} failed`}
                </span>
              )}
            </div>
            <div className="space-y-2">
              {subtasks.map(st => (
                <SubtaskCard key={st.id} st={st} phase={phase} />
              ))}
            </div>
          </div>
        )}

        {/* Streaming text during aggregation */}
        {(streamingText || phase === "aggregating") && (
          <div>
            <div className="flex items-center gap-2 mb-3">
              <BarChart3 size={14} className="text-emerald-500" />
              <span className="text-xs font-semibold text-ink">Live Report</span>
              {phase === "aggregating" && <Loader2 size={12} className="text-emerald-400 animate-spin" />}
            </div>
            <div className="bg-white border border-emerald-200 rounded-xl p-5">
              <div className="text-sm leading-relaxed text-ink/80 whitespace-pre-wrap">
                {streamingText || <span className="text-gray-300 italic">Generating report...</span>}
              </div>
            </div>
          </div>
        )}

        {/* Aggregate result (final) */}
        {aggregated && !streamingText && (
          <AggregateResult data={aggregated} />
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="px-6 py-4 border-t border-border bg-white shrink-0">
        <div className="flex gap-2">
          <textarea
            value={goal}
            onChange={e => setGoal(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isRunning}
            placeholder={isRunning ? phaseMessage : "Enter a complex goal to decompose..."}
            rows={2}
            className="flex-1 px-4 py-3 text-sm border border-border rounded-xl bg-warm
                       focus:outline-none focus:ring-2 focus:ring-amber-200 resize-none
                       placeholder:text-gray-300 disabled:opacity-50"
          />
          <button
            onClick={handleSubmit}
            disabled={isRunning || !goal.trim()}
            className="shrink-0 w-12 h-12 rounded-xl bg-ink text-white flex items-center justify-center
                       hover:bg-slate-hover disabled:opacity-30 transition-colors self-end"
          >
            {isRunning ? <Loader2 size={18} className="animate-spin" /> : <Send size={16} />}
          </button>
        </div>
      </div>
    </div>
  );
}
