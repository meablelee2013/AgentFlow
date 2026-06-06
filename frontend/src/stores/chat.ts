/** Zustand store for chat state management with streaming support */
import { create } from "zustand";
import { api } from "../api/client";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

interface ChatState {
  messages: Message[];
  threadId: string | null;
  loading: boolean;
  streaming: string;
  editingId: string | null;

  send: (content: string) => Promise<void>;
  loadHistory: (tid: string) => Promise<void>;
  editMessage: (id: string, content: string) => void;
  clear: () => void;
}

let msgCounter = 0;
const nextId = () => `msg-${++msgCounter}`;

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  threadId: null,
  loading: false,
  streaming: "",
  editingId: null,

  send: async (content: string) => {
    const { threadId } = get();
    const userMsg: Message = { id: nextId(), role: "user", content };
    const assistantId = nextId();

    set((s) => ({
      messages: [...s.messages, userMsg],
      loading: true,
      streaming: "",
    }));

    // Accumulate streamed tokens
    let fullResponse = "";
    const controller = api.streamChat(
      content,
      threadId || undefined,
      (token) => {
        fullResponse += token;
        set({ streaming: fullResponse });
      },
      (finalTid) => {
        set((s) => ({
          messages: [
            ...s.messages,
            { id: assistantId, role: "assistant", content: fullResponse },
          ],
          threadId: finalTid || s.threadId,
          loading: false,
          streaming: "",
        }));
      }
    );

    // Expose controller for abort (future: cancel button)
    (window as unknown as Record<string, unknown>).__abortStream = () =>
      controller.abort();
  },

  loadHistory: async (tid: string) => {
    try {
      const hist = await api.getHistory(tid);
      set({
        messages: hist.messages.map((m) => ({
          id: nextId(),
          role: m.role as "user" | "assistant",
          content: m.content,
        })),
        threadId: tid,
      });
    } catch {
      // thread not found, start fresh
    }
  },

  editMessage: (id: string, content: string) => {
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === id ? { ...m, content } : m
      ),
    }));
  },

  clear: () =>
    set({ messages: [], threadId: null, streaming: "", editingId: null }),
}));
