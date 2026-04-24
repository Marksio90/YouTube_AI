"use client";
import { createContext, useContext } from "react";
import { cn } from "@/lib/utils/cn";

/* ── Context ────────────────────────────────────────────────────────────────── */
interface TabsCtx { value: string; onChange: (v: string) => void }
const Ctx = createContext<TabsCtx>({ value: "", onChange: () => {} });

/* ── Root ───────────────────────────────────────────────────────────────────── */
interface TabsProps {
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
  className?: string;
}

export function Tabs({ value, onChange, children, className }: TabsProps) {
  return (
    <Ctx.Provider value={{ value, onChange }}>
      <div className={cn("flex flex-col", className)}>{children}</div>
    </Ctx.Provider>
  );
}

/* ── List ───────────────────────────────────────────────────────────────────── */
interface TabsListProps {
  children: React.ReactNode;
  className?: string;
  variant?: "underline" | "pill";
}

export function TabsList({ children, className, variant = "underline" }: TabsListProps) {
  return (
    <div
      role="tablist"
      className={cn(
        "flex items-center gap-1",
        variant === "underline"
          ? "border-b border-[var(--border)]"
          : "bg-surface-active p-1 rounded-lg gap-1",
        className
      )}
    >
      {children}
    </div>
  );
}

/* ── Trigger ────────────────────────────────────────────────────────────────── */
interface TabsTriggerProps {
  value: string;
  children: React.ReactNode;
  count?: number;
  disabled?: boolean;
  variant?: "underline" | "pill";
}

export function TabsTrigger({
  value,
  children,
  count,
  disabled,
  variant = "underline",
}: TabsTriggerProps) {
  const { value: active, onChange } = useContext(Ctx);
  const isActive = active === value;

  if (variant === "pill") {
    return (
      <button
        role="tab"
        aria-selected={isActive}
        disabled={disabled}
        onClick={() => onChange(value)}
        className={cn(
          "focus-ring inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
          isActive
            ? "bg-[#18181b] text-gray-100 shadow-card"
            : "text-gray-500 hover:text-gray-300",
          disabled && "pointer-events-none opacity-40"
        )}
      >
        {children}
        {count !== undefined && (
          <span className={cn(
            "rounded-full px-1.5 py-0.5 text-2xs font-medium tabular-nums",
            isActive ? "bg-gray-700 text-gray-300" : "bg-gray-800 text-gray-500"
          )}>
            {count}
          </span>
        )}
      </button>
    );
  }

  return (
    <button
      role="tab"
      aria-selected={isActive}
      disabled={disabled}
      onClick={() => onChange(value)}
      className={cn(
        "focus-ring relative inline-flex items-center gap-1.5 px-1 pb-3 pt-0.5 text-sm font-medium transition-colors",
        isActive ? "text-gray-100" : "text-gray-500 hover:text-gray-300",
        "after:absolute after:inset-x-0 after:bottom-0 after:h-[2px] after:rounded-full after:transition-colors",
        isActive ? "after:bg-brand-500" : "after:bg-transparent",
        disabled && "pointer-events-none opacity-40"
      )}
    >
      {children}
      {count !== undefined && (
        <span className={cn(
          "rounded-full px-1.5 py-0.5 text-2xs font-medium tabular-nums",
          isActive ? "bg-brand-950 text-brand-300" : "bg-gray-800 text-gray-500"
        )}>
          {count}
        </span>
      )}
    </button>
  );
}

/* ── Content ────────────────────────────────────────────────────────────────── */
interface TabsContentProps {
  value: string;
  children: React.ReactNode;
  className?: string;
}

export function TabsContent({ value, children, className }: TabsContentProps) {
  const { value: active } = useContext(Ctx);
  if (active !== value) return null;
  return (
    <div role="tabpanel" className={cn("animate-fade-in", className)}>
      {children}
    </div>
  );
}
