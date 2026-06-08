import { useState, useEffect } from "react";
import { X, Trash2, Brain, ChevronRight, AlertTriangle } from "lucide-react";
import { api } from "../../api/client";
import type { MemoryItem } from "../../api/client";

interface Props {
  open: boolean;
  onClose: () => void;
}

const CATEGORY_LABELS: Record<string, string> = {
  personal: "Personal",
  preference: "Preference",
  project: "Project",
  relationship: "Relationship",
  context: "Context",
};

const CATEGORY_COLORS: Record<string, string> = {
  personal: "bg-blue-50 text-blue-700 border-blue-200",
  preference: "bg-amber-50 text-amber-700 border-amber-200",
  project: "bg-emerald-50 text-emerald-700 border-emerald-200",
  relationship: "bg-violet-50 text-violet-700 border-violet-200",
  context: "bg-slate-50 text-slate-600 border-slate-200",
};

export function MemoryPanel({ open, onClose }: Props) {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);

  const loadMemories = async () => {
    setLoading(true);
    try {
      const data = await api.listMemories();
      setMemories(data.memories);
    } catch {
      // silently handle
    }
    setLoading(false);
  };

  useEffect(() => {
    if (open) loadMemories();
  }, [open]);

  const handleDelete = async (id: string) => {
    await api.deleteMemory(id);
    setMemories((prev) => prev.filter((m) => m.id !== id));
  };

  const handleClearAll = async () => {
    await api.clearMemories();
    setMemories([]);
    setShowClearConfirm(false);
  };

  // Group by category
  const grouped: Record<string, MemoryItem[]> = {};
  for (const m of memories) {
    (grouped[m.category] ||= []).push(m);
  }

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/10 z-40" onClick={onClose} />
      {/* Panel */}
      <div className="fixed right-0 top-0 bottom-0 w-80 border-l border-border bg-white flex flex-col shadow-lg z-50">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <div className="flex items-center gap-2">
            <Brain size={17} className="text-ink/60" />
            <span className="font-semibold text-sm text-ink">Memory</span>
            {memories.length > 0 && (
              <span className="text-[10px] bg-ink/5 px-1.5 py-0.5 rounded font-mono text-ink/50">
                {memories.length}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <X size={16} className="text-ink/40" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin w-5 h-5 border-2 border-ink/20 border-t-ink/60 rounded-full" />
            </div>
          ) : memories.length === 0 ? (
            <div className="py-12 px-4 text-center">
              <Brain size={28} className="text-gray-200 mx-auto mb-3" />
              <p className="text-xs text-gray-400 leading-relaxed">
                No memories yet.
                <br />
                Memories are extracted from conversations
                <br />
                and help me remember you.
              </p>
            </div>
          ) : (
            <div className="py-2">
              {Object.entries(grouped).map(([category, items]) => (
                <div key={category} className="mb-1">
                  {/* Category header */}
                  <div className="flex items-center gap-1.5 px-4 py-2">
                    <ChevronRight size={11} className="text-ink/30" />
                    <span className="text-[10px] font-mono uppercase tracking-wider text-ink/40">
                      {CATEGORY_LABELS[category] || category}
                    </span>
                    <span className="text-[9px] text-ink/25">({items.length})</span>
                  </div>
                  {/* Memory cards */}
                  {items.map((m) => (
                    <div
                      key={m.id}
                      className="mx-3 mb-1.5 px-3 py-2 rounded-lg border border-border/60 bg-gray-50/50 group hover:bg-gray-50 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <p className="text-[12px] text-ink/80 leading-relaxed">
                            {m.content}
                          </p>
                          <div className="flex items-center gap-2 mt-1.5">
                            <span
                              className={`text-[9px] px-1.5 py-0.5 rounded border ${
                                CATEGORY_COLORS[category] || CATEGORY_COLORS.context
                              }`}
                            >
                              {m.key}
                            </span>
                            {m.confidence < 1.0 && (
                              <span className="text-[9px] text-gray-400 font-mono">
                                {Math.round(m.confidence * 100)}%
                              </span>
                            )}
                          </div>
                        </div>
                        <button
                          onClick={() => handleDelete(m.id)}
                          className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-red-50 transition-all"
                          title="Delete memory"
                        >
                          <Trash2 size={12} className="text-gray-400 hover:text-red-500" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        {memories.length > 0 && (
          <div className="px-3 py-3 border-t border-border">
            {showClearConfirm ? (
              <div className="flex flex-col gap-2">
                <div className="flex items-start gap-2 px-1">
                  <AlertTriangle size={13} className="text-red-400 mt-0.5 shrink-0" />
                  <p className="text-[11px] text-red-600 leading-snug">
                    Delete all {memories.length} memories? This cannot be undone.
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleClearAll}
                    className="flex-1 px-2 py-1.5 text-[11px] font-medium bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors"
                  >
                    Delete All
                  </button>
                  <button
                    onClick={() => setShowClearConfirm(false)}
                    className="flex-1 px-2 py-1.5 text-[11px] font-medium border border-border rounded-lg hover:bg-gray-50 transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setShowClearConfirm(true)}
                className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-[11px] text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
              >
                <Trash2 size={12} />
                Clear all memories
              </button>
            )}
          </div>
        )}
      </div>
    </>
  );
}
