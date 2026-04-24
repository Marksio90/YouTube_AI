import { cn } from "@/lib/utils/cn";
import { Spinner } from "./Spinner";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "outline";
type Size    = "xs" | "sm" | "md" | "lg";

const variants: Record<Variant, string> = {
  primary:   "bg-brand-600 text-white hover:bg-brand-500 active:bg-brand-700",
  secondary: "bg-gray-800 text-gray-100 hover:bg-gray-700 active:bg-gray-900",
  ghost:     "text-gray-400 hover:text-gray-100 hover:bg-gray-800 active:bg-gray-900",
  danger:    "bg-danger-muted text-danger-text hover:bg-red-900/40 active:bg-danger-muted",
  outline:   "border border-gray-700 text-gray-300 hover:border-gray-600 hover:text-white hover:bg-gray-800/50",
};

const sizes: Record<Size, string> = {
  xs: "h-7  px-2.5 text-xs gap-1.5",
  sm: "h-8  px-3   text-sm gap-1.5",
  md: "h-9  px-4   text-sm gap-2",
  lg: "h-11 px-5   text-base gap-2",
};

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: React.ReactNode;
  iconRight?: React.ReactNode;
}

export function Button({
  variant = "secondary",
  size = "md",
  loading,
  icon,
  iconRight,
  className,
  children,
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center rounded-lg font-medium transition-colors",
        "focus-ring disabled:pointer-events-none disabled:opacity-40",
        variants[variant],
        sizes[size],
        className
      )}
    >
      {loading ? (
        <Spinner className="h-3.5 w-3.5" />
      ) : icon ? (
        <span className="shrink-0">{icon}</span>
      ) : null}
      {children}
      {iconRight && <span className="shrink-0">{iconRight}</span>}
    </button>
  );
}
