import ConversationSidebar from "@/components/ConversationSidebar";
import ChatPanel from "@/components/ChatPanel";

export default function Chat() {
  return (
    <div className="h-screen w-screen flex overflow-hidden">
      <ConversationSidebar />
      <ChatPanel />
    </div>
  );
}
