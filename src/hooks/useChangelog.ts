import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import type { ChangelogData } from "../types/changelog";

export function useChangelog(): UseQueryResult<ChangelogData, Error> {
  return useQuery<ChangelogData>({
    queryKey: ["changelog"],
    queryFn: async () => {
      const response = await fetch("/changelog.json");
      if (!response.ok) {
        throw new Error("Failed to load changelog");
      }
      return response.json();
    },
    // Keep data fresh for 5 minutes
    staleTime: 5 * 60 * 1000,
    // Keep cached data for 30 minutes
    gcTime: 30 * 60 * 1000,
  });
}
