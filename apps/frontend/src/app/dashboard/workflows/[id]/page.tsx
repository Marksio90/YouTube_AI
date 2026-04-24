import type { Metadata } from "next";
import { WorkflowDetailView } from "./WorkflowDetailView";

export const metadata: Metadata = { title: "Workflow Run — AI Media OS" };

export default function WorkflowDetailPage({ params }: { params: { id: string } }) {
  return <WorkflowDetailView id={params.id} />;
}
