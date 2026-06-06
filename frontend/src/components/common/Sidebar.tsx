import { NavLink } from "react-router-dom";
import { MessageSquare, Database, Workflow, Hexagon } from "lucide-react";

interface Props {
  collapsed: boolean;
  width: number;
  onToggle: () => void;
}

const navItems = [
  { to: "/", icon: Hexagon, label: "Dashboard" },
  { to: "/chat", icon: MessageSquare, label: "Chat" },
  { to: "/knowledge", icon: Database, label: "Knowledge Base" },
  { to: "#", icon: Workflow, label: "Workflow", soon: true },
];

export function Sidebar({ collapsed, width, onToggle }: Props) {
  return (
    <aside
      className="h-screen bg-slate border-r border-white/5 flex flex-col select-none
                 transition-[width] duration-200 ease-out shrink-0"
      style={{ width }}
    >
      {/* Logo */}
      <button
        onClick={onToggle}
        className={`flex items-center gap-2.5 px-3 py-4 hover:bg-white/5 transition-colors
                    ${collapsed ? "justify-center" : "px-5"}`}
      >
        <div className="w-7 h-7 rounded-md bg-accent flex items-center justify-center shrink-0">
          <Hexagon size={15} className="text-black" strokeWidth={2.5} />
        </div>
        {!collapsed && (
          <span className="font-semibold text-sm tracking-tight text-white">
            Agent<span className="text-accent">Flow</span>
          </span>
        )}
      </button>

      {/* Navigation */}
      <nav className="flex-1 px-2 space-y-0.5">
        {navItems.map(({ to, icon: Icon, label, soon }) => (
          <NavLink
            key={to}
            to={to}
            title={collapsed ? label : undefined}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13px] font-medium
               transition-all duration-150 ${
                 to === "#"
                   ? "opacity-30 cursor-not-allowed"
                   : isActive
                     ? "bg-white/10 text-white"
                     : "text-gray-400 hover:text-white hover:bg-white/5"
               } ${collapsed ? "justify-center px-0" : ""}`
            }
          >
            <Icon size={collapsed ? 18 : 16} strokeWidth={1.8} />
            {!collapsed && (
              <>
                <span className="flex-1">{label}</span>
                {soon && (
                  <span className="text-[9px] font-mono text-accent/70 bg-accent/10 px-1.5 py-0.5 rounded">
                    SOON
                  </span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className={`px-3 py-4 border-t border-white/5 ${collapsed ? "text-center" : ""}`}>
        <button
          onClick={onToggle}
          className={`text-[10px] text-gray-600 font-mono hover:text-gray-400 transition-colors ${
            collapsed ? "text-[16px]" : ""
          }`}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? "→" : "←  collapse"}
        </button>
      </div>
    </aside>
  );
}
