import type { Metadata } from "next";
import { TopicsView } from "./TopicsView";

export const metadata: Metadata = { title: "Topics — AI Media OS" };

export default function TopicsPage() {
  return <TopicsView />;
}
