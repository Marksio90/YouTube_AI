"use client";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "./Button";

interface ErrorStateProps {
  title?: string;
  description?: string;
  onRetry?: () => void;
  compact?: boolean;
}

export function ErrorState({
  title = "Something went wrong",
  description = "There was a problem loading this data. Please try again.",
  onRetry,
  compact,
}: ErrorStateProps) {
  if (compact) {
    return (
      <div className="flex items-center gap-2 text-sm text-danger-text py-4">
        <AlertTriangle className="h-4 w-4 shrink-0" />
        <span>{title}</span>
        {onRetry && (
          <button onClick={onRetry} className="ml-2 underline text-gray-400 hover:text-white">
            Retry
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center text-center py-16 px-6">
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-xl border border-danger-muted bg-danger-muted/30 text-danger-text">
        <AlertTriangle className="h-6 w-6" />
      </div>
      <h3 className="text-sm font-semibold text-gray-200 mb-1">{title}</h3>
      <p className="text-sm text-gray-500 max-w-xs">{description}</p>
      {onRetry && (
        <div className="mt-4">
          <Button size="sm" variant="outline" icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={onRetry}>
            Try again
          </Button>
        </div>
      )}
    </div>
  );
}
