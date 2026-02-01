import { describe, it, expect } from "vitest";
import {
  buildYearPattern,
  expandAbbreviatedYear,
  findTimelineEntryForYear,
  parseTextWithYears,
} from "../hooks/useTimelineYears";
import type { TimelineData, TimelineEntry } from "../types/timeline";

describe("useTimelineYears", () => {
  describe("buildYearPattern", () => {
    it("matches full 4-digit years in the 1900s", () => {
      const pattern = buildYearPattern();
      const text = "In 1917, something happened.";
      const matches = [...text.matchAll(pattern)];
      expect(matches).toHaveLength(1);
      expect(matches[0][1]).toBe("1917");
    });

    it("matches full 4-digit years in the 1800s", () => {
      const pattern = buildYearPattern();
      const text = "Back in 1899.";
      const matches = [...text.matchAll(pattern)];
      expect(matches).toHaveLength(1);
      expect(matches[0][1]).toBe("1899");
    });

    it("matches abbreviated years with apostrophe", () => {
      const pattern = buildYearPattern();
      const text = "Around '17 or so.";
      const matches = [...text.matchAll(pattern)];
      expect(matches).toHaveLength(1);
      expect(matches[0][2]).toBe("17");
    });

    it("matches multiple years in text", () => {
      const pattern = buildYearPattern();
      const text = "From 1914 to '18, that would take us through 1916, '17, I'd say.";
      const matches = [...text.matchAll(pattern)];
      expect(matches).toHaveLength(4);
    });

    it("does not match years outside 18xx/19xx range", () => {
      const pattern = buildYearPattern();
      const text = "In 2024, things changed.";
      const matches = [...text.matchAll(pattern)];
      expect(matches).toHaveLength(0);
    });

    it("does not match partial numbers", () => {
      const pattern = buildYearPattern();
      const text = "The number 12345 is not a year.";
      const matches = [...text.matchAll(pattern)];
      expect(matches).toHaveLength(0);
    });
  });

  describe("expandAbbreviatedYear", () => {
    it("converts 2-digit year to 1900s", () => {
      expect(expandAbbreviatedYear("17")).toBe(1917);
      expect(expandAbbreviatedYear("02")).toBe(1902);
      expect(expandAbbreviatedYear("65")).toBe(1965);
    });
  });

  describe("findTimelineEntryForYear", () => {
    const mockEntries: TimelineEntry[] = [
      {
        year_start: 1902,
        year_end: 1902,
        title: "Birth",
        description: "",
        age_start: 0,
        age_end: 0,
        excerpts: [],
      },
      {
        year_start: 1905,
        year_end: 1907,
        title: "Early Years",
        description: "",
        age_start: 3,
        age_end: 5,
        excerpts: [],
      },
      {
        year_start: 1911,
        year_end: 1916,
        title: "Childhood",
        description: "",
        age_start: 9,
        age_end: 14,
        excerpts: [],
      },
    ];

    it("finds exact year match", () => {
      expect(findTimelineEntryForYear(1902, mockEntries)).toBe(0);
    });

    it("finds year within range", () => {
      expect(findTimelineEntryForYear(1906, mockEntries)).toBe(1);
      expect(findTimelineEntryForYear(1914, mockEntries)).toBe(2);
    });

    it("returns undefined for years not in any entry", () => {
      expect(findTimelineEntryForYear(1904, mockEntries)).toBeUndefined();
      expect(findTimelineEntryForYear(2000, mockEntries)).toBeUndefined();
    });
  });

  describe("parseTextWithYears", () => {
    const mockTimelineData: TimelineData = {
      generatedAt: "2026-01-01",
      timelineStart: 1902,
      timelineEnd: 1966,
      entries: [
        {
          year_start: 1902,
          year_end: 1902,
          title: "Birth",
          description: "",
          age_start: 0,
          age_end: 0,
          excerpts: [],
        },
        {
          year_start: 1911,
          year_end: 1916,
          title: "Childhood",
          description: "",
          age_start: 9,
          age_end: 14,
          excerpts: [],
        },
      ],
    };

    it("parses text without years", () => {
      const result = parseTextWithYears("No years here.", mockTimelineData);
      expect(result).toHaveLength(1);
      expect(result[0].type).toBe("text");
      expect(result[0].content).toBe("No years here.");
    });

    it("parses full year in text", () => {
      const result = parseTextWithYears("Born in 1902.", mockTimelineData);
      expect(result).toHaveLength(3);
      expect(result[0]).toEqual({ type: "text", content: "Born in " });
      expect(result[1]).toEqual({
        type: "year",
        content: "1902",
        year: 1902,
        entryIndex: 0,
      });
      expect(result[2]).toEqual({ type: "text", content: "." });
    });

    it("parses abbreviated year", () => {
      const result = parseTextWithYears("Around '14 or so.", mockTimelineData);
      expect(result).toHaveLength(3);
      expect(result[1]).toEqual({
        type: "year",
        content: "'14",
        year: 1914,
        entryIndex: 1,
      });
    });

    it("treats years outside timeline range as text", () => {
      const result = parseTextWithYears("In 1800, nothing.", mockTimelineData);
      // 1800 is outside the 1902-1966 range, so it should be parsed as plain text segments
      // The regex still matches 18xx but parseTextWithYears converts it to text type
      const yearSegments = result.filter((s) => s.type === "year");
      expect(yearSegments).toHaveLength(0);
    });

    it("handles mixed full and abbreviated years", () => {
      const result = parseTextWithYears("From 1914 to '16, those years.", mockTimelineData);
      const yearSegments = result.filter((s) => s.type === "year");
      expect(yearSegments).toHaveLength(2);
      expect(yearSegments[0].year).toBe(1914);
      expect(yearSegments[1].year).toBe(1916);
    });

    it("returns plain text segments when no timeline data", () => {
      const result = parseTextWithYears("In 1914.", null);
      // With no timeline data, years are not detected as clickable links
      const yearSegments = result.filter((s) => s.type === "year");
      expect(yearSegments).toHaveLength(0);
    });
  });
});
