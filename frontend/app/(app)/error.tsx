"use client";

import { ErrorState } from "@/components/states/states";
import { ApiError } from "@/lib/api";

export default function AppError({ error, retry }: { error: unknown; retry: () => void }) {
  const message =
    error instanceof ApiError
      ? error.message
      : "The page failed to load. Check that the backend API is running, then retry.";
  return <ErrorState title="This page couldn't load" message={message} onRetry={() => retry()} />;
}
