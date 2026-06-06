import { useState, useEffect } from "react";
import { Plus, MessageSquare, RefreshCw } from "lucide-react";
import { ChatWindow } from "../components/chat/ChatWindow";
import { useChatStore } from "../stores/chat";

interface Conv {
  thread_id: string;
  title: string;
  updated_at: string | null;
}

export function ChatApp() {
  const { threadId, loadHistory, clear } = useChatStore();
  const [convs, setConvs] = useState<Conv[]>([]);
  const [loadingConvs, setLoadingConvs] = useState(false);
  const [activeTid, setActiveTid] = useState<string | null>(threadId);

  const loadConvs = async () => {
    setLoadingConvs(true);
    try {
      const data = await fetch("/api/v1/chat/conversations").then((r) => r.json());
      setConvs(data);
    } catch { /* */ }
    setLoadingConvs(false);
  };

  useEffect(() => { loadConvs(); }, []);
  // Refresh list after each message
  // Sync active thread ID and refresh list when a new conversation is created
  useEffect(() => {
    if (threadId) {
      setActiveTid(threadId);
      loadConvs(); // Immediately refresh the conversation list
    }
  }, [threadId]);

  // Periodically refresh conversation list
  useEffect(() => {
    const i = setInterval(loadConvs, 5000);
    return () => clearInterval(i);
  }, []);

  const handleNew = () => {
    clear();
    setActiveTid(null);
  };

  const handleSelect = async (tid: string) => {
    setActiveTid(tid);
    await loadHistory(tid);
  };

  const formatDate = (iso: string | null) => {
    if (!iso) return "";
    const d = new Date(iso);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return d.toLocaleDateString();
  };

  return (
    <div className="flex h-full bg-warm">
      {/* Conversation sidebar */}
      <div className="w-60 border-r border-border bg-white shrink-0 flex flex-col">
        {/* New Chat button */}
        <div className="p-3">
          <button
            onClick={handleNew}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-xl border-2 border-dashed
                       border-border hover:border-ink/20 hover:bg-ink/[0.02] transition-all text-sm
                       font-medium text-ink/60"
          >
            <Plus size={15} />
            New Chat
          </button>
        </div>

        {/* Conversation list */}
        <div className="flex-1 overflow-y-auto">
          <div className="px-3 pb-1">
            <button
              onClick={loadConvs}
              className="flex items-center gap-1.5 text-[10px] text-gray-400 hover:text-gray-600
                         font-mono uppercase tracking-wider px-1 py-1"
            >
              <RefreshCw size={10} className={loadingConvs ? "animate-spin" : ""} />
              Conversations
            </button>
          </div>
          {convs.length === 0 && !loadingConvs && (
            <p className="px-4 py-8 text-xs text-gray-300 text-center">
              No conversations yet
            </p>
          )}
          <div className="space-y-0.5 px-2">
            {convs.map((c) => (
              <button
                key={c.thread_id}
                onClick={() => handleSelect(c.thread_id)}
                className={`w-full text-left px-3 py-2 rounded-lg text-[13px] transition-all ${
                  activeTid === c.thread_id
                    ? "bg-ink/5 font-medium text-ink"
                    : "text-gray-500 hover:bg-gray-50"
                }`}
              >
                <div className="flex items-center gap-2">
                  <MessageSquare size={13} className="shrink-0 opacity-50" />
                  <span className="truncate flex-1">{c.title}</span>
                </div>
                {c.updated_at && (
                  <span className="text-[10px] text-gray-300 font-mono ml-5">
                    {formatDate(c.updated_at)}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="px-3 py-3 border-t border-border">
          <p className="text-[10px] text-gray-400 font-mono text-center">
            {convs.length} conversation{convs.length !== 1 ? "s" : ""}
          </p>
        </div>
      </div>

      {/* Chat */}
      <div className="flex-1 min-w-0">
        <ChatWindow />
      </div>
    </div>
  );
}
