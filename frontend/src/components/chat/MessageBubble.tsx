import { useState } from "react";
import { Copy, Check, Pencil } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useChatStore } from "../../stores/chat";

interface Props {
  id: string;
  role: "user" | "assistant";
  content: string;
}

export function MessageBubble({ id, role, content }: Props) {
  const isUser = role === "user";
  const editMessage = useChatStore((s) => s.editMessage);
  const [copied, setCopied] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(content);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSaveEdit = () => {
    editMessage(id, editText.trim() || content);
    setEditing(false);
  };

  const handleCancelEdit = () => {
    setEditText(content);
    setEditing(false);
  };

  return (
    <div className={`group flex gap-3 animate-message-in ${isUser ? "flex-row-reverse" : ""}`}>
      {/* Avatar */}
      <div
        className={`w-7 h-7 rounded-md flex items-center justify-center shrink-0 mt-0.5 ${
          isUser ? "bg-ink" : "border border-border bg-white"
        }`}
      >
        <span
          className={`text-[10px] font-mono font-semibold ${
            isUser ? "text-white" : "text-ink/50"
          }`}
        >
          {isUser ? "YOU" : "AI"}
        </span>
      </div>

      {/* Content */}
      <div className={`max-w-[75%] ${isUser ? "text-right" : ""}`}>
        {editing ? (
          <div className="flex flex-col gap-2">
            <textarea
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              className="w-96 px-4 py-2.5 text-[14px] leading-relaxed rounded-2xl border-2
                         border-ink/20 bg-white focus:outline-none focus:border-ink/50
                         resize-none font-sans"
              rows={5}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSaveEdit(); }
                if (e.key === "Escape") handleCancelEdit();
              }}
            />
            <div className="flex gap-2 justify-end">
              <button onClick={handleCancelEdit}
                className="px-2.5 py-1 text-[11px] text-gray-500 hover:text-gray-700 font-mono">esc</button>
              <button onClick={handleSaveEdit}
                className="px-3 py-1 text-[11px] bg-ink text-white rounded-md hover:bg-slate-hover font-mono transition-colors">save ↵</button>
            </div>
          </div>
        ) : (
          <div
            className={`inline-block px-4 py-2.5 text-[14px] leading-relaxed ${
              isUser
                ? "bg-ink text-white rounded-2xl rounded-tr-sm"
                : "bg-white border border-border text-ink/85 rounded-2xl rounded-tl-sm shadow-sm"
            }`}
          >
            {isUser ? (
              <p className="whitespace-pre-wrap">{content}</p>
            ) : (
              <div className="
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
              ">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {content}
                </ReactMarkdown>
              </div>
            )}
          </div>
        )}

        {/* Action buttons — show on hover */}
        {!editing && (
          <div
            className={`flex gap-0.5 mt-1 opacity-0 group-hover:opacity-100 transition-opacity ${
              isUser ? "justify-end" : ""
            }`}
          >
            <button onClick={handleCopy}
              className="p-1 rounded hover:bg-black/5 transition-colors" title="Copy">
              {copied ? <Check size={12} className="text-accent" /> : <Copy size={12} className="text-gray-400" />}
            </button>
            <button onClick={() => { setEditText(content); setEditing(true); }}
              className="p-1 rounded hover:bg-black/5 transition-colors" title="Edit">
              <Pencil size={12} className="text-gray-400" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
