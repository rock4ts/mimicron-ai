import { ChatView } from "@/components/chat-view";

export default async function ConversationPage({
  params,
}: {
  params: Promise<{ companionId: string; conversationId: string }>;
}) {
  const { companionId, conversationId } = await params;
  return <ChatView companionId={companionId} conversationId={conversationId} />;
}
