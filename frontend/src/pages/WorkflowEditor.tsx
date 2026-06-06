import { useCallback, useState, useRef } from "react";
import type { DragEvent } from "react";
import {
  ReactFlow, Controls, Background, MiniMap, addEdge,
  useNodesState, useEdgesState, BackgroundVariant, Panel, MarkerType,
} from "@xyflow/react";
import type { Connection, Node, Edge } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Save, Play, MessageSquare, Database, Wrench,
         GitBranch, Repeat, UserCheck } from "lucide-react";

// ── Node type palette ──────────────────────────────────────

const NODE_TYPES_PALETTE = [
  { type: "chat", label: "Chat", icon: MessageSquare, color: "#3b82f6" },
  { type: "rag", label: "RAG", icon: Database, color: "#8b5cf6" },
  { type: "tool", label: "Tool", icon: Wrench, color: "#f59e0b" },
  { type: "condition", label: "Condition", icon: GitBranch, color: "#ef4444" },
  { type: "loop", label: "Loop", icon: Repeat, color: "#06b6d4" },
  { type: "hitl", label: "HITL", icon: UserCheck, color: "#10b981" },
];

const START_NODE: Node = {
  id: "start", type: "default",
  position: { x: 80, y: 80 },
  data: { label: "START" },
  style: { background: "#1a1a1a", color: "#fff", border: "none", borderRadius: 20, fontWeight: 600, fontSize: 12, padding: "8px 20px" },
};

const END_NODE: Node = {
  id: "end", type: "default",
  position: { x: 80, y: 400 },
  data: { label: "END" },
  style: { background: "#faf7f2", color: "#1a1a1a", border: "2px solid #1a1a1a", borderRadius: 20, fontWeight: 600, fontSize: 12, padding: "8px 20px" },
};

const initialNodes: Node[] = [START_NODE, END_NODE];
const initialEdges: Edge[] = [];

// ── Custom Node Component ───────────────────────────────────

import type { NodeProps } from "@xyflow/react";

function CustomNode({ data, type }: { data: Record<string, unknown>; type: string }) {
  const colors: Record<string, string> = {
    chat: "border-blue-400 bg-blue-50",
    rag: "border-violet-400 bg-violet-50",
    tool: "border-amber-400 bg-amber-50",
    condition: "border-red-400 bg-red-50",
    loop: "border-cyan-400 bg-cyan-50",
    hitl: "border-emerald-400 bg-emerald-50",
  };
  const labels: Record<string, string> = {
    chat: "Chat", rag: "RAG", tool: "Tool",
    condition: "Condition", loop: "Loop", hitl: "HITL",
  };

  return (
    <div className={`px-4 py-2.5 rounded-xl border-2 shadow-sm min-w-[120px] text-center ${colors[type] || "border-gray-200 bg-white"}`}>
      <p className="text-xs font-semibold text-ink/80">{labels[type] || type}</p>
      {data?.label ? <p className="text-[10px] text-gray-400 mt-0.5 truncate max-w-[140px]">{String(data.label)}</p> : null}
    </div>
  );
}

const nodeTypes = {
  chat: (props: NodeProps) => <CustomNode {...props} type="chat" />,
  rag: (props: NodeProps) => <CustomNode {...props} type="rag" />,
  tool: (props: NodeProps) => <CustomNode {...props} type="tool" />,
  condition: (props: NodeProps) => <CustomNode {...props} type="condition" />,
  loop: (props: NodeProps) => <CustomNode {...props} type="loop" />,
  hitl: (props: NodeProps) => <CustomNode {...props} type="hitl" />,
};

// ── Page Component ──────────────────────────────────────────

export function WorkflowEditor() {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [wfName, setWfName] = useState("Untitled");
  const [saving, setSaving] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [execOutput, setExecOutput] = useState("");
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [reactFlowInstance, setReactFlowInstance] = useState<any>(null);

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds: Edge[]) => addEdge({ ...params, markerEnd: { type: MarkerType.ArrowClosed } }, eds)),
    [setEdges]
  );

  // Drag from palette → drop on canvas
  const onDragOver = useCallback((e: DragEvent) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; }, []);

  const onDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      const type = e.dataTransfer.getData("application/reactflow");
      if (!type || !reactFlowWrapper.current || !reactFlowInstance) return;

      const bounds = reactFlowWrapper.current.getBoundingClientRect();
      const position = reactFlowInstance.screenToFlowPosition({
        x: e.clientX - bounds.left,
        y: e.clientY - bounds.top,
      });

      const newNode: Node = {
        id: `${type}-${Date.now()}`,
        type,
        position,
        data: { label: type.charAt(0).toUpperCase() + type.slice(1) },
        style: { fontSize: 12 },
      };
      setNodes((nds: Node[]) => [...nds, newNode]);
    },
    [reactFlowInstance, setNodes]
  );

  const handleSave = async () => {
    setSaving(true);
    try {
      await fetch("/api/v1/workflows", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: wfName,
          nodes: nodes.map((n: Node) => ({ id: n.id, type: n.type, position: n.position, data: n.data })),
          edges: edges.map((e: Edge) => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle })),
        }),
      });
    } catch (err) { /* */ }
    setSaving(false);
  };

  const handleExecute = async () => {
    setExecuting(true);
    setExecOutput("Executing...");
    try {
      // Save first
      const saveRes = await fetch("/api/v1/workflows", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: wfName,
          nodes: nodes.map((n: Node) => ({ id: n.id, type: n.type, position: n.position, data: n.data })),
          edges: edges.map((e: Edge) => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle })),
        }),
      });
      const saved = await saveRes.json();
      // Execute
      const execRes = await fetch(`/api/v1/workflows/${saved.id}/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: "Hello! Test the workflow." }),
      });
      const result = await execRes.json();
      setExecOutput(result.output || JSON.stringify(result));
    } catch (err) {
      setExecOutput(`Error: ${err}`);
    }
    setExecuting(false);
  };

  return (
    <div className="flex h-full bg-warm">
      {/* Palette Sidebar */}
      <div className="w-48 border-r border-border bg-white p-3 flex flex-col gap-3 shrink-0">
        <div>
          <input
            value={wfName}
            onChange={e => setWfName(e.target.value)}
            className="w-full px-2 py-1.5 text-sm font-semibold bg-transparent border-b border-border focus:outline-none focus:border-ink/30"
          />
        </div>
        <p className="text-[10px] text-gray-400 font-mono uppercase tracking-wider">Nodes</p>
        {NODE_TYPES_PALETTE.map(({ type, label, icon: Icon, color }) => (
          <div
            key={type}
            draggable
            onDragStart={(e) => { e.dataTransfer.setData("application/reactflow", type); e.dataTransfer.effectAllowed = "move"; }}
            className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border cursor-grab
                       hover:shadow-sm hover:-translate-y-0.5 transition-all active:cursor-grabbing bg-white"
          >
            <div className="w-6 h-6 rounded flex items-center justify-center" style={{ background: `${color}18` }}>
              <Icon size={12} style={{ color }} />
            </div>
            <span className="text-xs font-medium text-ink/70">{label}</span>
          </div>
        ))}

        <div className="mt-auto space-y-2 pt-4 border-t border-border">
          <button onClick={handleSave} disabled={saving}
            className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg
                       bg-ink text-white hover:bg-slate-hover disabled:opacity-50 transition-colors">
            <Save size={12} /> {saving ? "Saving..." : "Save"}
          </button>
          <button onClick={handleExecute} disabled={executing}
            className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg
                       bg-accent text-black hover:bg-accent-hover disabled:opacity-50 transition-colors">
            <Play size={12} /> {executing ? "Running..." : "Execute"}
          </button>
        </div>
      </div>

      {/* Canvas */}
      <div className="flex-1" ref={reactFlowWrapper}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onInit={setReactFlowInstance}
          onDragOver={onDragOver}
          onDrop={onDrop}
          nodeTypes={nodeTypes}
          fitView
          deleteKeyCode={["Backspace", "Delete"]}
          style={{ background: "#faf7f2" }}
        >
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
