import { useCallback, useState, useRef, useEffect } from "react";
import type { DragEvent } from "react";
import {
  ReactFlow, Controls, Background, MiniMap, addEdge,
  useNodesState, useEdgesState, BackgroundVariant, Panel, MarkerType,
  Handle, Position,
} from "@xyflow/react";
import type { Connection, Node, Edge } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Save, Play, MessageSquare, Database, Wrench,
         GitBranch, Repeat, UserCheck, Plus, ArrowLeft, Workflow } from "lucide-react";

const NODE_PALETTE = [
  { type: "chat", label: "Chat", icon: MessageSquare, color: "#3b82f6" },
  { type: "rag", label: "RAG", icon: Database, color: "#8b5cf6" },
  { type: "tool", label: "Tool", icon: Wrench, color: "#f59e0b" },
  { type: "condition", label: "Condition", icon: GitBranch, color: "#ef4444" },
  { type: "loop", label: "Loop", icon: Repeat, color: "#06b6d4" },
  { type: "hitl", label: "HITL", icon: UserCheck, color: "#10b981" },
];

const START_NODE: Node = {
  id: "start", type: "startNode", position: { x: 50, y: 200 }, data: {},
};
const END_NODE: Node = {
  id: "end", type: "endNode", position: { x: 700, y: 200 }, data: {},
};

// ── Custom Nodes with + button ─────────────────────────────

function CustomNode({ id, data, type }: { id: string; data: Record<string, unknown>; type: string }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const labels: Record<string, string> = {
    chat: "Chat", rag: "RAG", tool: "Tool", condition: "Condition", loop: "Loop", hitl: "HITL",
  };
  const colors: Record<string, string> = {
    chat: "border-blue-400 bg-blue-50", rag: "border-violet-400 bg-violet-50",
    tool: "border-amber-400 bg-amber-50", condition: "border-red-400 bg-red-50",
    loop: "border-cyan-400 bg-cyan-50", hitl: "border-emerald-400 bg-emerald-50",
  };
  const onAdd = data?.onAddNode as ((sourceId: string, nodeType: string) => void) | undefined;

  return (
    <div className={`relative px-4 py-2.5 rounded-xl border-2 shadow-sm min-w-[140px] text-center ${colors[type] || "border-gray-200 bg-white"}`}>
      <Handle type="target" position={Position.Left} className="!w-2.5 !h-2.5 !bg-ink/40 !border-2 !border-white" />
      <p className="text-xs font-semibold text-ink/80">{labels[type] || type}</p>
      {data?.label ? <p className="text-[10px] text-gray-400 mt-0.5 truncate">{String(data.label)}</p> : null}
      <Handle type="source" position={Position.Right} className="!w-2.5 !h-2.5 !bg-ink/40 !border-2 !border-white" />

      {/* + Button */}
      <button
        onClick={(e) => { e.stopPropagation(); setMenuOpen(!menuOpen); }}
        className="absolute -right-3 top-1/2 -translate-y-1/2 w-6 h-6 rounded-full bg-ink text-white
                   flex items-center justify-center hover:scale-110 transition-transform shadow-md z-10"
        title="Add next node"
      >
        <Plus size={12} />
      </button>

      {/* Dropdown */}
      {menuOpen && (
        <div className="absolute left-full ml-3 top-0 bg-white border border-border rounded-xl shadow-xl z-50 py-1 min-w-[160px]"
             onClick={e => e.stopPropagation()}>
          <p className="px-3 py-1.5 text-[10px] text-gray-400 font-mono uppercase tracking-wider">Add Node</p>
          {NODE_PALETTE.map(({ type: nt, label, icon: Icon, color }) => (
            <button
              key={nt}
              onClick={() => { setMenuOpen(false); onAdd?.(id, nt); }}
              className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-gray-50 transition-colors text-left"
            >
              <div className="w-5 h-5 rounded flex items-center justify-center" style={{ background: `${color}20` }}>
                <Icon size={10} style={{ color }} />
              </div>
              {label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function StartNode({ id, data }: { id: string; data: Record<string, unknown> }) {
  const onAdd = data?.onAddNode as ((sourceId: string, nodeType: string) => void) | undefined;
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <div className="relative px-5 py-2.5 bg-ink text-white rounded-full font-semibold text-xs shadow-md">
      <Handle type="source" position={Position.Right} className="!w-2.5 !h-2.5 !bg-ink !border-2 !border-white" />
      START
      <button
        onClick={(e) => { e.stopPropagation(); setMenuOpen(!menuOpen); }}
        className="absolute -right-3 top-1/2 -translate-y-1/2 w-6 h-6 rounded-full bg-accent text-black
                   flex items-center justify-center hover:scale-110 transition-transform shadow-md z-10"
      >
        <Plus size={12} strokeWidth={3} />
      </button>
      {menuOpen && (
        <div className="absolute left-full ml-3 top-0 bg-white border border-border rounded-xl shadow-xl z-50 py-1 min-w-[160px]"
             onClick={e => e.stopPropagation()}>
          <p className="px-3 py-1.5 text-[10px] text-gray-400 font-mono uppercase tracking-wider">Add Node</p>
          {NODE_PALETTE.map(({ type: nt, label, icon: Icon, color }) => (
            <button key={nt} onClick={() => { setMenuOpen(false); onAdd?.(id, nt); }}
              className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-gray-50 transition-colors text-left">
              <div className="w-5 h-5 rounded flex items-center justify-center" style={{ background: `${color}20` }}>
                <Icon size={10} style={{ color }} />
              </div>
              {label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function EndNode() {
  return (
    <div className="relative px-5 py-2.5 bg-warm text-ink border-2 border-ink rounded-full font-semibold text-xs">
      <Handle type="target" position={Position.Left} className="!w-2.5 !h-2.5 !bg-ink !border-2 !border-white" /> END
    </div>
  );
}

// ── Workflow List Item ─────────────────────────────────────

interface WFItem { id: string; name: string; description: string; nodes: unknown[]; edges: unknown[] }

function mapType(t: string | undefined) {
  if (t === "startNode") return "start";
  if (t === "endNode") return "end";
  return t || "chat";
}

// ── Editor View ────────────────────────────────────────────

function EditorView({ wf, onBack }: { wf: WFItem | null; onBack: () => void }) {
  const [wfName, setWfName] = useState(wf?.name || "Untitled");
  const [saving, setSaving] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [execOutput, setExecOutput] = useState("");

  const initNodesRaw: Node[] = wf?.nodes?.length
    ? (wf.nodes as any[]).map((n: any) => ({ ...n, type: n.type === "start" ? "startNode" : n.type === "end" ? "endNode" : n.type }))
    : [START_NODE, END_NODE];

  const initEdges: Edge[] = wf?.edges?.length
    ? (wf.edges as any[]).map((e: any) => ({ ...e, markerEnd: { type: MarkerType.ArrowClosed } }))
    : [];

  const [nodes, setNodes, onNodesChange] = useNodesState(initNodesRaw);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initEdges);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [rfInstance, setRfInstance] = useState<any>(null);

  // Add-node callback: creates a new node and auto-connects from source
  const addNodeAfter = useCallback((sourceId: string, nodeType: string) => {
    setNodes((nds: Node[]) => {
      const src = nds.find(n => n.id === sourceId);
      if (!src) return nds;
      const newNode: Node = {
        id: `${nodeType}-${Date.now()}`,
        type: nodeType,
        position: { x: src.position.x + 220, y: src.position.y + (Math.random() - 0.5) * 100 },
        data: { label: nodeType, onAddNode: addNodeAfter },
      };
      setEdges((eds: Edge[]) => [...eds, {
        id: `e-${sourceId}-${newNode.id}`, source: sourceId, target: newNode.id,
        markerEnd: { type: MarkerType.ArrowClosed },
      }]);
      return [...nds, newNode];
    });
  }, [setNodes, setEdges]);

  // Inject onAddNode into all non-END nodes
  useEffect(() => {
    setNodes((nds: Node[]) =>
      nds.map(n => n.type === "endNode" ? n : { ...n, data: { ...n.data, onAddNode: addNodeAfter } })
    );
  }, [addNodeAfter]);

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds: Edge[]) => addEdge({ ...params, markerEnd: { type: MarkerType.ArrowClosed } }, eds)),
    [setEdges]
  );

  const onDragOver = useCallback((e: DragEvent) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; }, []);
  const onDrop = useCallback((e: DragEvent) => {
    e.preventDefault();
    const type = e.dataTransfer.getData("application/reactflow");
    if (!type || !wrapperRef.current || !rfInstance) return;
    const bounds = wrapperRef.current.getBoundingClientRect();
    const pos = rfInstance.screenToFlowPosition({ x: e.clientX - bounds.left, y: e.clientY - bounds.top });
    const id = `${type}-${Date.now()}`;
    setNodes((nds: Node[]) => [...nds, { id, type, position: pos, data: { label: type, onAddNode: addNodeAfter } }]);
  }, [rfInstance, setNodes, addNodeAfter]);

  const buildPayload = () => ({
    name: wfName,
    nodes: nodes.map((n: Node) => ({ id: n.id, type: mapType(n.type), position: n.position, data: { label: n.data?.label } })),
    edges: edges.map((e: Edge) => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle })),
  });

  const handleSave = async () => {
    setSaving(true);
    await fetch("/api/v1/workflows", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(buildPayload()) });
    setSaving(false);
  };

  const handleExecute = async () => {
    setExecuting(true); setExecOutput("Executing...");
    try {
      const sr = await fetch("/api/v1/workflows", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(buildPayload()) });
      const saved = await sr.json();
      const er = await fetch(`/api/v1/workflows/${saved.id}/execute`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: "Hello!" }) });
      const result = await er.json();
      setExecOutput(result.output || JSON.stringify(result));
    } catch (err: any) { setExecOutput(`Error: ${err}`); }
    setExecuting(false);
  };

  const nodeTypes = {
    startNode: StartNode,
    endNode: EndNode,
    chat: (p: any) => <CustomNode {...p} type="chat" />,
    rag: (p: any) => <CustomNode {...p} type="rag" />,
    tool: (p: any) => <CustomNode {...p} type="tool" />,
    condition: (p: any) => <CustomNode {...p} type="condition" />,
    loop: (p: any) => <CustomNode {...p} type="loop" />,
    hitl: (p: any) => <CustomNode {...p} type="hitl" />,
  };

  return (
    <div className="flex h-full bg-warm">
      {/* Sidebar controls only */}
      <div className="w-48 border-r border-border bg-white p-3 flex flex-col gap-3 shrink-0">
        <button onClick={onBack} className="flex items-center gap-1 text-xs text-gray-400 hover:text-ink transition-colors">
          <ArrowLeft size={12} /> Back
        </button>
        <input value={wfName} onChange={e => setWfName(e.target.value)}
          className="w-full px-2 py-1.5 text-sm font-semibold bg-transparent border-b border-border focus:outline-none focus:border-ink/30" />
        <div className="flex-1" />
        <button onClick={handleSave} disabled={saving}
          className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg bg-ink text-white hover:bg-slate-hover disabled:opacity-50 transition-colors">
          <Save size={12} /> {saving ? "Saving..." : "Save"}
        </button>
        <button onClick={handleExecute} disabled={executing}
          className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg bg-accent text-black hover:bg-accent-hover disabled:opacity-50 transition-colors">
          <Play size={12} /> {executing ? "Running..." : "Execute"}
        </button>
      </div>

      {/* Canvas */}
      <div className="flex-1" ref={wrapperRef}>
        <ReactFlow
          nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
          onConnect={onConnect} onInit={setRfInstance} onDragOver={onDragOver} onDrop={onDrop}
          nodeTypes={nodeTypes} fitView deleteKeyCode={["Backspace", "Delete"]}
          style={{ background: "#faf7f2" }}>
          <Controls className="bg-white border-border rounded-lg shadow-sm" />
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#e8e5e0" />
          <MiniMap style={{ background: "#faf7f2", border: "1px solid #e8e5e0" }} nodeColor="#1a1a1a" />
          {execOutput && (
            <Panel position="bottom-center">
              <div className="bg-ink text-white px-4 py-2 rounded-xl text-xs font-mono max-w-lg max-h-32 overflow-y-auto shadow-lg">
                {execOutput}
                <button onClick={() => setExecOutput("")} className="ml-2 text-gray-400 hover:text-white">×</button>
              </div>
            </Panel>
          )}
        </ReactFlow>
      </div>
    </div>
  );
}

// ── List View ──────────────────────────────────────────────

function ListView({ onCreate, onEdit }: { onCreate: () => void; onEdit: (wf: WFItem) => void }) {
  const [workflows, setWorkflows] = useState<WFItem[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try { setWorkflows(await fetch("/api/v1/workflows").then(r => r.json())); } catch { /* */ }
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-ink tracking-tight">Workflows</h1>
          <p className="text-sm text-gray-400 mt-1">Visual agent workflow builder</p>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-4">
        <button onClick={onCreate}
          className="group p-6 rounded-2xl border-2 border-dashed border-border hover:border-ink/30
                     hover:bg-ink/[0.02] transition-all text-left min-h-[160px] flex flex-col items-center justify-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-ink/5 flex items-center justify-center group-hover:scale-110 transition-transform">
            <Plus size={24} className="text-ink/30" />
          </div>
          <p className="text-sm font-medium text-ink/50">Create New Workflow</p>
        </button>
        {workflows.map(wf => (
          <button key={wf.id} onClick={() => onEdit(wf)}
            className="p-6 rounded-2xl bg-white border border-border hover:border-ink/20 hover:shadow-sm
                       transition-all text-left group min-h-[160px] flex flex-col">
            <div className="w-10 h-10 rounded-xl bg-ink/5 flex items-center justify-center mb-3">
              <Workflow size={20} className="text-ink/50" />
            </div>
            <h3 className="text-sm font-semibold text-ink truncate">{wf.name}</h3>
            <p className="text-xs text-gray-400 mt-1">
              {String(wf.nodes?.length || 0)} nodes · {String(wf.edges?.length || 0)} edges
            </p>
            <p className="text-[10px] text-gray-300 mt-auto pt-3 font-mono">{wf.id.slice(0, 8)}...</p>
          </button>
        ))}
        {!loading && workflows.length === 0 && (
          <div className="col-span-2 flex items-center text-sm text-gray-400 pl-2">
            No workflows yet — click "Create New" to build your first one.
          </div>
        )}
      </div>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────

export function WorkflowEditor() {
  const [view, setView] = useState<"list" | "editor">("list");
  const [editingWf, setEditingWf] = useState<WFItem | null>(null);

  return view === "list"
    ? <ListView onCreate={() => { setEditingWf(null); setView("editor"); }} onEdit={wf => { setEditingWf(wf); setView("editor"); }} />
    : <EditorView wf={editingWf} onBack={() => setView("list")} />;
}
