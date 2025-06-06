import React from "react";

export function LoadingSkeleton() {
  return (
    <div className="w-64 bg-card border-r border-border p-4">
      <div className="h-6 bg-muted rounded mb-3 animate-pulse" />
      <div className="h-10 bg-muted rounded mb-4 animate-pulse" />

      {[1, 2, 3].map((i) => (
        <div key={i} className="mb-4">
          <div className="h-8 bg-muted rounded mb-2 animate-pulse" />
          <div className="space-y-2 pl-4">
            <div className="h-16 bg-muted rounded animate-pulse" />
            <div className="h-16 bg-muted rounded animate-pulse" />
          </div>
        </div>
      ))}
    </div>
  );
}
