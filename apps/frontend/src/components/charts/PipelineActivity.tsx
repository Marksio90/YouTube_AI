"use client";

export function PipelineActivity() {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
      <h2 className="text-sm font-semibold text-gray-300 mb-4">Pipeline Activity</h2>
      <div className="flex items-center justify-center h-32 text-gray-600 text-sm">
        No pipeline runs — trigger a pipeline to see activity.
      </div>
    </div>
  );
}
