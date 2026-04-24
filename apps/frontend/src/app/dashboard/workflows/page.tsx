import type { Metadata } from "next";
import { WorkflowsView } from "./WorkflowsView";

export const metadata: Metadata = { title: "Workflows — AI Media OS" };

export default function WorkflowsPage() {
  return <WorkflowsView />;
}
