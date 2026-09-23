import { describe, expect, test } from "bun:test";
import { gateText, modeText, statusText, t, viewLabel } from "../src/i18n";

describe("i18n", () => {
  test("returns Korean and English page labels", () => {
    expect(viewLabel("ko", "dashboard")).toBe("대시보드");
    expect(viewLabel("en", "dashboard")).toBe("Dashboard");
    // The setup screen is named for what a person does there, not for the config it writes.
    expect(t("ko", "controlLab")).toBe("실험 설정하기");
    expect(t("en", "controlLab")).toBe("Set up a run");
    expect(viewLabel("ko", "control")).toBe("실험 만들기");
  });

  test("localizes research states", () => {
    expect(statusText("ko", "security_regression")).toBe("보안 회귀");
    expect(gateText("en", "comparison_blocked")).toBe("comparison blocked");
    expect(modeText("ko", "smoke")).toBe("스모크");
  });
});
