import Header from "./components/Header";
import ChatWindow from "./components/ChatWindow";
import InputBar from "./components/InputBar";
import { useChat } from "./hooks/useChat";

export default function App() {
  const {
    messages,
    isLoading,
    sendMessage,
    selectClarification,
    cancelRequest,
    clearMessages,
  } = useChat();

  return (
    <div className="h-screen flex flex-col" style={{ background: "transparent" }}>
      <Header onClear={clearMessages} messageCount={messages.length} />
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
    </div>
  );
}
