import { useState, useEffect, useRef } from "react";
import { Upload, Link, Database, CheckCircle2, Loader2, Clock, AlertCircle } from "lucide-react";
import { api, type KnowledgeBaseItem } from "../api/client";

export function KnowledgeBase() {
  const [bases, setBases] = useState<KnowledgeBaseItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [urlValue, setUrlValue] = useState("");
  const [ingesting, setIngesting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadBases = async () => {
    setLoading(true);
    try {
      const data = await api.listBases();
      setBases(data);
    } catch {
      // backend might not be running
    }
    setLoading(false);
  };

  useEffect(() => { loadBases(); }, []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await api.upload(file);
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
      await api.ingestUrl(url);
      setUrlValue("");
      await loadBases();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Ingest failed");
    }
    setIngesting(false);
  };

  const statusIcon = (status: string) => {
    switch (status) {
      case "ready": return <CheckCircle2 size={14} className="text-green-500" />;
      case "processing": return <Loader2 size={14} className="text-blue-500 animate-spin" />;
      case "error": return <AlertCircle size={14} className="text-red-500" />;
      default: return <Clock size={14} className="text-gray-400" />;
    }
  };

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Knowledge Base</h1>
          <p className="text-sm text-gray-500 mt-1">Upload documents or web pages for RAG retrieval</p>
        </div>
      </div>

      {/* Upload Area */}
      <div className="grid grid-cols-2 gap-3 mb-6">
        {/* File Upload */}
        <div
          onClick={() => fileRef.current?.click()}
          className="group relative p-6 rounded-2xl border-2 border-dashed border-gray-200
                     hover:border-blue-300 hover:bg-blue-50/50 transition-all cursor-pointer
                     text-center"
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
              <Loader2 size={28} className="text-blue-500 animate-spin" />
              <span className="text-sm text-blue-600 font-medium">Processing...</span>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2">
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-50 to-blue-100 flex items-center justify-center group-hover:scale-110 transition-transform">
                <Upload size={22} className="text-blue-500" />
              </div>
              <span className="text-sm font-medium text-gray-700">Upload File</span>
              <span className="text-xs text-gray-400">PDF, DOCX, PPTX, CSV, JSON, EPUB, HTML...</span>
            </div>
          )}
        </div>

        {/* URL Ingest */}
        <div className="p-6 rounded-2xl border-2 border-dashed border-gray-200 hover:border-violet-300 hover:bg-violet-50/50 transition-all">
          <div className="flex flex-col items-center gap-2 mb-3">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-violet-50 to-violet-100 flex items-center justify-center">
              <Link size={22} className="text-violet-500" />
            </div>
            <span className="text-sm font-medium text-gray-700">Ingest URL</span>
            <span className="text-xs text-gray-400">Web page content extraction</span>
          </div>
          <div className="flex gap-2">
            <input
              type="url"
              value={urlValue}
              onChange={(e) => setUrlValue(e.target.value)}
              placeholder="https://..."
              className="flex-1 px-3 py-1.5 text-xs rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-violet-500/20"
              onKeyDown={(e) => e.key === "Enter" && handleIngestUrl()}
            />
            <button
              onClick={handleIngestUrl}
              disabled={ingesting || !urlValue.trim()}
              className="px-3 py-1.5 text-xs font-medium rounded-lg bg-violet-500 text-white hover:bg-violet-600 disabled:opacity-40 transition-colors"
            >
              {ingesting ? <Loader2 size={12} className="animate-spin" /> : "Go"}
            </button>
          </div>
        </div>
      </div>

      {/* Knowledge Base List */}
      <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden shadow-sm">
        <div className="px-5 py-3 border-b border-gray-50 flex items-center gap-2">
          <Database size={15} className="text-gray-400" />
          <span className="text-sm font-medium text-gray-600">
            {bases.length} Knowledge Base{bases.length !== 1 ? "s" : ""}
          </span>
          {loading && <Loader2 size={14} className="text-gray-400 animate-spin ml-auto" />}
        </div>
        {bases.length === 0 ? (
          <div className="px-5 py-12 text-center">
            <Database size={32} className="text-gray-200 mx-auto mb-3" />
            <p className="text-sm text-gray-400">No knowledge bases yet</p>
            <p className="text-xs text-gray-300 mt-1">Upload a file or ingest a URL to get started</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-50">
            {bases.map((kb) => (
              <div
                key={kb.id}
                className="px-5 py-3 flex items-center gap-3 hover:bg-gray-50/50 transition-colors"
              >
                {statusIcon(kb.status)}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-700 truncate">{kb.name}</p>
                  <p className="text-xs text-gray-400">{kb.id.slice(0, 8)}...</p>
                </div>
                <span
                  className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${
                    kb.status === "ready"
                      ? "bg-green-50 text-green-600"
                      : kb.status === "error"
                        ? "bg-red-50 text-red-600"
                        : "bg-blue-50 text-blue-600"
                  }`}
                >
                  {kb.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
