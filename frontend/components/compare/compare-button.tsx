"use client";

import { GitCompareArrows } from "lucide-react";
import { useState } from "react";

import { CompareFullError, toggleCompare, useCompareList } from "@/lib/compare-store";

export function CompareButton({ fullName }: { fullName: string }) {
  const list = useCompareList();
  const [message, setMessage] = useState<string | null>(null);
  const selected = list.includes(fullName);

  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        aria-pressed={selected}
        onClick={() => {
          setMessage(null);
          try {
            toggleCompare(fullName);
          } catch (error) {
            if (error instanceof CompareFullError) setMessage(error.message);
          }
        }}
        className={`inline-flex items-center gap-1.5 rounded border px-2.5 py-1 text-sm font-medium ${
          selected ? "border-accent bg-accent-soft text-accent" : "border-rule bg-surface hover:border-ink"
        }`}
      >
        <GitCompareArrows aria-hidden size={15} />
        {selected ? "In compare" : "Compare"}
      </button>
      {message && (
        <span role="status" className="text-xs text-danger">
          {message}
        </span>
      )}
    </span>
  );
}
