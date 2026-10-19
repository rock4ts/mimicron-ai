import { CompanionProfile } from "@/components/companion-profile";

export default async function CompanionPage({
  params,
}: {
  params: Promise<{ companionId: string }>;
}) {
  const { companionId } = await params;
  return <CompanionProfile companionId={companionId} />;
}
