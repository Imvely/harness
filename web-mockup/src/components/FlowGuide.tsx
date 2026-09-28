import type { Locale } from "../types";
import { Hint } from "./Hint";

/**
 * Where you are in the work, and what comes next.
 *
 * Walking the app as someone who has never done this: the sidebar opened on results, the setup
 * screens sat at the bottom, and nothing anywhere said that the order is the other way round —
 * read, connect data, configure, *run it in a terminal*, then come back for the numbers. The
 * terminal step is the one that breaks people: the screen composes a command, says it will not
 * run it, and then never says where the result appears or how long it takes.
 *
 * So the five steps are stated once, in order, on every screen. The step you are on is marked,
 * the others are one click away, and the step that does not live in this app says so.
 */

export type FlowView =
  | "literature"
  | "storage"
  | "control"
  | "runs"
  | "dashboard"
  | "compare"
  | "report"
  | "audit";

export interface FlowStep {
  n: number;
  /** The view this step opens, or null for the one that happens outside this app. */
  view: FlowView | null;
  ko: { title: string; body: string };
  en: { title: string; body: string };
}

export const FLOW: FlowStep[] = [
  {
    n: 1,
    view: "literature",
    ko: {
      title: "논문 찾기",
      body: "이미 밝혀진 것과 아직 아닌 것을 봅니다. 여기서 읽은 논문을 나중에 실험과 연결해 두면, 결과를 설명할 때 근거가 따라옵니다.",
    },
    en: {
      title: "Read first",
      body: "See what is already known. A paper linked to an experiment here becomes the evidence behind that result later.",
    },
  },
  {
    n: 2,
    view: "storage",
    ko: {
      title: "데이터 연결",
      body: "내 컴퓨터가 영상 데이터에 닿는지 확인합니다. 한 번만 하면 됩니다.",
    },
    en: {
      title: "Connect the data",
      body: "Check that this machine can reach the clips. Done once.",
    },
  },
  {
    n: 3,
    view: "control",
    ko: {
      title: "실험 설정",
      body: "무엇을·어떤 데이터로·어떤 모델로 할지 고르면 명령 한 줄이 만들어집니다.",
    },
    en: {
      title: "Set up a run",
      body: "Choose the goal, the data and the model; the screen writes the command.",
    },
  },
  {
    n: 4,
    view: null,
    ko: {
      title: "터미널에서 실행",
      body: "복사한 명령을 터미널에 붙여넣습니다. 이 화면은 학습을 시작하지 않습니다 — 결과가 나오기까지 몇 분에서 몇 시간이 걸리고, 끝나면 다음 단계에 나타납니다.",
    },
    en: {
      title: "Run it in a terminal",
      body: "Paste the command there. This app never starts training. A run takes minutes to hours, and shows up in the next step when it finishes.",
    },
  },
  {
    n: 5,
    view: "runs",
    ko: {
      title: "결과 보기",
      body: "실행 목록에 숫자가 나타납니다. 대시보드는 전체 흐름, 비교는 두 실험의 차이, 감사는 그 숫자를 믿어도 되는지를 봅니다.",
    },
    en: {
      title: "Read the result",
      body: "The numbers appear in the run list. The dashboard shows the trend, compare shows a difference, and the audit view says whether to trust it.",
    },
  },
];

/** Which step a view belongs to, so the strip can mark where the reader is. */
export function stepFor(view: string): number {
  if (view === "literature") return 1;
  if (view === "storage") return 2;
  if (view === "control") return 3;
  if (view === "runs" || view === "dashboard" || view === "compare" || view === "report" || view === "audit") {
    return 5;
  }
  return 0;
}

export function FlowStrip({
  view,
  locale,
  onNavigate,
}: {
  view: string;
  locale: Locale;
  onNavigate: (view: FlowView) => void;
}) {
  const current = stepFor(view);
  return (
    <nav aria-label={locale === "ko" ? "실험하는 순서" : "How a run happens"} className="flow-strip">
      <span className="flow-strip__lead">
        {locale === "ko" ? "순서" : "Order"}
        <Hint align="start" label={locale === "ko" ? "전체 순서 설명" : "About this order"}>
          {locale === "ko"
            ? "논문을 읽고, 데이터를 연결하고, 실험을 설정해 명령을 복사한 뒤, 그 명령을 터미널에서 실행합니다. 실행이 끝나면 결과가 이 앱의 '실행 목록'에 나타납니다. 이 앱은 어떤 학습도 직접 시작하지 않습니다."
            : "Read, connect the data, configure a run and copy its command, then run that command in a terminal. When it finishes, the result appears in this app's run list. This app never starts training itself."}
        </Hint>
      </span>
      <ol className="flow-strip__steps">
        {FLOW.map((step) => {
          const state = step.n === current ? "is-current" : step.n < current ? "is-done" : "";
          const label = step[locale].title;
          if (step.view === null) {
            return (
              <li className={`flow-step flow-step--outside ${state}`} key={step.n}>
                <span className="flow-step__n">{step.n}</span>
                <span className="flow-step__title">{label}</span>
                <Hint align="center" label={label}>
                  {step[locale].body}
                </Hint>
              </li>
            );
          }
          // No ? per step: five in a row is noise, the lead one explains the whole order, and
          // the guide spells out each step. A native `title` is not the answer either — it
          // appears late, cannot be styled, and never shows on touch (see Hint).
          return (
            <li className={`flow-step ${state}`} key={step.n}>
              <button
                aria-current={step.n === current ? "step" : undefined}
                className="flow-step__button"
                onClick={() => onNavigate(step.view as FlowView)}
                type="button"
              >
                <span className="flow-step__n">{step.n}</span>
                <span className="flow-step__title">{label}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/**
 * The same five steps as a card, for someone who has just arrived.
 *
 * The strip is a reminder; this is the explanation, and it is what the first-visit guide opens
 * with — before any vocabulary, because "what do I do here" comes before "what does APCER mean".
 */
export function FlowCard({ locale }: { locale: Locale }) {
  return (
    <ol className="flow-card">
      {FLOW.map((step) => (
        <li key={step.n}>
          <span className="flow-card__n">{step.n}</span>
          <div>
            <strong>
              {step[locale].title}
              {step.view === null && (
                <span className="pill pill--outside">
                  {locale === "ko" ? "이 앱 밖에서" : "outside this app"}
                </span>
              )}
            </strong>
            <span>{step[locale].body}</span>
          </div>
        </li>
      ))}
    </ol>
  );
}
