import { useState, useEffect, useMemo } from "react";
import type { Node, Edge } from "@xyflow/react";
import { X, Play, Loader2, ChevronDown } from "lucide-react";

interface ConfigDrawerProps {
  node: Node | null;
  onClose: () => void;
  onUpdate: (nodeId: string, data: Record<string, unknown>) => void;
  edges?: Edge[];
  allNodes?: Node[];
}

interface KVRow {
  id: number;
  key: string;
  value: string;
}

interface InputRow {
  id: number;
  name: string;
  source: "reference" | "literal";
  ref: string;     // template path like "search.results"
  value: string;   // fixed literal value
  type: string;    // string | number | boolean | object | array | any
  required: boolean;
}

// ── Per-node default outputs ──────────────────────────────

const NODE_OUTPUTS: Record<string, { name: string; type: string; description: string }[]> = {
  start: [
    { name: "query", type: "string", description: "用户输入文本" },
  ],
  chat: [
    { name: "content", type: "string", description: "LLM 回复内容" },
  ],
  rag: [
    { name: "documents", type: "array", description: "检索到的文档列表" },
    { name: "kb_id", type: "string", description: "知识库 ID" },
    { name: "query", type: "string", description: "搜索查询" },
  ],
  search: [
    { name: "results", type: "array", description: "搜索结果列表" },
    { name: "query", type: "string", description: "搜索关键词" },
    { name: "backend", type: "string", description: "搜索引擎名称" },
  ],
  tool: [
    { name: "result", type: "any", description: "工具执行结果" },
    { name: "tool_name", type: "string", description: "工具名称" },
  ],
  http_api: [
    { name: "status", type: "number", description: "HTTP 状态码" },
    { name: "body", type: "any", description: "响应体" },
    { name: "headers", type: "object", description: "响应头" },
    { name: "duration_ms", type: "number", description: "请求耗时(ms)" },
  ],
  hitl: [
    { name: "status", type: "string", description: "审批状态" },
    { name: "message", type: "string", description: "审批消息" },
  ],
};

const INPUT_TYPES = ["string", "number", "boolean", "object", "array", "any"];

// ── Node type metadata ─────────────────────────────────────

const NODE_META: Record<string, { icon: string; label: string; color: string }> = {
  start:     { icon: "▶", label: "Start",            color: "bg-gray-800 text-white" },
  chat:      { icon: "💬", label: "Chat",            color: "bg-blue-100 text-blue-600" },
  rag:       { icon: "📚", label: "RAG",              color: "bg-violet-100 text-violet-600" },
  search:    { icon: "🌐", label: "Web Search",       color: "bg-teal-100 text-teal-600" },
  tool:      { icon: "🔧", label: "Tool",             color: "bg-amber-100 text-amber-600" },
  http_api:  { icon: "📡", label: "API Call",         color: "bg-sky-100 text-sky-600" },
  condition: { icon: "🔀", label: "Condition",        color: "bg-red-100 text-red-600" },
  loop:      { icon: "🔄", label: "Loop",             color: "bg-cyan-100 text-cyan-600" },
  hitl:      { icon: "✋", label: "HITL",              color: "bg-emerald-100 text-emerald-600" },
};

const METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH"];
const OPERATORS = ["contains", "equals", "gt", "lt"];
const AUTH_MODES = [
  { value: "none", label: "None" },
  { value: "bearer", label: "Bearer Token" },
  { value: "api_key", label: "API Key" },
  { value: "basic", label: "Basic Auth" },
];

// ── KV helpers ─────────────────────────────────────────────

function kvToRows(obj: Record<string, string> | undefined): KVRow[] {
  if (!obj || Object.keys(obj).length === 0) return [{ id: Date.now(), key: "", value: "" }];
  return Object.entries(obj).map(([k, v], i) => ({ id: Date.now() + i, key: k, value: v }));
}

function rowsToKv(rows: KVRow[]): Record<string, string> {
  const result: Record<string, string> = {};
  for (const r of rows) {
    if (r.key.trim()) result[r.key.trim()] = r.value;
  }
  return result;
}

// ── Reusable field components ──────────────────────────────

function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-500 mb-1.5">{label}</label>
      {children}
    </div>
  );
}

function TextField({ value, onChange, onBlur, placeholder, mono }: {
  value: string; onChange: (v: string) => void; onBlur?: () => void;
  placeholder?: string; mono?: boolean;
}) {
  return (
    <input
      type="text" value={value}
      onChange={e => onChange(e.target.value)} onBlur={onBlur}
      placeholder={placeholder}
      className={`w-full px-3 py-2 text-sm border border-border rounded-lg bg-white
                  focus:outline-none focus:ring-2 focus:ring-sky-200 ${mono ? "font-mono" : ""}`}
    />
  );
}

function NumberField({ value, onChange, onBlur, min, max }: {
  value: number; onChange: (v: number) => void; onBlur?: () => void; min?: number; max?: number;
}) {
  return (
    <input
      type="number" value={value}
      onChange={e => onChange(Number(e.target.value))} onBlur={onBlur}
      min={min} max={max}
      className="w-full px-3 py-2 text-sm border border-border rounded-lg bg-white
                 focus:outline-none focus:ring-2 focus:ring-sky-200"
    />
  );
}

function SelectField({ value, onChange, options }: {
  value: string; onChange: (v: string) => void;
  options: (string | { value: string; label: string })[];
}) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)}
      className="w-full px-3 py-2 text-sm border border-border rounded-lg bg-white
                 focus:outline-none focus:ring-2 focus:ring-sky-200">
      {options.map(o =>
        typeof o === "string"
          ? <option key={o} value={o}>{o}</option>
          : <option key={o.value} value={o.value}>{o.label}</option>
      )}
    </select>
  );
}

// ── KV Section ─────────────────────────────────────────────

function KVSection({ title, rows, addRow, updateRow, removeRow, onBlur }: {
  title: string; rows: KVRow[]; setRows: (r: KVRow[]) => void;
  addRow: () => void;
  updateRow: (id: number, field: "key" | "value", val: string) => void;
  removeRow: (id: number) => void;
  onBlur: () => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <label className="text-xs font-medium text-gray-500">{title}</label>
        <button onClick={addRow}
          className="text-[10px] text-sky-500 hover:text-sky-700 font-medium transition-colors">
          + 添加
        </button>
      </div>
      <div className="border border-border rounded-lg overflow-hidden">
        {rows.map((r, i) => (
          <div key={r.id} className={`flex border-b border-border last:border-b-0 ${i % 2 === 0 ? "bg-white" : "bg-gray-50/50"}`}>
            <input type="text" value={r.key}
              onChange={e => updateRow(r.id, "key", e.target.value)}
              onBlur={onBlur} placeholder="Key"
              className="flex-1 px-3 py-2 text-xs border-r border-border bg-transparent focus:outline-none focus:bg-sky-50/30 min-w-0" />
            <input type="text" value={r.value}
              onChange={e => updateRow(r.id, "value", e.target.value)}
              onBlur={onBlur} placeholder="Value"
              className="flex-1 px-3 py-2 text-xs bg-transparent focus:outline-none focus:bg-sky-50/30 min-w-0" />
            <button onClick={() => removeRow(r.id)}
              className="px-2 text-gray-300 hover:text-red-400 transition-colors shrink-0" title="Remove">
              <X size={12} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Smart Reference Input ─────────────────────────────────

function RefInput({ value, onChange, onBlur, upstreamOutputs }: {
  value: string;
  onChange: (v: string) => void;
  onBlur: () => void;
  upstreamOutputs: { nodeId: string; nodeLabel: string; path: string; description: string }[];
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");

  const filtered = search.trim()
    ? upstreamOutputs.filter(o =>
        o.path.toLowerCase().includes(search.toLowerCase()) ||
        o.nodeLabel.toLowerCase().includes(search.toLowerCase()))
    : upstreamOutputs;

  return (
    <div className="relative">
      <div className="flex gap-1">
        <input
          type="text"
          value={value}
          onChange={e => { onChange(e.target.value); setSearch(e.target.value); }}
          onFocus={() => setOpen(true)}
          onBlur={() => { setTimeout(() => setOpen(false), 150); onBlur(); }}
          placeholder="手动输入或选择上游输出"
          className="flex-1 px-2 py-1.5 text-xs border border-border rounded bg-white font-mono text-sky-600 focus:outline-none focus:ring-1 focus:ring-sky-200"
        />
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="px-1.5 border border-border rounded bg-gray-50 hover:bg-gray-100 transition-colors"
          title="选择上游节点输出"
        >
          <ChevronDown size={12} className="text-gray-400" />
        </button>
      </div>

      {open && upstreamOutputs.length > 0 && (
        <div className="absolute z-50 left-0 right-0 mt-1 bg-white border border-border rounded-lg shadow-xl max-h-48 overflow-y-auto">
          <div className="px-2 py-1.5 border-b border-border bg-gray-50">
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="搜索上游输出..."
              className="w-full px-2 py-1 text-[10px] border border-border rounded bg-white focus:outline-none"
              onClick={e => e.stopPropagation()}
            />
          </div>
          {filtered.length === 0 ? (
            <div className="px-3 py-2 text-[10px] text-gray-400 text-center">
              {upstreamOutputs.length === 0 ? "无上游节点" : "无匹配结果"}
            </div>
          ) : (
            filtered.map(o => (
              <button
                key={o.path}
                type="button"
                onClick={() => {
                  onChange(`{{${o.path}}}`);
                  setOpen(false);
                  setSearch("");
                }}
                className="w-full text-left px-3 py-2 hover:bg-sky-50 transition-colors border-b border-border last:border-b-0 flex items-center justify-between"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-[10px] bg-gray-100 px-1 py-0.5 rounded font-mono text-gray-500 shrink-0">{o.nodeId}</span>
                  <span className="text-xs font-mono text-sky-600 truncate">{o.path}</span>
                </div>
                <span className="text-[10px] text-gray-400 shrink-0 ml-2">{o.description}</span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ── Main ConfigDrawer ──────────────────────────────────────

export function ConfigDrawer({ node, onClose, onUpdate, edges, allNodes }: ConfigDrawerProps) {
  const isOpen = node !== null;
  // Map ReactFlow internal types to config types
  const rawType = node?.type || "";
  const nodeType = rawType === "startNode" ? "start" : rawType === "endNode" ? "end" : rawType;
  const meta = NODE_META[nodeType] || { icon: "⚙️", label: nodeType, color: "bg-gray-100 text-gray-600" };

  // ── Compute upstream node outputs ────────────────────
  const upstreamOutputs = useMemo(() => {
    if (!node || !edges || !allNodes) return [];
    const upstreamEdgeIds = edges
      .filter(e => e.target === node.id)
      .map(e => e.source);
    const upstreamNodes = allNodes.filter(n => upstreamEdgeIds.includes(n.id));
    const outputs: { nodeId: string; nodeLabel: string; path: string; description: string }[] = [];
    for (const un of upstreamNodes) {
      const ut = un.type === "startNode" ? "start" : un.type === "endNode" ? "end" : (un.type || "");
      if (ut === "end" || ut === "condition" || ut === "loop") continue;
      const defs = NODE_OUTPUTS[ut] || [];
      for (const o of defs) {
        outputs.push({
          nodeId: un.id,
          nodeLabel: (un.data?.label as string) || ut || un.id,
          path: `${un.id}.${o.name}`,
          description: o.description,
        });
      }
    }
    return outputs;
  }, [node, edges, allNodes]);

  // ── KB list (fetched once) ────────────────────────────
  const [kbList, setKbList] = useState<{ id: string; name: string }[]>([]);

  // ── Common state (reset per node) ──────────────────────
  const [systemPrompt, setSystemPrompt] = useState("");
  const [kbId, setKbId] = useState("");
  const [toolName, setToolName] = useState("");
  const [url, setUrl] = useState("");
  const [method, setMethod] = useState("GET");
  const [headers, setHeaders] = useState<KVRow[]>([{ id: 1, key: "", value: "" }]);
  const [queryParams, setQueryParams] = useState<KVRow[]>([{ id: 1, key: "", value: "" }]);
  const [body, setBody] = useState("");
  const [timeout, setTimeout_] = useState(30);
  const [retryCount, setRetryCount] = useState(0);
  const [responsePath, setResponsePath] = useState("");
  const [authMode, setAuthMode] = useState("none");
  const [condField, setCondField] = useState("");
  const [condOp, setCondOp] = useState("contains");
  const [condValue, setCondValue] = useState("");
  const [loopInputField, setLoopInputField] = useState("");
  const [loopMaxIter, setLoopMaxIter] = useState(5);
  const [hitlMsg, setHitlMsg] = useState("");
  const [startOutputName, setStartOutputName] = useState("query");

  // ── Dynamic outputs for start node ──────────────────
  const startOutputs = useMemo(() => {
    const name = startOutputName || "query";
    return [{ name, type: "string", description: "用户输入变量" }];
  }, [startOutputName]);

  // ── Debug state (http_api only) ────────────────────────
  const [debugLoading, setDebugLoading] = useState(false);
  const [debugResult, setDebugResult] = useState<Record<string, unknown> | null>(null);

  // ── Inputs state ──────────────────────────────────────
  const [inputs, setInputs] = useState<InputRow[]>([{ id: 1, name: "", source: "reference", ref: "", value: "", type: "any", required: false }]);

  const inputsToPayload = (rows: InputRow[]) =>
    rows.filter(r => r.name.trim()).map(r => ({
      name: r.name.trim(),
      source: r.source,
      ref: r.source === "reference" ? r.ref : "",
      value: r.source === "literal" ? r.value : null,
      type: r.type,
      required: r.required,
    }));

  const payloadToInputs = (payload: unknown[] | undefined): InputRow[] => {
    if (!payload || !Array.isArray(payload) || payload.length === 0) {
      return [{ id: 1, name: "", source: "reference", ref: "", value: "", type: "any", required: false }];
    }
    return payload.map((p: any, i: number) => ({
      id: Date.now() + i,
      name: p.name || "",
      source: p.source || "reference",
      ref: p.ref || "",
      value: p.value ?? "",
      type: p.type || "any",
      required: p.required ?? false,
    }));
  };

  // ── Fetch KB list on mount ───────────────────────────
  useEffect(() => {
    fetch("/api/v1/knowledge/bases")
      .then(r => r.json())
      .then(data => setKbList(Array.isArray(data) ? data : []))
      .catch(() => setKbList([]));
  }, []);

  // ── Reset form on node change ──────────────────────────
  useEffect(() => {
    if (!node) return;
    const d = node.data as Record<string, unknown> | undefined;
    setSystemPrompt(String(d?.system_prompt || ""));
    setKbId(String(d?.knowledge_base_id || ""));
    setToolName(String(d?.tool_name || ""));
    setUrl(String(d?.url || ""));
    setMethod(String(d?.method || "GET"));
    setHeaders(kvToRows(d?.headers as Record<string, string> | undefined));
    setQueryParams(kvToRows(d?.query_params as Record<string, string> | undefined));
    setBody(String(d?.body || ""));
    setTimeout_(Number(d?.timeout) || 30);
    setRetryCount(Number(d?.retry_count) || 0);
    setResponsePath(String(d?.response_path || ""));
    setAuthMode(String(d?.auth_mode || "none"));
    setCondField(String(d?.field || ""));
    setCondOp(String(d?.operator || "contains"));
    setCondValue(String(d?.value || ""));
    setLoopInputField(String(d?.input_field || ""));
    setLoopMaxIter(Number(d?.max_iterations) || 5);
    setHitlMsg(String(d?.approval_message || ""));
    setStartOutputName(String(d?.output_name || "query"));
    setInputs(payloadToInputs(d?.inputs as unknown[] | undefined));
    setDebugResult(null);
  }, [node]);

  // ── Sync helpers ───────────────────────────────────────
  const emit = (updates: Record<string, unknown>) => {
    if (!node) return;
    onUpdate(node.id, updates);
  };

  // ── http_api debug ─────────────────────────────────────
  const handleDebug = async () => {
    setDebugLoading(true);
    setDebugResult(null);
    try {
      const resp = await fetch("/api/v1/customer-service/test-api-call", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url, method,
          headers: rowsToKv(headers),
          query_params: rowsToKv(queryParams),
          body: body || null,
          timeout, retry_count: retryCount,
          response_path: responsePath || null,
        }),
      });
      setDebugResult(await resp.json());
    } catch (e: unknown) {
      setDebugResult({ error: String(e) });
    }
    setDebugLoading(false);
  };

  // ── Render ─────────────────────────────────────────────
  return (
    <>
      {isOpen && <div className="fixed inset-0 z-40" onClick={onClose} />}

      <div className={`fixed top-0 right-0 h-full w-[400px] bg-white border-l border-border shadow-2xl z-50
                       flex flex-col transition-transform duration-200 ${isOpen ? "translate-x-0" : "translate-x-full"}`}>

        {/* ── Header ──────────────────────────────────── */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
          <div className="flex items-center gap-2">
            <div className={`w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold ${meta.color}`}>
              {meta.icon}
            </div>
            <span className="font-semibold text-sm text-ink">{meta.label}</span>
          </div>
          <button onClick={onClose} className="p-1 rounded-md hover:bg-gray-100 transition-colors">
            <X size={16} className="text-gray-400" />
          </button>
        </div>

        {/* ── Body ────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">

          {/* ======== START ======== */}
          {nodeType === "start" && (
            <FieldRow label="输出变量名称">
              <TextField value={startOutputName} onChange={setStartOutputName}
                onBlur={() => emit({ output_name: startOutputName })}
                placeholder="query" mono />
              <p className="text-[10px] text-gray-400 mt-1">
                下游节点通过 <code className="font-mono text-sky-500 bg-sky-50 px-1 rounded">{`{{${node?.id || "start"}.${startOutputName || "query"}}}`}</code> 引用
              </p>
            </FieldRow>
          )}

          {/* ======== CHAT ======== */}
          {nodeType === "chat" && (
            <FieldRow label="System Prompt">
              <textarea
                value={systemPrompt}
                onChange={e => setSystemPrompt(e.target.value)}
                onBlur={() => emit({ system_prompt: systemPrompt })}
                rows={8}
                placeholder="You are a helpful assistant..."
                className="w-full px-3 py-2 text-sm border border-border rounded-lg bg-white font-mono
                           focus:outline-none focus:ring-2 focus:ring-blue-200 resize-y"
              />
            </FieldRow>
          )}

          {/* ======== RAG ======== */}
          {nodeType === "rag" && (
            <FieldRow label="Knowledge Base">
              {kbList.length === 0 ? (
                <div className="text-sm text-gray-400 py-2">Loading knowledge bases...</div>
              ) : (
                <select value={kbId}
                  onChange={e => {
                    setKbId(e.target.value);
                    const selected = kbList.find(kb => kb.id === e.target.value);
                    emit({ knowledge_base_id: e.target.value, knowledge_base_name: selected?.name || "" });
                  }}
                  className="w-full px-3 py-2 text-sm border border-border rounded-lg bg-white
                             focus:outline-none focus:ring-2 focus:ring-violet-200">
                  <option value="">— 选择知识库 —</option>
                  {kbList.map(kb => (
                    <option key={kb.id} value={kb.id}>{kb.name}</option>
                  ))}
                </select>
              )}
            </FieldRow>
          )}

          {/* ======== SEARCH ======== */}
          {nodeType === "search" && (
            <div className="text-sm text-gray-400 text-center py-8">
              Web Search 节点无需额外配置
            </div>
          )}

          {/* ======== TOOL ======== */}
          {nodeType === "tool" && (
            <FieldRow label="Tool Name">
              <TextField value={toolName} onChange={setToolName}
                onBlur={() => emit({ tool_name: toolName })}
                placeholder="e.g. calculator, file_search" />
            </FieldRow>
          )}

          {/* ======== HTTP API ======== */}
          {nodeType === "http_api" && (
            <>
              <FieldRow label="HTTP Method">
                <SelectField value={method}
                  onChange={v => { setMethod(v); emit({ method: v }); }}
                  options={METHODS} />
              </FieldRow>

              <FieldRow label="URL">
                <TextField value={url} onChange={setUrl}
                  onBlur={() => emit({ url })}
                  placeholder="https://api.example.com/data" mono />
              </FieldRow>

              <div className="flex gap-3">
                <div className="flex-1">
                  <FieldRow label="Timeout (s)">
                    <NumberField value={timeout} onChange={setTimeout_}
                      onBlur={() => emit({ timeout })} min={1} max={300} />
                  </FieldRow>
                </div>
                <div className="flex-1">
                  <FieldRow label="Retry (失败重试)">
                    <NumberField value={retryCount} onChange={setRetryCount}
                      onBlur={() => emit({ retry_count: retryCount })} min={0} max={10} />
                  </FieldRow>
                </div>
              </div>

              <KVSection title="Request Parameters" rows={queryParams}
                setRows={setQueryParams}
                onBlur={() => emit({ query_params: rowsToKv(queryParams) })}
                addRow={() => setQueryParams([...queryParams, { id: Date.now(), key: "", value: "" }])}
                updateRow={(id, f, v) => setQueryParams(queryParams.map(r => r.id === id ? { ...r, [f]: v } : r))}
                removeRow={(id) => { if (queryParams.length > 1) setQueryParams(queryParams.filter(r => r.id !== id)); }}
              />

              <KVSection title="Request Headers" rows={headers}
                setRows={setHeaders}
                onBlur={() => emit({ headers: rowsToKv(headers) })}
                addRow={() => setHeaders([...headers, { id: Date.now(), key: "", value: "" }])}
                updateRow={(id, f, v) => setHeaders(headers.map(r => r.id === id ? { ...r, [f]: v } : r))}
                removeRow={(id) => { if (headers.length > 1) setHeaders(headers.filter(r => r.id !== id)); }}
              />

              <FieldRow label="Request Body">
                <textarea value={body} onChange={e => setBody(e.target.value)}
                  onBlur={() => emit({ body })}
                  rows={6} placeholder='{"query": "{{input.keyword}}"}'
                  className="w-full px-3 py-2 text-sm border border-border rounded-lg bg-white font-mono
                             focus:outline-none focus:ring-2 focus:ring-sky-200 resize-y" />
              </FieldRow>

              <FieldRow label="Response — JSONPath 提取">
                <TextField value={responsePath} onChange={setResponsePath}
                  onBlur={() => emit({ response_path: responsePath })}
                  placeholder="data.items" mono />
              </FieldRow>

              <FieldRow label="认证模式">
                <SelectField value={authMode}
                  onChange={v => { setAuthMode(v); emit({ auth_mode: v }); }}
                  options={AUTH_MODES} />
              </FieldRow>

              {/* Debug */}
              <button onClick={handleDebug} disabled={debugLoading || !url}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 text-sm font-medium
                           rounded-xl bg-sky-500 text-white hover:bg-sky-600 disabled:opacity-40
                           transition-colors shadow-sm">
                {debugLoading
                  ? <><Loader2 size={16} className="animate-spin" /> Testing...</>
                  : <><Play size={14} /> 调试运行</>
                }
              </button>

              {debugResult && (
                <div className="border border-border rounded-xl overflow-hidden">
                  <div className="flex items-center gap-2 px-3 py-2 bg-gray-50 border-b border-border">
                    {debugResult.error ? (
                      <span className="text-xs text-red-500">❌ Error</span>
                    ) : (
                      <>
                        <span className="text-xs font-mono text-green-600">{String(debugResult.status)} OK</span>
                        <span className="text-[10px] text-gray-400">⏱ {String(debugResult.duration_ms)}ms</span>
                        {Number(debugResult.retries_used) > 0 && (
                          <span className="text-[10px] text-amber-500">🔄 retries: {String(debugResult.retries_used)}</span>
                        )}
                      </>
                    )}
                  </div>
                  <pre className="p-3 text-xs font-mono text-gray-700 bg-white max-h-60 overflow-y-auto whitespace-pre-wrap">
                    {JSON.stringify(debugResult.body || debugResult.error, null, 2)}
                  </pre>
                </div>
              )}
            </>
          )}

          {/* ======== CONDITION ======== */}
          {nodeType === "condition" && (
            <>
              <FieldRow label="Field">
                <TextField value={condField} onChange={setCondField}
                  onBlur={() => emit({ field: condField })}
                  placeholder="e.g. messages[-1].content" mono />
              </FieldRow>

              <FieldRow label="Operator">
                <SelectField value={condOp}
                  onChange={v => { setCondOp(v); emit({ operator: v }); }}
                  options={OPERATORS} />
              </FieldRow>

              <FieldRow label="Value">
                <TextField value={condValue} onChange={setCondValue}
                  onBlur={() => emit({ value: condValue })}
                  placeholder="Match value..." />
              </FieldRow>
            </>
          )}

          {/* ======== LOOP ======== */}
          {nodeType === "loop" && (
            <>
              <FieldRow label="Input Field">
                <TextField value={loopInputField} onChange={setLoopInputField}
                  onBlur={() => emit({ input_field: loopInputField })}
                  placeholder="e.g. node_1.body.items" mono />
              </FieldRow>

              <FieldRow label="Max Iterations">
                <NumberField value={loopMaxIter} onChange={setLoopMaxIter}
                  onBlur={() => emit({ max_iterations: loopMaxIter })} min={1} max={100} />
              </FieldRow>
            </>
          )}

          {/* ======== HITL ======== */}
          {nodeType === "hitl" && (
            <FieldRow label="Approval Message">
              <textarea value={hitlMsg} onChange={e => setHitlMsg(e.target.value)}
                onBlur={() => emit({ approval_message: hitlMsg })}
                rows={4}
                placeholder="Approve this action?"
                className="w-full px-3 py-2 text-sm border border-border rounded-lg bg-white
                           focus:outline-none focus:ring-2 focus:ring-emerald-200 resize-y" />
            </FieldRow>
          )}

          {/* ======== INPUTS + OUTPUTS ======== */}
          {nodeType !== "" && nodeType !== "end" && (
            <>
              <hr className="border-border" />

              {/* ── Inputs (skip for start — it's the data source) ── */}
              {nodeType !== "start" && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Inputs</label>
                  <button
                    onClick={() => {
                      const next = [...inputs, { id: Date.now(), name: "", source: "reference" as const, ref: "", value: "", type: "any", required: false }];
                      setInputs(next);
                      emit({ inputs: inputsToPayload(next) });
                    }}
                    className="text-[10px] text-sky-500 hover:text-sky-700 font-medium transition-colors">
                    + 添加
                  </button>
                </div>
                <div className="space-y-2">
                  {inputs.map((r, i) => (
                    <div key={r.id} className="border border-border rounded-lg p-3 bg-gray-50/50 space-y-2">
                      {/* Row 1: name + type */}
                      <div className="flex gap-2">
                        <input
                          type="text" value={r.name}
                          onChange={e => {
                            const next = inputs.map(ir => ir.id === r.id ? { ...ir, name: e.target.value } : ir);
                            setInputs(next);
                          }}
                          onBlur={() => emit({ inputs: inputsToPayload(inputs) })}
                          placeholder="参数名"
                          className="flex-1 px-2 py-1.5 text-xs border border-border rounded bg-white font-mono focus:outline-none focus:ring-1 focus:ring-sky-200 min-w-0"
                        />
                        <select
                          value={r.type}
                          onChange={e => {
                            const next = inputs.map(ir => ir.id === r.id ? { ...ir, type: e.target.value } : ir);
                            setInputs(next);
                            emit({ inputs: inputsToPayload(next) });
                          }}
                          className="w-20 px-1 py-1.5 text-xs border border-border rounded bg-white focus:outline-none focus:ring-1 focus:ring-sky-200">
                          {INPUT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                        </select>
                        {inputs.length > 1 && (
                          <button
                            onClick={() => {
                              const next = inputs.filter(ir => ir.id !== r.id);
                              setInputs(next);
                              emit({ inputs: inputsToPayload(next) });
                            }}
                            className="px-1 text-gray-300 hover:text-red-400 transition-colors shrink-0">
                            <X size={14} />
                          </button>
                        )}
                      </div>

                      {/* Row 2: source toggle */}
                      <div className="flex gap-2 items-center">
                        <label className="flex items-center gap-1 cursor-pointer">
                          <input
                            type="radio"
                            name={`source-${r.id}`}
                            checked={r.source === "reference"}
                            onChange={() => {
                              const next = inputs.map(ir => ir.id === r.id ? { ...ir, source: "reference" as const } : ir);
                              setInputs(next);
                              emit({ inputs: inputsToPayload(next) });
                            }}
                            className="w-3 h-3"
                          />
                          <span className="text-[10px] text-gray-500">引用</span>
                        </label>
                        <label className="flex items-center gap-1 cursor-pointer">
                          <input
                            type="radio"
                            name={`source-${r.id}`}
                            checked={r.source === "literal"}
                            onChange={() => {
                              const next = inputs.map(ir => ir.id === r.id ? { ...ir, source: "literal" as const } : ir);
                              setInputs(next);
                              emit({ inputs: inputsToPayload(next) });
                            }}
                            className="w-3 h-3"
                          />
                          <span className="text-[10px] text-gray-500">字面值</span>
                        </label>
                        <div className="flex-1" />
                        <label className="flex items-center gap-1 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={r.required}
                            onChange={() => {
                              const next = inputs.map(ir => ir.id === r.id ? { ...ir, required: !ir.required } : ir);
                              setInputs(next);
                              emit({ inputs: inputsToPayload(next) });
                            }}
                            className="w-3 h-3"
                          />
                          <span className="text-[10px] text-gray-400">必填</span>
                        </label>
                      </div>

                      {/* Row 3: ref or literal value */}
                      {r.source === "reference" ? (
                        <RefInput
                          value={r.ref}
                          onChange={v => {
                            const next = inputs.map(ir => ir.id === r.id ? { ...ir, ref: v } : ir);
                            setInputs(next);
                          }}
                          onBlur={() => emit({ inputs: inputsToPayload(inputs) })}
                          upstreamOutputs={upstreamOutputs}
                        />
                      ) : (
                        <input
                          type="text"
                          value={r.value}
                          onChange={e => {
                            const next = inputs.map(ir => ir.id === r.id ? { ...ir, value: e.target.value } : ir);
                            setInputs(next);
                          }}
                          onBlur={() => emit({ inputs: inputsToPayload(inputs) })}
                          placeholder="固定值"
                          className="w-full px-2 py-1.5 text-xs border border-border rounded bg-white font-mono text-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-200"
                        />
                      )}
                    </div>
                  ))}
                </div>
              </div>
              )}

              {/* ── Outputs (read-only) ─────────────────── */}
              {((nodeType === "start" ? startOutputs : NODE_OUTPUTS[nodeType]) || []).length > 0 && (
                <div>
                  <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Outputs</label>
                  <div className="border border-border rounded-lg overflow-hidden">
                    {(nodeType === "start" ? startOutputs : NODE_OUTPUTS[nodeType] || []).map((o, i) => (
                      <div key={o.name} className={`flex items-center justify-between px-3 py-2 ${i % 2 === 0 ? "bg-white" : "bg-gray-50/50"} ${i > 0 ? "border-t border-border" : ""}`}>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-mono text-ink font-medium">{node?.id}.{o.name}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded font-mono">{o.type}</span>
                          <span className="text-[10px] text-gray-400 hidden sm:inline">{o.description}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

        </div>
      </div>
    </>
  );
}
