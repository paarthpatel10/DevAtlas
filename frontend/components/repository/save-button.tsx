"use client";

import { Bookmark, BookmarkCheck } from "lucide-react";
import { useState } from "react";

import { saveRepository, unsaveRepository } from "@/lib/api";

export function SaveButton({
  owner,
  name,
  initialSaved,
  onChange,
}: {
  owner: string;
  name: string;
  initialSaved: boolean;
  onChange?: (saved: boolean) => void;
}) {
  const [saved, setSaved] = useState(initialSaved);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);

  async function toggle() {
    const next = !saved;
    setSaved(next); // optimistic
    setFailed(false);
    setPending(true);
    try {
      await (next ? saveRepository(owner, name) : unsaveRepository(owner, name));
      onChange?.(next);
    } catch {
      setSaved(!next); // roll back
      setFailed(true);
    } finally {
      setPending(false);
    }
  }

  const Icon = saved ? BookmarkCheck : Bookmark;
  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        onClick={toggle}
        disabled={pending}
        aria-pressed={saved}
        className={`inline-flex items-center gap-1.5 rounded border px-2.5 py-1 text-sm font-medium transition-colors disabled:opacity-60 ${
          saved
            ? "border-accent bg-accent-soft text-accent"
            : "border-rule bg-surface text-ink hover:border-ink"
        }`}
      >
        <Icon aria-hidden size={15} />
        {saved ? "Saved" : "Save"}
      </button>
      {failed && (
        <span role="status" className="text-xs text-danger">
          Couldn&apos;t save — try again
        </span>
      )}
    </span>
  );
}
