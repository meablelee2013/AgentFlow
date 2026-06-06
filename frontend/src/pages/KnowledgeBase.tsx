import { useState, useEffect, useRef } from "react";
import { Plus, Trash2, Upload, Link, FileText, Loader2, CheckCircle2, AlertCircle, Clock, ArrowLeft, Database } from "lucide-react";
import { api, type KnowledgeBaseItem } from "../api/client";

type DocStatus = "pending" | "processing" | "ready" | "error";

interface Doc {
  id: string;
  filename: string;
  file_type: string;
  chunk_count: number;
  status: DocStatus;
  created_at: string;
}

type View = "list" | "detail";

export function KnowledgeBase() {
  const [view, setView] = useState<View>("list");
  const [bases, setBases] = useState<KnowledgeBaseItem[]>([]);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [selectedKb, setSelectedKb] = useState<KnowledgeBaseItem | null>(null);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  // Staging area for files before upload
  interface StagedFile { id: string; file: File; addedAt: string; }
  const [stagedFiles, setStagedFiles] = useState<StagedFile[]>([]);
  const [urlValue, setUrlValue] = useState("");
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const SUPPORTED_FORMATS = [
    ".pdf", ".docx", ".doc", ".md", ".markdown",
    ".txt", ".csv", ".xlsx", ".xls", ".pptx", ".ppt",
    ".json", ".epub", ".html", ".htm",
  ];
  const ACCEPT = SUPPORTED_FORMATS.join(",");

  const addFiles = (files: FileList | File[]) => {
    const incoming = Array.from(files).filter(f =>
      SUPPORTED_FORMATS.some(ext => f.name.toLowerCase().endsWith(ext))
    );
    setStagedFiles(prev => [
      ...prev,
      ...incoming.map(f => ({
        id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        file: f,
        addedAt: new Date().toLocaleTimeString(),
      })),
    ]);
  };

  const removeStaged = (id: string) => {
    setStagedFiles(prev => prev.filter(f => f.id !== id));
  };

  const handleUploadAll = async () => {
    if (!selectedKb || stagedFiles.length === 0) return;
    setUploading(true);
    for (const sf of stagedFiles) {
      try {
        const form = new FormData();
        form.append("file", sf.file);
        form.append("knowledge_base_id", selectedKb.id);
        await fetch("/api/v1/knowledge/upload", { method: "POST", body: form });
        // Remove from staging one by one as they complete
        setStagedFiles(prev => prev.filter(f => f.id !== sf.id));
      } catch (err) {
        alert(`${sf.file.name}: ${err instanceof Error ? err.message : "Failed"}`);
      }
    }
    setUploading(false);
    await loadDocs(selectedKb.id);
    await loadBases();
  };

  const loadBases = async () => {
    try { setBases(await api.listBases()); } catch { /* */ }
  };

  const loadDocs = async (kbId: string) => {
    try {
      const res = await fetch(`/api/v1/knowledge/bases/${kbId}/documents`).then(r => r.json());
      setDocs(res);
    } catch { /* */ }
  };

  useEffect(() => { loadBases(); }, []);

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name) return;
    setCreating(true);
    try {
      await fetch("/api/v1/knowledge/bases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      setNewName("");
      await loadBases();
    } catch (err) { alert("Create failed"); }
    setCreating(false);
  };

  const handleDeleteKb = async (id: string, name: string) => {
    if (!confirm(`Delete "${name}" and all its documents?`)) return;
    await fetch(`/api/v1/knowledge/bases/${id}`, { method: "DELETE" });
    if (selectedKb?.id === id) { setSelectedKb(null); setView("list"); }
    await loadBases();
  };

  const handleDeleteDoc = async (docId: string) => {
    if (!selectedKb) return;
    await fetch(`/api/v1/knowledge/bases/${selectedKb.id}/documents/${docId}`, { method: "DELETE" });
    await loadDocs(selectedKb.id);
  };

  const handleSelectKb = async (kb: KnowledgeBaseItem) => {
    setSelectedKb(kb);
    setView("detail");
    await loadDocs(kb.id);
  };

  const handleUrlIngest = async () => {
    if (!urlValue.trim() || !selectedKb) return;
    setUploading(true);
    try {
      await api.ingestUrl(urlValue.trim(), selectedKb.id);
      setUrlValue("");
      await loadDocs(selectedKb.id);
      await loadBases();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Ingest failed");
    }
    setUploading(false);
  };

  const statusIcon = (s: string) => {
    switch (s) {
      case "ready": return <CheckCircle2 size={14} className="text-accent" />;
      case "processing": return <Loader2 size={14} className="text-blue-500 animate-spin" />;
      case "pending": return <Clock size={14} className="text-gray-300" />;
      case "error": return <AlertCircle size={14} className="text-red-400" />;
      default: return <Clock size={14} className="text-gray-300" />;
    }
  };

  // === LIST VIEW ===
  if (view === "list") {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-bold text-ink tracking-tight">Knowledge Bases</h1>
            <p className="text-sm text-gray-400 mt-1">Create separate bases for different teams or topics</p>
          </div>
          <div className="flex gap-2">
            <input
              type="text" value={newName}
              onChange={e => setNewName(e.target.value)}
              placeholder="Name..."
              className="px-3 py-1.5 text-sm rounded-lg border border-border bg-white focus:outline-none focus:ring-2 focus:ring-ink/10 w-40"
              onKeyDown={e => e.key === "Enter" && handleCreate()}
            />
            <button onClick={handleCreate} disabled={creating || !newName.trim()}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg bg-ink text-white hover:bg-slate-hover disabled:opacity-30 transition-colors">
              <Plus size={14} /> Create
            </button>
          </div>
        </div>

        {bases.length === 0 ? (
          <div className="text-center py-20">
            <Database size={36} className="text-gray-200 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-ink mb-1">No knowledge bases yet</h3>
            <p className="text-sm text-gray-400">Create one above to start uploading documents</p>
          </div>
        ) : (
          <div className="space-y-2">
            {bases.map(kb => (
              <button key={kb.id}
                onClick={() => handleSelectKb(kb)}
                className="w-full flex items-center gap-4 p-4 rounded-xl bg-white border border-border
                           hover:border-ink/20 hover:shadow-sm transition-all text-left group">
                <div className="w-10 h-10 rounded-xl bg-ink/5 flex items-center justify-center">
                  <Database size={20} className="text-ink/50" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-sm font-semibold text-ink">{kb.name}</h3>
                  <p className="text-xs text-gray-400 mt-0.5">{kb.id.slice(0, 8)}...</p>
                </div>
                <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full ${
                  kb.status === "ready" ? "bg-accent/10 text-accent" :
                  kb.status === "error" ? "bg-red-50 text-red-500" : "bg-blue-50 text-blue-500"
                }`}>{kb.status}</span>
                <button onClick={e => { e.stopPropagation(); handleDeleteKb(kb.id, kb.name); }}
                  className="p-1.5 rounded-lg text-gray-300 hover:text-red-400 hover:bg-red-50 opacity-0 group-hover:opacity-100 transition-all">
                  <Trash2 size={14} />
                </button>
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  // === DETAIL VIEW ===
  if (!selectedKb) return null;

  return (
    <div className="p-6 max-w-3xl mx-auto">
      {/* Back + Title */}
      <button onClick={() => { setView("list"); setSelectedKb(null); }}
        className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-ink mb-4 transition-colors">
        <ArrowLeft size={14} /> Back to bases
      </button>

      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-ink">{selectedKb.name}</h1>
          <p className="text-xs text-gray-400 font-mono mt-1">{selectedKb.id}</p>
        </div>
        <button onClick={() => handleDeleteKb(selectedKb.id, selectedKb.name)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-red-500 hover:bg-red-50 rounded-lg transition-colors">
          <Trash2 size={12} /> Delete base
        </button>
      </div>

      {/* === STAGING AREA (中转站) === */}
      <div
        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={e => { e.preventDefault(); setDragOver(false); }}
        onDrop={e => { e.preventDefault(); setDragOver(false); addFiles(e.dataTransfer.files); }}
        onClick={() => fileRef.current?.click()}
        className={`rounded-2xl border-2 border-dashed p-5 mb-4 transition-all cursor-pointer ${
          dragOver
            ? "border-accent bg-accent/[0.04] scale-[1.01]"
            : "border-border hover:border-ink/20 hover:bg-ink/[0.01]"
        }`}
      >
        <input ref={fileRef} type="file" multiple onChange={e => e.target.files && addFiles(e.target.files)}
          className="hidden" accept={ACCEPT} />
        <div className="flex flex-col items-center gap-2">
          <Upload size={20} className="text-ink/20" />
          <p className="text-sm text-gray-500">
            {dragOver ? "Drop files here" : "Drag & drop files or click to browse"}
          </p>
          <p className="text-xs text-gray-300">PDF, DOCX, PPTX, CSV, JSON, EPUB, HTML, MD, TXT</p>
        </div>
      </div>

      {/* Staged files list */}
      {stagedFiles.length > 0 && (
        <div className="mb-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
              Staged ({stagedFiles.length})
            </span>
            <div className="flex gap-2">
              <button onClick={() => setStagedFiles([])}
                className="text-[10px] text-gray-400 hover:text-red-500 font-mono transition-colors">
                Clear all
              </button>
              <button onClick={handleUploadAll}
                disabled={uploading}
                className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-medium rounded-lg
                           bg-ink text-white hover:bg-slate-hover disabled:opacity-30 transition-colors">
                <Upload size={12} />
                {uploading ? "Uploading..." : `Upload ${stagedFiles.length} file${stagedFiles.length > 1 ? "s" : ""}`}
              </button>
            </div>
          </div>
          <div className="space-y-1">
            {stagedFiles.map(sf => (
              <div key={sf.id}
                className="flex items-center gap-3 px-3 py-2 rounded-xl bg-white border border-border text-sm">
                <FileText size={14} className="text-ink/30 shrink-0" />
                <span className="flex-1 truncate font-medium text-ink/80">{sf.file.name}</span>
                <span className="text-[10px] text-gray-400 font-mono shrink-0">
                  {(sf.file.size / 1024).toFixed(1)} KB
                </span>
                <span className="text-[10px] text-gray-300 font-mono shrink-0">{sf.addedAt}</span>
                <button onClick={() => removeStaged(sf.id)}
                  className="text-gray-300 hover:text-red-400 transition-colors shrink-0">
                  <Trash2 size={12} />
                </button>
              </div>
            ))}
          </div>
          {uploading && (
            <div className="mt-2 h-1 bg-border rounded-full overflow-hidden">
              <div className="h-full bg-accent rounded-full animate-pulse transition-all"
                style={{ width: `${((stagedFiles.length) / Math.max(stagedFiles.length, 1)) * 100}%` }} />
            </div>
          )}
        </div>
      )}

      {/* URL ingest */}
      <div className="flex gap-2 mb-4">
        <input type="url" value={urlValue}
          onChange={e => setUrlValue(e.target.value)}
          placeholder="Or paste a URL to ingest..."
          className="flex-1 px-3 py-2 text-xs rounded-xl border border-border focus:outline-none focus:ring-2 focus:ring-ink/10"
          onKeyDown={e => e.key === "Enter" && urlValue.trim() && handleUrlIngest()}
        />
        {urlValue.trim() && (
          <button onClick={handleUrlIngest}
            disabled={uploading}
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-xl
                       bg-violet-500 text-white hover:bg-violet-600 disabled:opacity-30 transition-colors shrink-0">
            <Link size={12} /> Ingest URL
          </button>
        )}
      </div>

      {/* Documents List */}
      <div className="bg-white rounded-2xl border border-border shadow-sm overflow-hidden">
        <div className="px-5 py-3 border-b border-border flex items-center gap-2">
          <FileText size={14} className="text-gray-400" />
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Documents</span>
          <span className="text-[10px] text-gray-400 font-mono ml-auto">{docs.length} files</span>
        </div>
        {docs.length === 0 ? (
          <div className="px-5 py-12 text-center">
            <Upload size={28} className="text-gray-200 mx-auto mb-3" />
            <p className="text-sm text-gray-400">No documents yet</p>
            <p className="text-xs text-gray-300 mt-1">Select a file or enter a URL above</p>
          </div>
        ) : (
          <div className="divide-y divide-border/50">
            {docs.map(doc => (
              <div key={doc.id} className="px-5 py-3 flex items-center gap-3 hover:bg-gray-50/50 transition-colors group">
                {statusIcon(doc.status)}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-ink/80 truncate">{doc.filename}</span>
                    <span className="text-[10px] font-mono text-gray-400 shrink-0">.{doc.file_type}</span>
                  </div>
                  <div className="flex items-center gap-3 mt-0.5">
                    <span className={`text-[10px] font-mono ${
                      doc.status === "ready" ? "text-accent" :
                      doc.status === "error" ? "text-red-400" :
                      doc.status === "processing" ? "text-blue-500" : "text-gray-400"
                    }`}>{doc.status}</span>
                    {doc.chunk_count > 0 && (
                      <span className="text-[10px] text-gray-300 font-mono">{doc.chunk_count} chunks</span>
                    )}
                  </div>
                </div>
                <button onClick={() => handleDeleteDoc(doc.id)}
                  className="p-1.5 rounded-lg text-gray-300 hover:text-red-400 hover:bg-red-50 opacity-0 group-hover:opacity-100 transition-all">
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
