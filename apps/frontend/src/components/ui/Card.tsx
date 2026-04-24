import { cn } from "@/lib/utils/cn";

interface CardProps {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  padding?: "none" | "sm" | "md" | "lg";
  as?: "div" | "article" | "section";
}

const paddings = { none: "", sm: "p-4", md: "p-5", lg: "p-6" };

export function Card({
  children,
  className,
  hover,
  padding = "md",
  as: Tag = "div",
}: CardProps) {
  return (
    <Tag
      className={cn(
        "card",
        paddings[padding],
        hover && "transition-colors cursor-pointer hover:border-gray-700/60 hover:bg-[#1c1c1f]",
        className
      )}
    >
      {children}
    </Tag>
  );
}

export function CardHeader({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center justify-between mb-4", className)}>
      {children}
    </div>
  );
}

export function CardTitle({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <h3 className={cn("t-section", className)}>{children}</h3>;
}
