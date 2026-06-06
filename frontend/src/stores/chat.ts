/** Zustand store for chat state management */
import { create } from "zustand";
import { api, type ChatResponse } from "../api/client";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface ChatState {
  messages: Message[];
  threadId: string | null;
  loading: boolean;
  streaming: string; // current streaming token

  send: (content: string) => Promise<void>;
  loadHistory: (tid: string) => Promise<void>;
  clear: () => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  threadId: null,
  loading: false,
  streaming: "",

  send: async (content: string) => {
    const { threadId } = get();
    set({ loading: true, streaming: "" });

    // Add user message immediately
    set((s) => ({
      messages: [...s.messages, { role: "user", content }],
    }));

    try {
      const res: ChatResponse = await api.chat(content, threadId || undefined);
      set((s) => ({
        messages: [
          ...s.messages,
          { role: "assistant", content: res.message },
        ],
        threadId: res.thread_id,
        loading: false,
      }));
    } catch (err) {
      set((s) => ({
        messages: [
          ...s.messages,
          {
            role: "assistant",
            content: `Error: ${err instanceof Error ? err.message : "Failed to send"}`,
          },
        ],
        loading: false,
      }));
    }
  },

  loadHistory: async (tid: string) => {
    try {
      const hist = await api.getHistory(tid);
      set({
        messages: hist.messages.map((m) => ({
          role: m.role as "user" | "assistant",
          content: m.content,
        })),
        threadId: tid,
      });
    } catch {
      // thread not found, start fresh
    }
  },

  clear: () => set({ messages: [], threadId: null, streaming: "" }),
}));
