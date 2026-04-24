import type { Metadata } from "next";
import { ScriptsView } from "./ScriptsView";

export const metadata: Metadata = { title: "Scripts — AI Media OS" };

export default function ScriptsPage() {
  return <ScriptsView />;
}
