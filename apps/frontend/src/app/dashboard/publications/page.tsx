import type { Metadata } from "next";
import { PublicationsView } from "./PublicationsView";

export const metadata: Metadata = { title: "Publications — AI Media OS" };

export default function PublicationsPage() {
  return <PublicationsView />;
}
