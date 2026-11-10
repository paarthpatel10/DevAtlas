import { ListSkeleton } from "@/components/states/skeletons";

export default function Loading() {
  return <ListSkeleton rows={3} label="Loading saved repositories…" />;
}
