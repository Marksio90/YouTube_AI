"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled error:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return this.props.fallback ?? <GlobalErrorFallback error={this.state.error} />;
    }
    return this.props.children;
  }
}

function GlobalErrorFallback({ error }: { error: Error }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 text-gray-50 p-8">
      <div className="max-w-md text-center space-y-4">
        <h1 className="text-2xl font-semibold">Something went wrong</h1>
        <p className="text-gray-400 text-sm">{error.message}</p>
        <button
          className="px-4 py-2 bg-indigo-600 rounded text-sm hover:bg-indigo-500"
          onClick={() => window.location.reload()}
        >
          Reload page
        </button>
      </div>
    </div>
  );
}
