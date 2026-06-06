import { useState, useRef, useEffect, type KeyboardEvent } from "react";
import { ArrowUp } from "lucide-react";

interface Props {
  onSend: (message: string) => void;
  loading: boolean;
}

export function ChatInput({ onSend, loading }: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 160) + "px";
    }
  }, [value]);

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || loading) return;
    onSend(trimmed);
    setValue("");
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="border-t border-border bg-warm/80 backdrop-blur-sm px-4 py-3">
      <div className="max-w-3xl mx-auto flex gap-3 items-end">
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            rows={1}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            className="w-full resize-none rounded-2xl border border-border bg-white px-5 py-3 text-[14px]
                       placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-ink/10 focus:border-ink/30
                       transition-shadow font-sans"
            disabled={loading}
          />
          <span className="absolute right-3 bottom-3 text-[10px] text-gray-300 font-mono pointer-events-none">
            ↵
          </span>
        </div>
        <button
          onClick={handleSend}
          disabled={!value.trim() || loading}
          className="shrink-0 w-11 h-11 rounded-xl bg-ink text-white flex items-center justify-center
                     hover:bg-slate-hover disabled:opacity-20 disabled:cursor-not-allowed
                     transition-all duration-150 active:scale-95"
        >
          <ArrowUp size={18} strokeWidth={2.5} />
        </button>
      </div>
      <p className="text-center text-[10px] text-gray-400 mt-2 font-mono">
        Shift + Enter for new line
      </p>
    </div>
  );
}
