import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useChatStore } from "../../stores/chat";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";

export function ChatWindow() {
  const { messages, loading, streaming, send } = useChatStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  return (
    <div className="flex flex-col h-full bg-warm">
      {/* Header */}
      <div className="border-b border-border bg-white px-6 py-3.5">
        <div className="max-w-3xl mx-auto flex items-center gap-3">
          <div className={`w-2 h-2 rounded-full ${loading ? "bg-accent animate-pulse" : "bg-accent"}`} />
          <div>
            <h2 className="text-[13px] font-semibold text-ink tracking-tight">
              AI Assistant
            </h2>
            <p className="text-[10px] text-gray-400 font-mono">
              deepseek-chat · {loading ? "streaming" : "online"}
            </p>
          </div>
          <div className="ml-auto">
            <span className="text-[10px] text-gray-400 font-mono">
              {messages.length} msgs
            </span>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-8 space-y-5">
          {messages.length === 0 && !streaming && (
            <div className="text-center py-24">
              <p className="font-mono text-[11px] text-gray-400 tracking-widest uppercase mb-6">
                New Conversation
              </p>
              <h3 className="text-xl font-semibold text-ink mb-2 tracking-tight">
                What would you like to build?
              </h3>
              <p className="text-sm text-gray-400 max-w-xs mx-auto leading-relaxed">
                I can help with coding, analysis, document Q&A, and more.
                Your conversation context is preserved across sessions.
              </p>
            </div>
          )}

          {messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              id={msg.id}
              role={msg.role}
              content={msg.content}
            />
          ))}

          {/* Streaming message — real-time token display */}
          {loading && streaming && (
            <div className="flex gap-3 animate-message-in">
              <div className="w-7 h-7 rounded-md border border-border bg-white flex items-center justify-center mt-0.5">
                <span className="text-[10px] font-mono text-ink/50 font-semibold">AI</span>
              </div>
              <div className="max-w-[72%]">
                <div className="inline-block px-4 py-2.5 text-[14px] leading-relaxed bg-white border border-border text-ink/85 rounded-2xl rounded-tl-sm shadow-sm md-content max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {streaming}
                  </ReactMarkdown>
                  <span className="inline-block w-[2px] h-[1em] bg-accent ml-0.5 align-text-bottom animate-pulse" />
                </div>
              </div>
            </div>
          )}

          {/* Loading state before first token */}
          {loading && !streaming && (
            <div className="flex gap-3 animate-message-in">
              <div className="w-7 h-7 rounded-md border border-border bg-white flex items-center justify-center mt-0.5">
                <span className="text-[10px] font-mono text-ink/50 font-semibold">AI</span>
              </div>
              <div className="px-4 py-2.5 rounded-2xl rounded-tl-sm bg-white border border-border shadow-sm inline-block">
                <div className="flex gap-1.5">
                  <span className="w-2 h-2 bg-ink/15 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="w-2 h-2 bg-ink/15 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="w-2 h-2 bg-ink/15 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                </div>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <ChatInput onSend={send} loading={loading} />
    </div>
  );
}
