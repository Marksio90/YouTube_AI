import type { Metadata } from "next";
import { ChannelsView } from "./ChannelsView";

export const metadata: Metadata = { title: "Channels — AI Media OS" };

export default function ChannelsPage() {
  return <ChannelsView />;
}
