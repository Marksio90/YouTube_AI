import { cn } from "@/lib/utils/cn";

interface CardProps {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  padding?: "none" | "sm" | "md" | "lg";
}

const paddings = {
  none: "",
  sm:   "p-4",
  md:   "p-5",
  lg:   "p-6",
};

export function Card({ children, className, hover, padding = "md" }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-gray-800 bg-gray-900",
        "shadow-inner-border",
        hover && "transition-colors hover:border-gray-700 hover:bg-gray-800/60 cursor-pointer",
        paddings[padding],
        className
      )}
      style={{ boxShadow: "inset 0 1px 0 0 rgba(255,255,255,0.04)" }}
    >
      {children}
    </div>
  );
}

export function CardHeader({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-center justify-between mb-4", className)}>
      {children}
    </div>
  );
}

export function CardTitle({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <h3 className={cn("text-sm font-semibold text-gray-100", className)}>{children}</h3>
  );
}
