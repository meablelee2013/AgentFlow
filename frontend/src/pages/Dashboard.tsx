import { MessageSquare, Database, Workflow, ArrowRight } from "lucide-react";
import { useNavigate } from "react-router-dom";

const cards = [
  {
    title: "Chat",
    desc: "AI-powered conversation with context memory and streaming.",
    icon: MessageSquare,
    href: "/chat",
    gradient: "from-blue-500 to-cyan-500",
    bg: "from-blue-50 to-cyan-50",
  },
  {
    title: "Knowledge Base",
    desc: "Upload documents, ingest URLs. RAG-powered retrieval with 17 format support.",
    icon: Database,
    href: "/knowledge",
    gradient: "from-violet-500 to-purple-500",
    bg: "from-violet-50 to-purple-50",
  },
  {
    title: "Workflow",
    desc: "Visual agent workflow builder with drag-and-drop orchestration. Coming in Phase 2.",
    icon: Workflow,
    href: "#",
    gradient: "from-amber-500 to-orange-500",
    bg: "from-amber-50 to-orange-50",
  },
];

export function Dashboard() {
  const navigate = useNavigate();

  return (
    <div className="p-8 max-w-5xl mx-auto">
      {/* Hero */}
      <div className="mb-10">
        <h1 className="text-3xl font-bold text-gray-900">
          Agent<span className="text-blue-500">Flow</span>
        </h1>
        <p className="mt-2 text-gray-500 text-sm max-w-lg">
          Open-source AI agent development platform. Build, orchestrate, and deploy
          intelligent workflows with LangGraph + RAG.
        </p>
      </div>

      {/* Feature Cards */}
      <div className="grid grid-cols-3 gap-4">
        {cards.map(({ title, desc, icon: Icon, href, gradient, bg }) => (
          <button
            key={title}
            onClick={() => href !== "#" && navigate(href)}
            className={`group p-6 rounded-2xl bg-gradient-to-br ${bg} border border-gray-100
                       text-left hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200
                       ${href === "#" ? "opacity-60 cursor-not-allowed" : "cursor-pointer"}`}
            disabled={href === "#"}
          >
            <div
              className={`w-10 h-10 rounded-xl bg-gradient-to-br ${gradient} flex items-center justify-center mb-3 group-hover:scale-110 transition-transform`}
            >
              <Icon size={20} className="text-white" />
            </div>
            <h3 className="font-semibold text-gray-900 mb-1 flex items-center gap-2">
              {title}
              {href === "#" && (
                <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-amber-100 text-amber-600">
                  Phase 2
                </span>
              )}
            </h3>
            <p className="text-sm text-gray-500 leading-relaxed">{desc}</p>
            {href !== "#" && (
              <div className="flex items-center gap-1 mt-3 text-xs font-medium text-blue-500 opacity-0 group-hover:opacity-100 transition-opacity">
                Open <ArrowRight size={12} />
              </div>
            )}
          </button>
        ))}
      </div>

      {/* Stats */}
      <div className="mt-8 grid grid-cols-3 gap-4">
        {[
          { label: "LLM Providers", value: "2", sub: "DeepSeek + Qwen" },
          { label: "File Formats", value: "17", sub: "Auto-parsed via strategy pattern" },
          { label: "Architecture", value: "LangGraph", sub: "StateGraph + Checkpointer" },
        ].map(({ label, value, sub }) => (
          <div key={label} className="p-4 rounded-xl bg-white border border-gray-100">
            <p className="text-xs text-gray-500">{label}</p>
            <p className="text-lg font-bold text-gray-900 mt-0.5">{value}</p>
            <p className="text-xs text-gray-400 mt-0.5">{sub}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
