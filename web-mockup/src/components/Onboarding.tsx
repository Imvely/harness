import type { Locale } from "../types";

/**
 * What this dashboard is, shown once on a first visit.
 *
 * Until now the app opened straight onto a filtered table of APCER values. Someone arriving
 * without context had no way to learn what they were looking at, and — more dangerously — no
 * way to learn what the screen does *not* do. The control view composes a training command and
 * the report view composes an export command; both look like they might run something.
 *
 * Kept to four points on purpose. The glossary carries the vocabulary and the banner carries the
 * data's origin, so this card only has to orient someone, not teach them.
 */

const seenKey = "pad-research-web-mockup-guide-seen";

export function hasSeenGuide(): boolean {
  // A blocked or cleared store must not make the card reappear forever, nor hide it forever;
  // treating a throw as "not seen" shows it once per session, which is the safer failure.
  try {
    return window.localStorage.getItem(seenKey) === "1";
  } catch {
    return false;
  }
}

export function markGuideSeen(): void {
  try {
    window.localStorage.setItem(seenKey, "1");
  } catch {
    // Private browsing, blocked site data. Nothing to recover: the card simply shows again.
  }
}

interface Point {
  title: string;
  body: string;
}

function points(locale: Locale): Point[] {
  if (locale === "ko") {
    return [
      {
        title: "이 화면은 실험 결과를 읽기만 합니다",
        body: "학습이나 평가를 시작하지 않고, 설정 파일이나 데이터를 바꾸지도 않습니다. 하네스가 남긴 기록을 렌더링할 뿐입니다.",
      },
      {
        title: "맨 위 배너가 숫자의 출처를 먼저 말합니다",
        body: "예시 데이터인지, 실제로 내보낸 실행인지, 그 실행의 데이터셋이 합성인지를 구분합니다. 같은 0.05라도 출처에 따라 뜻이 다릅니다.",
      },
      {
        title: "모르는 약어는 옆의 ? 를 누르세요",
        body: "APCER, tau, protocol_hash 같은 용어는 왼쪽 용어 사전에서 한국어 설명과 “낮을수록 안전 / 높을수록 좋음” 방향을 함께 볼 수 있습니다.",
      },
      {
        title: "성능이 좋아 보여도 그것만으로는 결론이 아닙니다",
        body: "감사 화면에서 protocol hash가 같은지, 시드가 3개 이상인지, 보안 회귀 판정이 무엇인지를 확인한 뒤에야 비교가 성립합니다.",
      },
    ];
  }
  return [
    {
      title: "This screen only reads results",
      body: "It never starts training or evaluation, and never edits a config or the data. It renders what the harness recorded.",
    },
    {
      title: "The banner at the top states where the numbers came from",
      body: "Sample rows, a real export, or a real export on synthetic data. The same 0.05 means different things in each case.",
    },
    {
      title: "Press the ? beside a term you do not know",
      body: "APCER, tau, protocol_hash and the rest open in the glossary on the left, with a definition and whether lower or higher is better.",
    },
    {
      title: "A good-looking number is not a conclusion",
      body: "A comparison holds only after Audit confirms a matching protocol hash, at least three seeds, and the gate verdict.",
    },
  ];
}

export function Onboarding({ locale, onDismiss }: { locale: Locale; onDismiss: () => void }) {
  const ko = locale === "ko";
  return (
    <section aria-labelledby="onboarding-title" className="onboarding">
      <div className="onboarding__head">
        <div>
          <p className="eyebrow">{ko ? "처음 오셨다면" : "First time here"}</p>
          <h2 id="onboarding-title">
            {ko ? "이 대시보드를 읽는 법" : "How to read this dashboard"}
          </h2>
        </div>
        <button className="button button--secondary" onClick={onDismiss} type="button">
          {ko ? "알겠습니다" : "Got it"}
        </button>
      </div>
      <ol className="onboarding__points">
        {points(locale).map((point, index) => (
          <li key={point.title}>
            <span aria-hidden="true" className="onboarding__step">
              {index + 1}
            </span>
            <div>
              <strong>{point.title}</strong>
              <p>{point.body}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
