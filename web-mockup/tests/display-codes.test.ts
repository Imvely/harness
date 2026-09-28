import { describe, expect, test } from "bun:test";
import { demoRuns } from "../src/data/demoRuns";
import { artifactLabel, claimBlockerLabel, runNoteLabel } from "../src/i18n";
import { ClaimBlockerSchema, RunNoteSchema } from "../src/db/schema";
import type { ClaimBlocker, Locale, RunNote } from "../src/types";

const LOCALES: Locale[] = ["ko", "en"];

describe("nothing the UI shows a human arrives as prose", () => {
  test("every demo run's blockers and notes are codes, not sentences", () => {
    // The exporter used to send English sentences and this UI printed them verbatim, so a
    // Korean reader met them mid-panel. A code has no language; a sentence has one.
    for (const run of demoRuns) {
      for (const blocker of run.claimEligibility.blockers) {
        expect(blocker).not.toContain(" ");
        expect(ClaimBlockerSchema.safeParse(blocker).success).toBe(true);
      }
      for (const note of run.notes) {
        expect(note).not.toContain(" ");
        expect(RunNoteSchema.safeParse(note).success).toBe(true);
      }
    }
  });

  test("an artifact carries a path, never a label", () => {
    for (const run of demoRuns) {
      for (const artifact of run.artifacts) {
        expect(artifact).not.toHaveProperty("label");
        expect(artifact.path).toContain("/");
      }
    }
  });
});

describe("every code renders in both languages", () => {
  test("each blocker has a translation, and the Korean one is Korean", () => {
    for (const blocker of ClaimBlockerSchema.options as ClaimBlocker[]) {
      for (const locale of LOCALES) {
        const text = claimBlockerLabel(locale, blocker);
        expect(text.length).toBeGreaterThan(10);
        // A missing translation would fall through to the English string in both slots.
        if (locale === "ko") expect(/[가-힣]/.test(text)).toBe(true);
      }
    }
  });

  test("each run note has a translation in both languages", () => {
    for (const note of RunNoteSchema.options as RunNote[]) {
      for (const locale of LOCALES) {
        const text = runNoteLabel(locale, note);
        expect(text.length).toBeGreaterThan(5);
        if (locale === "ko") expect(/[가-힣]/.test(text)).toBe(true);
      }
    }
  });

  test("an artifact is named by its file, and an unknown one still reads as itself", () => {
    expect(artifactLabel("ko", { path: "outputs/x/eval_test.json", kind: "json" })).toBe(
      "test 평가 결과",
    );
    expect(artifactLabel("en", { path: "outputs/x/eval_test.json", kind: "json" })).toBe(
      "Test evaluation",
    );
    // No entry: the file name beats a generic word like "Artifact", which the loader used to
    // substitute for anything it did not recognise.
    expect(artifactLabel("ko", { path: "outputs/x/something_new.json", kind: "json" })).toBe(
      "something_new.json",
    );
  });
});
