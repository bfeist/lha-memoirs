export interface CommitInfo {
  hash: string;
  date: string;
  message: string;
}

export interface ChangelogData {
  generatedAt: string;
  commits: CommitInfo[];
}
