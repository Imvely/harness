import type { DemoRun, Locale, MockDatabaseLoadResult, MockDbSeedSource } from "../types";

/**
 * The standing "what am I actually looking at" banner.
 *
 * This component existed before but was never rendered, so the app silently showed three
 * different kinds of data — bundled demo rows, rows exported from real MLflow runs, and rows
 * fabricated in the browser by the control lab — under identical chrome. Worse, a red
 * "demo only" badge was hardcoded elsewhere, so genuine exported results were labelled fake
 * while fabricated ones were not labelled at all.
 *
 * The banner now states the data's origin first, because every number below it means something
 * different depending on that origin, and a newcomer has no other way to tell.
 */

/**
 * "Where did these rows come from" has two independent axes, and collapsing them lies.
 *
 * A row can be a genuine MLflow export and still be worthless as evidence, because the
 * *dataset* behind it was synthetic. Labelling such an export simply "real results" would
 * reintroduce exactly the false confidence this banner exists to remove, so the synthetic
 * case gets its own state instead of being folded into `export`.
 */
export type DataOrigin = "demo" | "export_synthetic" | "export_real" | "mixed";

export function dataOrigin(seedSource: MockDbSeedSource, runs: DemoRun[]): DataOrigin {
  if (seedSource !== "export" || runs.length === 0) return "demo";
  if (runs.some((run) => run.demoOnly)) return "mixed";
  // `researchClaimAllowed` is the exporter's own verdict: it is false whenever any dataset
  // behind the run carries pii_policy "synthetic" (see dashboard/export.py).
  return runs.every((run) => !run.researchClaimAllowed) ? "export_synthetic" : "export_real";
}

type Copy = { tone: string; title: string; body: string };

function copyFor(origin: DataOrigin, locale: Locale): Copy {
  if (origin === "export_real") {
    return locale === "ko"
      ? {
          tone: "safety-banner--export",
          title: "실제 데이터로 측정된 결과입니다",
          body: "export_dashboard_data.py가 MLflow run에서 내보낸 값입니다. 연구 주장으로 쓰기 전에 protocol_hash가 같은지, seed가 3개 이상인지, gate 판정이 무엇인지를 감사 화면에서 확인하세요.",
        }
      : {
          tone: "safety-banner--export",
          title: "Measured on real data",
          body: "Exported from MLflow by export_dashboard_data.py. Before using these as a claim, check protocol_hash agreement, seed count, and the gate verdict in Audit.",
        };
  }
  if (origin === "export_synthetic") {
    return locale === "ko"
      ? {
          tone: "safety-banner--mixed",
          title: "실제 실행이지만 데이터가 합성입니다 — 연구 결과가 아닙니다",
          body: "MLflow에서 내보낸 진짜 run이므로 파이프라인이 어떻게 동작하는지는 보여줍니다. 다만 데이터셋이 합성이라 성능 주장에는 쓸 수 없습니다(모든 행의 research_claim_allowed가 false).",
        }
      : {
          tone: "safety-banner--mixed",
          title: "Real runs on synthetic data — not a research result",
          body: "These are genuine exported MLflow runs, so they show how the pipeline behaves. The datasets behind them are synthetic, so they cannot support a performance claim (every row has research_claim_allowed false).",
        };
  }
  if (origin === "mixed") {
    return locale === "ko"
      ? {
          tone: "safety-banner--mixed",
          title: "실제 결과와 브라우저가 만든 모의 행이 섞여 있습니다",
          body: "모의 행은 측정값이 아니라 이 화면이 공식으로 계산해 만든 숫자입니다. 표에서 '모의' 표시가 붙은 행은 어떤 비교에도 쓰지 마세요.",
        }
      : {
          tone: "safety-banner--mixed",
          title: "Real runs and browser-generated mock rows are mixed",
          body: "Mock rows are not measurements; this page computed them from a formula. Rows marked 'mock' must not be used in any comparison.",
        };
  }
  return locale === "ko"
    ? {
        tone: "safety-banner--demo",
        title: "SYNTHETIC SANITY — NOT A RESEARCH RESULT (합성 예시 데이터)",
        body: "화면을 둘러보기 위한 예시 행입니다. 측정된 결과가 아니므로 어떤 성능 주장에도 쓸 수 없습니다. 실제 결과를 보려면 export_dashboard_data.py로 내보낸 JSON을 web-mockup/public/ 에 두세요.",
      }
    : {
        tone: "safety-banner--demo",
        title: "SYNTHETIC SANITY — NOT A RESEARCH RESULT",
        body: "These are sample rows for exploring the UI. They are not measurements and cannot support any performance claim. To see real results, export JSON with export_dashboard_data.py into web-mockup/public/.",
      };
}

export function WarningBanner({
  origin,
  loadOrigin,
  locale,
}: {
  origin: DataOrigin;
  loadOrigin: MockDatabaseLoadResult["origin"];
  locale: Locale;
}) {
  const copy = copyFor(origin, locale);
  const ko = locale === "ko";
  return (
    <section
      className={`safety-banner ${copy.tone}`}
      aria-label={ko ? "표시 중인 데이터의 출처" : "Origin of the data on screen"}
    >
      <div>
        <strong>{copy.title}</strong>
        <span>{copy.body}</span>
      </div>
      <div className="safety-pills" aria-label={ko ? "항상 적용되는 규칙" : "Always-on rules"}>
        <span>{ko ? "임계값은 dev에서만 (dev threshold only)" : "dev threshold only"}</span>
        <span>{ko ? "protocol hash 일치 시에만 비교" : "protocol hash checked"}</span>
        <span>{ko ? "전체 실행은 사람 승인 (human full-run approval)" : "human full-run approval"}</span>
        <span>
          {loadOrigin === "persisted"
            ? ko
              ? "브라우저 저장본 사용 중"
              : "mock DB persisted"
            : ko
              ? "새로 적재됨"
              : "mock DB seeded"}
        </span>
      </div>
    </section>
  );
}

// Safety copy contract: SYNTHETIC SANITY, NOT A RESEARCH RESULT, dev threshold only, human full-run approval.
