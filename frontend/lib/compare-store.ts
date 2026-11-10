"use client";

import { useSyncExternalStore } from "react";

// Compare list kept in the browser (no accounts in V0). Max four repositories.
const KEY = "devatlas.compare";
export const COMPARE_MAX = 4;

export class CompareFullError extends Error {
  constructor() {
    super("You can compare up to four repositories. Remove one first.");
  }
}

let memory: string[] = [];
const listeners = new Set<() => void>();

function read(): string[] {
  try {
    const raw = localStorage.getItem(KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    memory = Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
  } catch {
    // Storage unavailable (private mode, blocked): fall back to the in-memory list.
  }
  return memory;
}

function write(next: string[]) {
  memory = next;
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // ignore: the in-memory list still works for this tab
  }
  listeners.forEach((listener) => listener());
}

export function getCompareList(): string[] {
  return read();
}

export function toggleCompare(fullName: string): string[] {
  const current = read();
  if (current.includes(fullName)) {
    const next = current.filter((n) => n !== fullName);
    write(next);
    return next;
  }
  if (current.length >= COMPARE_MAX) throw new CompareFullError();
  const next = [...current, fullName];
  write(next);
  return next;
}

export function clearCompare() {
  write([]);
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  const onStorage = (e: StorageEvent) => e.key === KEY && listener();
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

const EMPTY: string[] = [];
let snapshot: string[] = EMPTY;
let snapshotKey = "[]";

function getSnapshot(): string[] {
  const current = read();
  const key = JSON.stringify(current);
  if (key !== snapshotKey) {
    snapshotKey = key;
    snapshot = current;
  }
  return snapshot;
}

/** Current compare list, kept in sync across components and tabs. */
export function useCompareList(): string[] {
  return useSyncExternalStore(subscribe, getSnapshot, () => EMPTY);
}
