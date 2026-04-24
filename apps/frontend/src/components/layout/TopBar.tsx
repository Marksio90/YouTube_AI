"use client";

export function TopBar() {
  return (
    <header className="h-14 shrink-0 border-b border-gray-800 bg-gray-900 flex items-center justify-between px-6">
      <div className="flex-1" />
      <div className="flex items-center gap-4">
        <span className="text-xs text-gray-500">Production</span>
        <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center text-sm font-bold">
          U
        </div>
      </div>
    </header>
  );
}
