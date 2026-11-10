"use client";

import { useRouter } from "next/navigation";

import { ErrorState } from "@/components/states/states";

/** Error state for server-rendered pages: Retry re-runs the server render. */
export function RefreshError({ title, message }: { title?: string; message: string }) {
  const router = useRouter();
  return <ErrorState title={title} message={message} onRetry={() => router.refresh()} />;
}
