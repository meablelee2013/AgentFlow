import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Sidebar } from "./components/common/Sidebar";
import { Dashboard } from "./pages/Dashboard";
import { ChatApp } from "./pages/ChatApp";
import { KnowledgeBase } from "./pages/KnowledgeBase";
import { WorkflowEditor } from "./pages/WorkflowEditor";
import { DecomposeTestChat } from "./pages/DecomposeTestChat";
import { useResizableSidebar } from "./hooks/useResizableSidebar";

export default function App() {
  const { collapsed, width, toggle, startDrag, dragging } = useResizableSidebar();

  return (
    <BrowserRouter>
      <div className="flex h-screen bg-warm overflow-hidden">
        <Sidebar collapsed={collapsed} width={width} onToggle={toggle} />

        {/* Drag handle — only when expanded */}
        {!collapsed && (
          <div
            onMouseDown={startDrag}
            className={`w-1.5 cursor-col-resize shrink-0 transition-colors z-10
                        ${dragging ? "bg-accent/40" : "hover:bg-accent/20 bg-transparent"}`}
          />
        )}

        {/* Content */}
        <main className="flex-1 overflow-auto min-w-0">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/chat" element={<ChatApp />} />
            <Route path="/knowledge" element={<KnowledgeBase />} />
            <Route path="/workflow" element={<WorkflowEditor />} />
            <Route path="/decompose-test" element={<DecomposeTestChat />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
