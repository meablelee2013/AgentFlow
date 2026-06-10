import { useState } from "react";
import { Copy, Check, Pencil } from "lucide-react";
import { useChatStore } from "../../stores/chat";
import { renderMarkdown } from "../../utils/renderMarkdown";

interface Props {
  id: string;
  role: "user" | "assistant";
  content: string;
}

export function MessageBubble({ id, role, content }: Props) {
  const isUser = role === "user";
  const [copied, setCopied] = useState(false);
  const { /* editMessage */ } = useChatStore();

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleEdit = () => {
    // Dispatch custom event for ChatInput to pick up edit mode
    window.dispatchEvent(
      new CustomEvent("edit-message", { detail: { id, content } })
    );
  };

  return (
    <div
      className={`flex gap-3 animate-message-in ${
        isUser ? "justify-end" : "justify-start"
      }`}
    >
      {!isUser && (
        <div className="w-7 h-7 rounded-md border border-border bg-white flex items-center justify-center mt-0.5 shrink-0">
          <span className="text-[10px] font-mono text-ink/50 font-semibold">
            AI
          </span>
        </div>
      )}
      <div className={`group max-w-[72%] ${isUser ? "order-first" : ""}`}>
        <div
          className={`relative ${
            isUser
              ? "bg-ink text-white rounded-2xl rounded-tr-sm"
              : "bg-white border border-border text-ink/85 rounded-2xl rounded-tl-sm shadow-sm"
          }`}
        >
          {isUser ? (
            <p className="px-4 py-2.5 text-[14px] leading-relaxed whitespace-pre-wrap">
              {content}
            </p>
          ) : (
            <div
              className="inline-block px-4 py-2.5 text-[14px] leading-relaxed max-w-none
                [&_h1]:text-lg [&_h1]:font-bold [&_h1]:mt-4 [&_h1]:mb-2
                [&_h2]:text-base [&_h2]:font-bold [&_h2]:mt-3 [&_h2]:mb-1.5
                [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:mt-2 [&_h3]:mb-1
                [&_p]:my-1.5 [&_p]:leading-relaxed
                [&_ul]:pl-5 [&_ul]:my-1.5 [&_ol]:pl-5 [&_ol]:my-1.5
                [&_li]:my-0.5 [&_li]:leading-relaxed
                [&_code]:bg-[#f0ede8] [&_code]:text-[#d6336c] [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-[0.88em] [&_code]:font-mono
                [&_pre]:bg-[#1a1a1a] [&_pre]:text-[#e8e5e0] [&_pre]:p-3.5 [&_pre]:rounded-xl [&_pre]:overflow-x-auto [&_pre]:my-2 [&_pre]:text-[0.85em] [&_pre]:leading-relaxed
                [&_pre_code]:bg-transparent [&_pre_code]:text-inherit [&_pre_code]:p-0 [&_pre_code]:text-inherit
                [&_blockquote]:border-l-[3px] [&_blockquote]:border-[#d4d0c8] [&_blockquote]:pl-3.5 [&_blockquote]:my-2 [&_blockquote]:text-gray-500 [&_blockquote]:italic
                [&_a]:text-blue-600 [&_a]:underline
                [&_strong]:font-semibold
                [&_table]:w-full [&_table]:border-collapse [&_table]:my-2 [&_table]:text-sm
                [&_th]:border [&_th]:border-[#d4d0c8] [&_th]:p-2 [&_th]:bg-[#f5f2ed] [&_th]:font-semibold
                [&_td]:border [&_td]:border-[#d4d0c8] [&_td]:p-2
                [&_hr]:border-none [&_hr]:border-t [&_hr]:border-[#d4d0c8] [&_hr]:my-3
              "
              dangerouslySetInnerHTML={{
                __html: renderMarkdown(content),
              }}
            />
          )}
        </div>

        {/* Action buttons — show on hover */}
        {!isUser && (
          <div className="flex gap-1 mt-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
            <button
              onClick={handleCopy}
              className="p-1 rounded hover:bg-white/80 text-gray-400 hover:text-gray-600 transition-colors"
              title={copied ? "Copied!" : "Copy"}
            >
              {copied ? (
                <Check className="w-3 h-3 text-green-500" />
              ) : (
                <Copy className="w-3 h-3" />
              )}
            </button>
            <button
              onClick={handleEdit}
              className="p-1 rounded hover:bg-white/80 text-gray-400 hover:text-gray-600 transition-colors"
              title="Edit"
            >
              <Pencil className="w-3 h-3" />
            </button>
          </div>
        )}
      </div>
      {isUser && (
        <div className="w-7 h-7 rounded-md bg-ink flex items-center justify-center mt-0.5 shrink-0">
          <span className="text-[10px] font-mono text-white/60 font-semibold">
            U
          </span>
        </div>
      )}
    </div>
  );
}
