import type { Locale, MockDatabaseLoadResult, MockDbSeedSource } from "../types";
import { t } from "../i18n";

export function WarningBanner({
  seedSource,
  loadOrigin,
  locale,
}: {
  seedSource: MockDbSeedSource;
  loadOrigin: MockDatabaseLoadResult["origin"];
  locale: Locale;
}) {
  const sourceLabel =
    seedSource === "export"
      ? locale === "ko"
        ? "대시보드 내보내기 JSON이 mock DB에 적재되었습니다. "
        : "Dashboard export JSON is in the mock DB. "
      : locale === "ko"
        ? "정적 데모 행이 mock DB에 적재되었습니다. "
        : "Static demo rows are in the mock DB. ";
  return (
    <section className="safety-banner" aria-label="Research safety warnings">
      <div>
        <strong>{t(locale, "syntheticSafety")}</strong>
        <span>
          {sourceLabel}
          {locale === "ko"
            ? "스모크 실행, 적은 시드, 프로토콜 불일치는 연구 주장을 뒷받침할 수 없습니다."
            : "Smoke runs, seed-light samples, and protocol mismatches cannot support claims."}
        </span>
      </div>
      <div className="safety-pills" aria-label="Active safety rules">
        <span>
          {loadOrigin === "persisted"
            ? locale === "ko"
              ? "mock DB 저장됨"
              : "mock DB persisted"
            : locale === "ko"
              ? "mock DB 적재됨"
              : "mock DB seeded"}
        </span>
        <span>{t(locale, "devThresholdOnly")}</span>
        <span>{locale === "ko" ? "프로토콜 해시 확인" : "protocol hash checked"}</span>
        <span>{locale === "ko" ? "사람 전체 실행 승인" : "human full-run approval"}</span>
      </div>
    </section>
  );
}

// Safety copy contract: SYNTHETIC SANITY, NOT A RESEARCH RESULT, dev threshold only, human full-run approval.
