/** API client — typed wrapper around fetch for AgentFlow backend */
const BASE = "/api/v1";

// ── User identity ───────────────────────────────────────────────────
// Client-side UUID persisted in localStorage — used to scope user memories.
// Can be replaced with a real auth token when authentication is implemented.

function getUserId(): string {
  const key = "agentflow_user_id";
  let id = localStorage.getItem(key);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(key, id);
  }
  return id;
}

function authHeaders(): Record<string, string> {
  return { "X-User-Id": getUserId() };
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { "Content-Type": "application/json", ...authHeaders(), ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json();
}

export interface ChatResponse {
  thread_id: string;
  message: string;
  is_new: boolean;
}

export interface HistoryResponse {
  thread_id: string;
  messages: { role: string; content: string }[];
}

export interface KnowledgeBaseItem {
  id: string;
  name: string;
  status: string;
}

export interface QueryResponse {
  answer: string;
  chunks: { content: string; score: number; source: string }[];
}

export interface MemoryItem {
  id: string;
  category: string;
  key: string;
  content: string;
  confidence: number;
  is_active: boolean;
  source_conversation_id: string | null;
  created_at: string;
  updated_at: string;
}

export const api = {
  // Chat
  chat: (message: string, threadId?: string) =>
    request<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({ message, thread_id: threadId }),
    }),

  streamChat: (
    message: string,
    threadId: string | undefined,
    onToken: (t: string) => void,
    onDone: (threadId: string) => void
  ) => {
    const controller = new AbortController();
    fetch(`${BASE}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ message, thread_id: threadId }),
      signal: controller.signal,
    }).then(async (res) => {
      const reader = res.body?.getReader();
      if (!reader) return;
      const decoder = new TextDecoder();
      let tid = threadId || "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const text = decoder.decode(value);
        for (const line of text.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6);
          if (payload === "[DONE]") continue;
          if (payload.startsWith("[THREAD:")) {
            tid = payload.slice(8, -1);
            continue;
          }
          onToken(payload);
        }
      }
      onDone(tid);
    });
    return controller;
  },

  getHistory: (threadId: string) =>
    request<HistoryResponse>(`/chat/history/${threadId}`),

  listConversations: () =>
    request<{ thread_id: string; title: string; updated_at: string | null }[]>(
      "/chat/conversations"
    ),

  // Knowledge Base
  upload: (file: File, kbId?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (kbId) form.append("knowledge_base_id", kbId);
    return fetch(`${BASE}/knowledge/upload`, { method: "POST", body: form }).then(
      (r) => r.json()
    );
  },

  ingestUrl: (url: string, kbId?: string) =>
    request<KnowledgeBaseItem>("/knowledge/ingest-url", {
      method: "POST",
      body: JSON.stringify({ url, knowledge_base_id: kbId }),
    }),

  query: (question: string, kbId?: string, topK = 5) =>
    request<QueryResponse>("/knowledge/query", {
      method: "POST",
      body: JSON.stringify({ question, knowledge_base_id: kbId, top_k: topK }),
    }),

  listBases: () => request<KnowledgeBaseItem[]>("/knowledge/bases"),

  // User Memory
  listMemories: () =>
    request<{ memories: MemoryItem[]; total: number }>("/memory"),

  deleteMemory: (memoryId: string) =>
    request<{ ok: boolean; deleted: string }>(`/memory/${memoryId}`, {
      method: "DELETE",
    }),

  clearMemories: () =>
    request<{ ok: boolean; deleted: string }>("/memory", {
      method: "DELETE",
      body: JSON.stringify({ confirm: true }),
    }),
};
