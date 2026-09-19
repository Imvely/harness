import { describe, expect, test } from "bun:test";
import { gateText, modeText, statusText, t, viewLabel } from "../src/i18n";

describe("i18n", () => {
  test("returns Korean and English page labels", () => {
    expect(viewLabel("ko", "dashboard")).toBe("대시보드");
    expect(viewLabel("en", "dashboard")).toBe("Dashboard");
    expect(t("ko", "controlLab")).toBe("제어 실험실");
    expect(t("en", "controlLab")).toBe("Control Lab");
  });

  test("localizes research states", () => {
    expect(statusText("ko", "security_regression")).toBe("보안 회귀");
    expect(gateText("en", "comparison_blocked")).toBe("comparison blocked");
    expect(modeText("ko", "smoke")).toBe("스모크");
  });
});
