interface Props {
  role: "user" | "assistant";
  content: string;
}

export function MessageBubble({ role, content }: Props) {
  const isUser = role === "user";

  return (
    <div
      className={`flex gap-3 animate-message-in ${isUser ? "flex-row-reverse" : ""}`}
      style={{ animationDelay: "0ms" }}
    >
      {/* Avatar */}
      <div
        className={`w-7 h-7 rounded-md flex items-center justify-center shrink-0 mt-0.5 ${
          isUser
            ? "bg-ink"
            : "border border-border bg-white"
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

      {/* Bubble */}
      <div className={`max-w-[72%] ${isUser ? "text-right" : ""}`}>
        <div
          className={`inline-block px-4 py-2.5 text-[14px] leading-relaxed ${
            isUser
              ? "bg-ink text-white rounded-2xl rounded-tr-sm"
              : "bg-white border border-border text-ink/85 rounded-2xl rounded-tl-sm shadow-sm"
          }`}
        >
          <p className="whitespace-pre-wrap">{content}</p>
        </div>
      </div>
    </div>
  );
}
