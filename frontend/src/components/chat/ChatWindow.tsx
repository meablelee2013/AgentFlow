import { useEffect, useLayoutEffect, useRef } from "react";
import { useChatStore } from "../../stores/chat";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";
import { renderMarkdown } from "../../utils/renderMarkdown";

export function ChatWindow() {
  const { messages, loading, streaming, send } = useChatStore();
  const bottomRef = useRef<HTMLDivElement>(null);
  const streamingRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  // Directly update innerHTML for streaming content to avoid React reconciliation issues
  useLayoutEffect(() => {
    if (streamingRef.current) {
      streamingRef.current.innerHTML = renderMarkdown(streaming);
    }
  }, [streaming]);

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
                <div
                  ref={streamingRef}
                  className="inline-block px-4 py-2.5 text-[14px] leading-relaxed bg-white border border-border text-ink/85 rounded-2xl rounded-tl-sm shadow-sm max-w-none
                  [&_h1]:text-lg [&_h1]:font-bold [&_h1]:mt-4 [&_h1]:mb-2
                  [&_h2]:text-base [&_h2]:font-bold [&_h2]:mt-3 [&_h2]:mb-1.5
                  [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:mt-2 [&_h3]:mb-1
                  [&_p]:my-1.5 [&_p]:leading-relaxed
                  [&_ul]:pl-5 [&_ul]:my-1.5 [&_ol]:pl-5 [&_ol]:my-1.5
                  [&_li]:my-0.5
                  [&_code]:bg-[#f0ede8] [&_code]:text-[#d6336c] [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-[0.88em] [&_code]:font-mono
                  [&_pre]:bg-[#1a1a1a] [&_pre]:text-[#e8e5e0] [&_pre]:p-3.5 [&_pre]:rounded-xl [&_pre]:overflow-x-auto [&_pre]:my-2 [&_pre]:text-[0.85em]
                  [&_pre_code]:bg-transparent [&_pre_code]:text-inherit [&_pre_code]:p-0
                  [&_blockquote]:border-l-[3px] [&_blockquote]:border-[#d4d0c8] [&_blockquote]:pl-3.5 [&_blockquote]:my-2 [&_blockquote]:text-gray-500
                  [&_a]:text-blue-600 [&_a]:underline [&_strong]:font-semibold"
                />
                <span className="inline-block w-[2px] h-[1em] bg-accent ml-0.5 align-text-bottom animate-pulse" />
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
