import { NavLink } from "react-router-dom";
import { MessageSquare, Database, Workflow, Hexagon } from "lucide-react";

const navItems = [
  { to: "/", icon: Hexagon, label: "Dashboard" },
  { to: "/chat", icon: MessageSquare, label: "Chat" },
  { to: "/knowledge", icon: Database, label: "Knowledge Base" },
  { to: "#", icon: Workflow, label: "Workflow", soon: true },
];

export function Sidebar() {
  return (
    <aside className="w-56 bg-slate flex flex-col border-r border-white/5 select-none">
      {/* Logo */}
      <div className="px-5 py-5">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-md bg-accent flex items-center justify-center">
            <Hexagon size={15} className="text-black" strokeWidth={2.5} />
          </div>
          <span className="font-semibold text-sm tracking-tight text-white">
            Agent<span className="text-accent">Flow</span>
          </span>
        </div>
        <p className="text-[10px] text-gray-500 mt-1.5 ml-0.5 font-mono tracking-wide">
          AI Agent Platform
        </p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 space-y-0.5">
        {navItems.map(({ to, icon: Icon, label, soon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13px] font-medium transition-all duration-150 ${
                to === "#"
                  ? "opacity-30 cursor-not-allowed"
                  : isActive
                    ? "bg-white/10 text-white"
                    : "text-gray-400 hover:text-white hover:bg-white/5"
              }`
            }
          >
            <Icon size={16} strokeWidth={1.8} />
            <span className="flex-1">{label}</span>
            {soon && (
              <span className="text-[9px] font-mono text-accent/70 bg-accent/10 px-1.5 py-0.5 rounded">
                SOON
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-white/5">
        <p className="text-[10px] text-gray-600 font-mono">
          v0.1.0 · Phase 1
        </p>
      </div>
    </aside>
  );
}
