import { useState } from "react";
import Header from "./components/Header";
import ChatWindow from "./components/ChatWindow";
import InputBar from "./components/InputBar";
import SavedFiltersSidebar from "./components/SavedFiltersSidebar";
import { useChat } from "./hooks/useChat";
import type { SavedFilter } from "./types";

export default function App() {
  const {
    messages,
    isLoading,
    sendMessage,
    selectClarification,
    cancelRequest,
    clearMessages,
  } = useChat();

  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleLoadFilter = (filter: SavedFilter) => {
    setSidebarOpen(false);
    // Send a message that describes the loaded filter
    const desc = filter.nl_description
      ? `Loaded saved filter "${filter.name}": ${filter.nl_description}`
      : `Loaded saved filter "${filter.name}"`;
    sendMessage(desc);
  };

  return (
    <div className="h-screen flex flex-col" style={{ background: "transparent" }}>
      <Header
        onClear={clearMessages}
        messageCount={messages.length}
        onToggleSavedFilters={() => setSidebarOpen((o) => !o)}
      />
      <ChatWindow
        messages={messages}
        isLoading={isLoading}
        onClarificationSelect={selectClarification}
      />
      <InputBar
        onSend={sendMessage}
        onCancel={cancelRequest}
        isLoading={isLoading}
      />
      <SavedFiltersSidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onLoadFilter={handleLoadFilter}
      />
    </div>
  );
}
