"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Tv2,
  Lightbulb,
  FileText,
  Youtube,
  BarChart3,
  Banknote,
  GitBranch,
  Settings,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils/cn";

const NAV_ITEMS = [
  { href: "/dashboard",              label: "Overview",      icon: LayoutDashboard },
  { href: "/dashboard/channels",     label: "Channels",      icon: Tv2 },
  { href: "/dashboard/topics",       label: "Topics",        icon: Lightbulb },
  { href: "/dashboard/scripts",      label: "Scripts",       icon: FileText },
  { href: "/dashboard/publications", label: "Publications",  icon: Youtube },
  { href: "/dashboard/analytics",    label: "Analytics",     icon: BarChart3 },
  { href: "/dashboard/monetization", label: "Monetization",  icon: Banknote },
  { href: "/dashboard/workflows",    label: "Workflows",     icon: GitBranch },
];

function NavItem({
  href,
  label,
  icon: Icon,
  exact = false,
}: {
  href: string;
  label: string;
  icon: React.ElementType;
  exact?: boolean;
}) {
  const pathname = usePathname();
  const active = exact ? pathname === href : pathname === href || pathname.startsWith(href + "/");

  return (
    <Link
      href={href}
      className={cn(
        "group flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors",
        active
          ? "bg-brand-950 text-brand-300"
          : "text-gray-500 hover:text-gray-200 hover:bg-gray-800/60"
      )}
    >
      <Icon
        className={cn(
          "h-4 w-4 shrink-0 transition-colors",
          active ? "text-brand-400" : "text-gray-600 group-hover:text-gray-400"
        )}
      />
      {label}
    </Link>
  );
}

export function Sidebar() {
  return (
    <aside className="flex flex-col w-[220px] shrink-0 border-r border-gray-800/60 bg-surface">
      {/* Logo */}
      <div className="flex items-center gap-2.5 h-14 px-4 border-b border-gray-800/60">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 shadow-lg shadow-brand-900/40">
          <Zap className="h-3.5 w-3.5 text-white" />
        </div>
        <span className="text-sm font-semibold tracking-tight text-gray-100">AI Media OS</span>
      </div>

      {/* Primary nav */}
      <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-0.5">
        {NAV_ITEMS.map((item) => (
          <NavItem
            key={item.href}
            href={item.href}
            label={item.label}
            icon={item.icon}
            exact={item.href === "/dashboard"}
          />
        ))}
      </nav>

      {/* Bottom */}
      <div className="px-2 py-3 border-t border-gray-800/60 space-y-0.5">
        <NavItem href="/dashboard/settings" label="Settings" icon={Settings} />
        <p className="px-2.5 pt-2 text-[11px] text-gray-700 tabular-nums">
          v{process.env.NEXT_PUBLIC_APP_VERSION ?? "0.1.0"}
        </p>
      </div>
    </aside>
  );
}
