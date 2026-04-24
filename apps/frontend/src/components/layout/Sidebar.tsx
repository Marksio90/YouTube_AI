"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Overview", icon: "⬡" },
  { href: "/dashboard/channels", label: "Channels", icon: "📺" },
  { href: "/dashboard/videos", label: "Videos", icon: "🎬" },
  { href: "/dashboard/scripts", label: "Scripts", icon: "📝" },
  { href: "/dashboard/pipelines", label: "Pipelines", icon: "⚙️" },
  { href: "/dashboard/analytics", label: "Analytics", icon: "📊" },
  { href: "/dashboard/settings", label: "Settings", icon: "⚙" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 shrink-0 border-r border-gray-800 bg-gray-900 flex flex-col">
      <div className="h-14 flex items-center px-4 border-b border-gray-800">
        <span className="font-bold text-sm tracking-widest text-brand-500 uppercase">AI Media OS</span>
      </div>
      <nav className="flex-1 overflow-y-auto py-4 px-2 space-y-1">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={clsx(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              pathname === item.href
                ? "bg-gray-800 text-white"
                : "text-gray-400 hover:bg-gray-800 hover:text-white"
            )}
          >
            <span className="text-base leading-none">{item.icon}</span>
            {item.label}
          </Link>
        ))}
      </nav>
      <div className="p-4 border-t border-gray-800">
        <p className="text-xs text-gray-600">v{process.env.NEXT_PUBLIC_APP_VERSION ?? "0.1.0"}</p>
      </div>
    </aside>
  );
}
