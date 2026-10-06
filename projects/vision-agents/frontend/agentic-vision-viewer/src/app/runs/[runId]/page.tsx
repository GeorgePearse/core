import { RunDetailPage } from "@/components/run-detail-page";

export default async function RunPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  return <RunDetailPage runId={runId} />;
}
