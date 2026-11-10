import Link from "next/link";

import { EmptyState } from "@/components/states/states";

export default function RepositoryNotFound() {
  return (
    <EmptyState
      title="Repository not in the index"
      message="This repository isn't in the curated dataset yet, or the name has changed."
      action={
        <Link href="/explore" className="text-sm text-accent hover:underline">
          Browse Explore
        </Link>
      }
    />
  );
}
