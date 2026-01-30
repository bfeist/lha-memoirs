import { execSync } from "child_process";
import { writeFileSync, mkdirSync, existsSync } from "fs";
import path from "path";
import type { Plugin } from "vite";

interface CommitInfo {
  hash: string;
  date: string;
  message: string;
}

interface ChangelogData {
  generatedAt: string;
  commits: CommitInfo[];
}

function getGitCommits(maxCommits?: number): CommitInfo[] {
  try {
    // Format: hash|date|message
    const limitFlag = maxCommits ? `-n ${maxCommits}` : "";
    const result = execSync(`git log --pretty=format:"%H|%ad|%s" --date=short ${limitFlag}`, {
      encoding: "utf-8",
    });

    return result
      .split("\n")
      .filter((line) => line.trim())
      .map((line) => {
        const [hash, date, ...messageParts] = line.split("|");
        return {
          hash: hash.substring(0, 7),
          date,
          message: messageParts.join("|"), // In case message contains |
        };
      });
  } catch (error) {
    console.warn("Failed to get git commits:", error);
    return [];
  }
}

function generateChangelog() {
  const commits = getGitCommits();
  const changelog: ChangelogData = {
    generatedAt: new Date().toISOString(),
    commits,
  };

  const publicDir = path.resolve(process.cwd(), "public");
  if (!existsSync(publicDir)) {
    mkdirSync(publicDir, { recursive: true });
  }

  const outputPath = path.join(publicDir, "changelog.json");
  writeFileSync(outputPath, JSON.stringify(changelog, null, 2));
  console.log(`✓ Generated changelog.json with ${commits.length} commits`);
}

export function gitChangelogPlugin(): Plugin {
  return {
    name: "vite-plugin-git-changelog",
    buildStart() {
      generateChangelog();
    },
    // handleHotUpdate() {
    //   generateChangelog();
    // },
  };
}
