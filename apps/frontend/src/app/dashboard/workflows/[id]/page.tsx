import type { Metadata } from "next";
import { WorkflowDetailView } from "./WorkflowDetailView";

export const metadata: Metadata = { title: "Workflow Run — AI Media OS" };

export default async function WorkflowDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <WorkflowDetailView id={id} />;
}
