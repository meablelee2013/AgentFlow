import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Sidebar } from "./components/common/Sidebar";
import { Dashboard } from "./pages/Dashboard";
import { ChatApp } from "./pages/ChatApp";
import { KnowledgeBase } from "./pages/KnowledgeBase";

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen bg-gray-50">
        <Sidebar />
        <main className="flex-1 overflow-auto">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/chat" element={<ChatApp />} />
            <Route path="/knowledge" element={<KnowledgeBase />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
