/** Build an Explore URL from current params plus changes; empty values are removed. */
export function exploreHref(
  current: Record<string, string | undefined>,
  changes: Record<string, string | undefined>,
): string {
  const params = new URLSearchParams();
  const merged = { ...current, ...changes };
  for (const [key, value] of Object.entries(merged)) {
    if (value) params.set(key, value);
  }
  // Any change other than paging returns to the first page.
  if (!("page" in changes)) params.delete("page");
  const text = params.toString();
  return text ? `/explore?${text}` : "/explore";
}
