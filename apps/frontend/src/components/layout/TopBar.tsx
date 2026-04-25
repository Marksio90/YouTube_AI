"use client";
import { usePathname } from "next/navigation";
import { Bell, ChevronRight, LogOut } from "lucide-react";
import { useAuth } from "@/components/auth/AuthContext";
import { cn } from "@/lib/utils/cn";

const CRUMBS: Record<string, string> = {
  dashboard:    "Overview",
  channels:     "Channels",
  topics:       "Topics",
  scripts:      "Scripts",
  publications: "Publications",
  analytics:    "Analytics",
  workflows:    "Workflows",
  settings:     "Settings",
};

function Breadcrumbs() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);

  return (
    <ol className="flex items-center gap-1 text-sm">
      {segments.map((seg, i) => {
        const isLast = i === segments.length - 1;
        const label = CRUMBS[seg] ?? seg;
        return (
          <li key={seg} className="flex items-center gap-1">
            {i > 0 && <ChevronRight className="h-3.5 w-3.5 text-gray-600" />}
            <span className={cn(isLast ? "text-gray-200 font-medium" : "text-gray-500")}>
              {label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function TopBar() {
  const { logout } = useAuth();

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-gray-800/60 bg-surface px-5">
      <Breadcrumbs />
      <div className="flex items-center gap-3">
        <button className="relative flex h-8 w-8 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-800 hover:text-gray-300 transition-colors">
          <Bell className="h-4 w-4" />
        </button>
        <button
          onClick={() => {
            void logout();
          }}
          className="flex h-8 items-center gap-1 rounded-lg px-2 text-xs text-gray-400 hover:bg-gray-800 hover:text-gray-100 transition-colors"
        >
          <LogOut className="h-3.5 w-3.5" />
          Logout
        </button>
        <div className="flex items-center gap-2 pl-2 border-l border-gray-800">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-700 text-xs font-bold text-white select-none">
            U
          </div>
          <span className="text-xs text-gray-400 hidden sm:block">Production</span>
        </div>
      </div>
    </header>
  );
}
