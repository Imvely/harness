import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  definition,
  directionHint,
  glossary,
  glossaryEntry,
  glossaryGroups,
  termLabel,
} from "../src/glossary";
import { lowerIsBetter, metricKeys } from "../src/utils";

const componentsDir = join(import.meta.dir, "..", "src", "components");

describe("glossary coverage", () => {
  test("every metric the UI prints has an entry", () => {
    // A metric with no entry is a bare acronym on screen with nowhere to look it up, which is
    // the state the whole app was in.
    for (const metric of metricKeys) {
      expect(glossaryEntry(metric)).toBeDefined();
    }
  });

  test("every entry says something in both languages", () => {
    for (const entry of glossary) {
      expect(entry.ko.length).toBeGreaterThan(0);
      expect(definition(entry, "ko").length).toBeGreaterThan(10);
      expect(definition(entry, "en").length).toBeGreaterThan(10);
    }
  });

  test("ids are unique and every entry belongs to a listed group", () => {
    const ids = glossary.map((entry) => entry.id);
    expect(new Set(ids).size).toBe(ids.length);
    const groups = new Set(glossaryGroups.map((group) => group.group));
    for (const entry of glossary) {
      expect(groups.has(entry.group)).toBe(true);
    }
  });
});

describe("glossary agrees with the rest of the app", () => {
  test("the direction hint matches the polarity rule the charts colour by", () => {
    // If these two ever disagree, the glossary tells the reader "lower is safer" about a metric
    // the chart paints green when it rises. One of them would be lying, and the reader has no
    // way to tell which.
    for (const metric of metricKeys) {
      const entry = glossaryEntry(metric)!;
      expect(entry.direction).toBe(lowerIsBetter(metric) ? "lower" : "higher");
    }
    expect(directionHint(glossaryEntry("apcer")!, "ko")).toBe("낮을수록 안전");
    expect(directionHint(glossaryEntry("auc")!, "ko")).toBe("높을수록 좋음");
  });

  test("a term with no direction offers no direction hint", () => {
    expect(directionHint(glossaryEntry("protocol-hash")!, "ko")).toBeNull();
  });

  test("Korean labels keep the acronym visible", () => {
    // The acronym is what the registry, the reports and the papers print, so translating it
    // away would leave the reader unable to match the screen to anything else.
    expect(termLabel(glossaryEntry("apcer")!, "ko")).toBe("공격 통과율 (APCER)");
    expect(termLabel(glossaryEntry("apcer")!, "en")).toBe("APCER");
  });

  test("every id in the GlossaryId union has an entry", () => {
    // `<Term>` and `<TermMark>` take `GlossaryId`, so tsc rejects a typo at the call site. What
    // it cannot see is a union member with no entry behind it: that compiles, then renders the
    // fallback text with no definition. This list is the union, and it has to stay in step.
    const declared = readFileSync(join(componentsDir, "..", "glossary.ts"), "utf8");
    const union = declared.slice(
      declared.indexOf("export type GlossaryId ="),
      declared.indexOf("export interface GlossaryEntry"),
    );
    const ids = [...union.matchAll(/"([a-z0-9-]+)"/g)].map((match) => match[1]!);
    expect(ids.length).toBe(glossary.length);
    for (const id of ids) {
      expect(glossaryEntry(id)).toBeDefined();
    }
  });
});
