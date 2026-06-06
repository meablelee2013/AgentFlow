import { useState, useEffect, useRef } from "react";
import {
  Upload, Link, Database, CheckCircle2, Loader2,
  AlertCircle, Plus, Trash2, ChevronRight, FolderOpen,
} from "lucide-react";
import { api, type KnowledgeBaseItem } from "../api/client";

export function KnowledgeBase() {
  const [bases, setBases] = useState<KnowledgeBaseItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [selectedKbId, setSelectedKbId] = useState<string | null>(null);
  const [urlValue, setUrlValue] = useState("");
  const [ingesting, setIngesting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadBases = async () => {
    try {
      const data = await api.listBases();
      setBases(data);
    } catch { /* backend might not be running */ }
  };

  useEffect(() => { loadBases(); }, []);

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name) return;
    setCreating(true);
    try {
      const res = await fetch("/api/v1/knowledge/bases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (!res.ok) throw new Error("Failed");
      setNewName("");
      await loadBases();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Create failed");
    }
    setCreating(false);
  };

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Delete "${name}" and all its documents?`)) return;
    try {
      await fetch(`/api/v1/knowledge/bases/${id}`, { method: "DELETE" });
      if (selectedKbId === id) setSelectedKbId(null);
      await loadBases();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await api.upload(file, selectedKbId || undefined);
      await loadBases();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Upload failed");
    }
    setUploading(false);
    if (fileRef.current) fileRef.current.value = "";
  };

  const handleIngestUrl = async () => {
    const url = urlValue.trim();
    if (!url) return;
    setIngesting(true);
    try {
      await api.ingestUrl(url, selectedKbId || undefined);
      setUrlValue("");
      await loadBases();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Ingest failed");
    }
    setIngesting(false);
  };

  const selectedKb = bases.find((b) => b.id === selectedKbId);

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-ink tracking-tight">
            Knowledge Base
          </h1>
          <p className="text-sm text-gray-400 mt-1">
            Create separate bases for different teams or topics
          </p>
        </div>

        {/* Create new */}
        <div className="flex gap-2">
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="New base name..."
            className="px-3 py-1.5 text-sm rounded-lg border border-border bg-white
                       focus:outline-none focus:ring-2 focus:ring-ink/10
                       placeholder:text-gray-300 w-44"
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
          />
          <button
            onClick={handleCreate}
            disabled={creating || !newName.trim()}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg
                       bg-ink text-white hover:bg-slate-hover disabled:opacity-30
                       transition-colors"
          >
            <Plus size={14} />
            Create
          </button>
        </div>
      </div>

      {/* KB Selector + Upload */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        {/* KB List */}
        <div className="col-span-1 bg-white rounded-2xl border border-border shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b border-border flex items-center gap-2">
            <Database size={14} className="text-gray-400" />
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
              Bases
            </span>
            <span className="text-[10px] text-gray-400 font-mono ml-auto">
              {bases.length}
            </span>
          </div>
          <div className="divide-y divide-border/50 max-h-64 overflow-y-auto">
            {bases.length === 0 ? (
              <div className="px-4 py-8 text-center">
                <FolderOpen size={24} className="text-gray-200 mx-auto mb-2" />
                <p className="text-xs text-gray-400">No bases yet</p>
              </div>
            ) : (
              bases.map((kb) => (
                <button
                  key={kb.id}
                  onClick={() =>
                    setSelectedKbId(selectedKbId === kb.id ? null : kb.id)
                  }
                  className={`w-full px-4 py-3 flex items-center gap-2.5 text-left hover:bg-gray-50
                              transition-colors ${
                                selectedKbId === kb.id ? "bg-ink/[0.03] border-l-2 border-ink" : ""
                              }`}
                >
                  {kb.status === "ready" ? (
                    <CheckCircle2 size={14} className="text-accent shrink-0" />
                  ) : kb.status === "error" ? (
                    <AlertCircle size={14} className="text-red-400 shrink-0" />
                  ) : (
                    <Loader2 size={14} className="text-gray-300 animate-spin shrink-0" />
                  )}
                  <span className="flex-1 text-sm font-medium text-ink/80 truncate">
                    {kb.name}
                  </span>
                  <ChevronRight
                    size={14}
                    className={`text-gray-300 transition-transform shrink-0 ${
                      selectedKbId === kb.id ? "rotate-90" : ""
                    }`}
                  />
                </button>
              ))
            )}
          </div>
        </div>

        {/* Upload area */}
        <div className="col-span-2 space-y-3">
          {selectedKb && (
            <div className="flex items-center gap-2 px-4 py-2 rounded-xl bg-ink/5 text-sm">
              <span className="text-gray-500">Uploading to</span>
              <span className="font-semibold text-ink">{selectedKb.name}</span>
              <button
                onClick={() => setSelectedKbId(null)}
                className="ml-auto text-xs text-gray-400 hover:text-gray-600"
              >
                clear
              </button>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            {/* File upload */}
            <div
              onClick={() => fileRef.current?.click()}
              className="group p-5 rounded-2xl border-2 border-dashed border-border
                         hover:border-ink/30 hover:bg-ink/[0.02] transition-all cursor-pointer text-center"
            >
              <input
                ref={fileRef}
                type="file"
                onChange={handleUpload}
                className="hidden"
                accept=".pdf,.docx,.doc,.md,.markdown,.txt,.text,.log,.csv,.xlsx,.xls,.pptx,.ppt,.json,.epub,.html,.htm"
              />
              {uploading ? (
                <div className="flex flex-col items-center gap-2">
                  <Loader2 size={24} className="text-ink animate-spin" />
                  <span className="text-xs text-ink/60 font-medium">Processing...</span>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-2">
                  <div className="w-10 h-10 rounded-xl bg-ink/5 flex items-center justify-center group-hover:scale-110 transition-transform">
                    <Upload size={18} className="text-ink/60" />
                  </div>
                  <span className="text-sm font-medium text-ink/80">Upload File</span>
                  <span className="text-[11px] text-gray-400">17 formats supported</span>
                </div>
              )}
            </div>

            {/* URL ingest */}
            <div className="p-5 rounded-2xl border-2 border-dashed border-border hover:border-ink/30 hover:bg-ink/[0.02] transition-all">
              <div className="flex flex-col items-center gap-2 mb-3">
                <div className="w-10 h-10 rounded-xl bg-ink/5 flex items-center justify-center">
                  <Link size={18} className="text-ink/60" />
                </div>
                <span className="text-sm font-medium text-ink/80">Ingest URL</span>
                <span className="text-[11px] text-gray-400">Web page extraction</span>
              </div>
              <div className="flex gap-2">
                <input
                  type="url"
                  value={urlValue}
                  onChange={(e) => setUrlValue(e.target.value)}
                  placeholder="https://..."
                  className="flex-1 px-3 py-1.5 text-xs rounded-lg border border-border focus:outline-none focus:ring-2 focus:ring-ink/10"
                  onKeyDown={(e) => e.key === "Enter" && handleIngestUrl()}
                />
                <button
                  onClick={handleIngestUrl}
                  disabled={ingesting || !urlValue.trim()}
                  className="px-3 py-1.5 text-xs font-medium rounded-lg bg-ink text-white hover:bg-slate-hover disabled:opacity-30 transition-colors"
                >
                  {ingesting ? <Loader2 size={12} className="animate-spin" /> : "Go"}
                </button>
              </div>
            </div>
          </div>

          {/* Delete selected */}
          {selectedKb && (
            <div className="flex justify-end">
              <button
                onClick={() => handleDelete(selectedKb.id, selectedKb.name)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-red-500 hover:text-red-600
                           hover:bg-red-50 rounded-lg transition-colors"
              >
                <Trash2 size={12} />
                Delete "{selectedKb.name}"
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
