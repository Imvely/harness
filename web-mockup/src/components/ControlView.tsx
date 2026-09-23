import { useState } from "react";
import type {
  AdaptationMethod,
  ControlState,
  DemoRun,
  ExperimentGoal,
  Locale,
  MockDatabaseState,
} from "../types";
import {
  buildLaunchCommand,
  buildValidationCommand,
  buildYamlPatch,
  launchBlocker,
} from "../db/controlPreview";
import { ControlStateSchema } from "../db/schema";
import { validateControlState } from "../db/mockDb";
import { MODEL_GROUP_LABELS, MODEL_GROUP_ORDER, modelById, modelsInGroup } from "../data/modelCatalog";
import type { ModelEntry } from "../data/modelCatalog";
import { summarise } from "../db/datasetSelection";
import { contextQuery } from "../db/literatureSearch";
import { localeDate, t } from "../i18n";
import { DatasetTree } from "./DatasetTree";
import { Field } from "./Field";
import { Hint } from "./Hint";
import { PaperLinks } from "./PaperLinks";

type ControlActionResult = {
  ok: boolean;
  message: string;
  issues: string[];
};

/**
 * Four questions, asked in the order a person can answer them.
 *
 * The screen used to be one grid of eleven controls — experiment id, adaptation method, source
 * run id, protocol id, threshold rule — every one of them visible whether or not it applied, and
 * each named after the config key it writes. That is a form you can only fill in if you already
 * know the answer.
 *
 * Now: what is this for, which data, which model, and then the numbers. Each step shows only
 * what its answer needs — a baseline has no source run to pick — and the terms behind a `?`.
 * The right-hand column stays honest about what the screen can do: it drafts and previews, and
 * a run still starts in a terminal after validation.
 */

const GOALS: {
  id: ExperimentGoal;
  ko: { title: string; body: string };
  en: { title: string; body: string };
  method: AdaptationMethod;
}[] = [
  {
    id: "baseline",
    method: "none",
    ko: {
      title: "그냥 학습해서 다른 환경에서 재보기",
      body: "적응 없이 학습하고, 본 적 없는 도메인에서 평가합니다. 다른 모든 결과의 기준선입니다.",
    },
    en: {
      title: "Train, then measure on an unseen domain",
      body: "No adaptation: train and evaluate on a domain the model never saw. Every other result is compared with this.",
    },
  },
  {
    id: "adapt_real_only",
    method: "spoof_preserve",
    ko: {
      title: "새 환경에 진짜 영상만 있을 때 적응",
      body: "목표 환경에서 얻을 수 있는 게 진짜 얼굴뿐인 경우입니다. 실제 도입 상황에 가장 가깝습니다.",
    },
    en: {
      title: "Adapt where only bona fide clips exist",
      body: "The target domain gives you real faces and nothing else — the situation an actual deployment starts in.",
    },
  },
  {
    id: "adapt_few_shot",
    method: "full_finetune",
    ko: {
      title: "새 환경에 진짜+공격 소수만 있을 때 적응",
      body: "목표 환경의 공격 영상을 몇 개 확보한 경우입니다. 위쪽 설정보다 유리하며, 둘을 비교하는 것이 연구 질문입니다.",
    },
    en: {
      title: "Adapt with a few labelled attacks",
      body: "A handful of target-domain attacks are available. It should beat the real-only setting, and comparing the two is the research question.",
    },
  },
];

export const initialControl: ControlState = {
  experimentId: "exp_ui_spoof_preserve_lab",
  goal: "adapt_real_only",
  modelId: "video_baseline",
  datasets: {
    train: ["aihub115/train"],
    dev: ["aihub115/dev"],
    test: ["idiap_replayattack/test"],
  },
  modelFamily: "video_baseline",
  frames: 8,
  batchSize: 8,
  epochs: 1,
  learningRate: "0.001",
  adaptationMethod: "spoof_preserve",
  sourceRunId: "run_syn_e02_video_source_only_1_full",
  protocolId: "syn_a_to_b_bf_adapt_v1",
  thresholdRule: "eer",
  smokeMode: true,
  seed: 4,
};

export function ControlView({
  control,
  database,
  locale = "en",
  sourceRuns,
  onChange,
  onSaveDraft,
  onCommandCopied,
}: {
  control: ControlState;
  database: MockDatabaseState;
  locale?: Locale;
  sourceRuns: DemoRun[];
  onChange: (control: ControlState) => void;
  onSaveDraft: () => ControlActionResult;
  onCommandCopied: (command: string) => void;
}) {
  const [actionMessage, setActionMessage] = useState<ControlActionResult | null>(null);
  const command = buildLaunchCommand(control);
  const yamlPatch = buildYamlPatch(control);
  const validationCommand = buildValidationCommand(control);
  const issues = validateControlState(control);
  const blocker = launchBlocker(control);
  const commandIsCopyable = blocker === null;
  const model = modelById(control.modelId);
  const recentDrafts = database.drafts.slice(0, 4);
  const adapting = control.goal !== "baseline";
  const testSummary = summarise(control.datasets, "test");
  const trainSummary = summarise(control.datasets, "train");

  const copyCommand = async () => {
    if (!commandIsCopyable) {
      setActionMessage({
        ok: false,
        message: locale === "ko" ? "아직 실행할 수 없는 구성입니다." : "This configuration cannot run yet.",
        issues: blocker ? [blocker, ...issues] : issues,
      });
      return;
    }
    try {
      await navigator.clipboard.writeText(command);
      onCommandCopied(command);
      setActionMessage({ ok: true, message: t(locale, "commandCopied"), issues: [] });
    } catch {
      setActionMessage({
        ok: false,
        message: "Clipboard permission was not available.",
        issues: ["Copy the command manually from the preview block."],
      });
    }
  };

  const pickGoal = (goal: ExperimentGoal) => {
    const method = GOALS.find((entry) => entry.id === goal)?.method ?? "none";
    onChange({ ...control, goal, adaptationMethod: method });
  };

  const pickModel = (entry: ModelEntry) => {
    onChange({
      ...control,
      modelId: entry.id,
      // The run table filters by family, so it follows the choice rather than being set twice.
      modelFamily: entry.frames > 1 ? "video_baseline" : "frame_baseline",
      frames: Math.min(16, Math.max(1, entry.frames)),
    });
  };

  return (
    <div className="page-grid page-grid--control">
      <section className="card card--wide step">
        <StepHead
          n={1}
          locale={locale}
          ko="무엇을 하려는 실험인가요?"
          en="What is this experiment for?"
          hintKo="이 답이 아래 설정을 결정합니다. 적응을 쓰지 않으면 원본 실행이나 적응 방법을 고를 필요가 없습니다."
          hintEn="This answer decides the rest: without adaptation there is no source run and no method to choose."
        />
        <div className="goal-grid">
          {GOALS.map((goal) => (
            <button
              aria-pressed={control.goal === goal.id}
              className={`goal-card${control.goal === goal.id ? " is-active" : ""}`}
              key={goal.id}
              onClick={() => pickGoal(goal.id)}
              type="button"
            >
              <strong>{goal[locale].title}</strong>
              <span>{goal[locale].body}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="card card--wide step">
        <StepHead
          n={2}
          locale={locale}
          ko="어떤 데이터로 할까요?"
          en="Which data?"
          hintKo="도메인을 펼쳐 조명·공격 종류까지 고를 수 있습니다. 고른 것이 학습·검증·테스트 중 어디에 들어가는지는 위의 탭에서 정합니다."
          hintEn="Open a domain to pick down to a lighting condition or an attack type. The tabs above decide which role it goes into."
        />
        <DatasetTree
          locale={locale}
          onChange={(datasets) => onChange({ ...control, datasets })}
          selection={control.datasets}
        />
      </section>

      <section className="card card--wide step">
        <StepHead
          n={3}
          locale={locale}
          ko="어떤 모델로 할까요?"
          en="Which model?"
          hintKo="파라미터 수가 적은 것부터 나열했습니다. '준비됨'은 이 저장소에 adapter가 있다는 뜻이고, '후보'는 리서치 목록에만 있어 설정 초안까지만 만들 수 있다는 뜻입니다."
          hintEn="Listed by parameter count. 'Ready' means this repository has an adapter; 'candidate' means it is on the research list and only a config draft can be made."
        />
        <ModelPicker locale={locale} modelId={control.modelId} onPick={pickModel} />
      </section>

      <section className="command-card">
        <div className="section-heading">
          <h2>
            {locale === "ko" ? "실행 준비 상태" : "Ready to run?"}
            <Hint label={locale === "ko" ? "이 화면의 한계" : "What this screen does not do"}>
              {locale === "ko"
                ? "이 UI는 학습을 시작하지 않습니다. 첫 줄은 설정 검증, 둘째 줄은 실행 명령이며, 실제 실행은 터미널에서 합니다."
                : "This UI does not start training. The first line validates, the second is the launch command, and a run happens in a terminal."}
            </Hint>
          </h2>
        </div>
        {blocker ? (
          <p className="action-message action-message--warn" role="status">
            {locale === "ko" ? "아직 실행할 수 없습니다" : "Not runnable yet"}
            <br />
            {blockerText(locale, blocker)}
          </p>
        ) : (
          <p className="action-message action-message--ok" role="status">
            {locale === "ko"
              ? "구성이 검증을 통과했습니다. 아래 명령을 터미널에서 실행하세요."
              : "The configuration passes validation. Run the commands below in a terminal."}
          </p>
        )}
        <div className="run-summary">
          <span>
            {locale === "ko" ? "학습" : "Train"}
            <strong>{trainSummary.clips.toLocaleString()}</strong>
          </span>
          <span>
            {locale === "ko" ? "테스트" : "Test"}
            <strong>{testSummary.clips.toLocaleString()}</strong>
          </span>
          <span>
            {locale === "ko" ? "모델" : "Model"}
            <strong>{model?.label ?? control.modelId}</strong>
          </span>
        </div>
        <pre>{validationCommand}</pre>
        <pre>{command}</pre>
        <div className="command-actions">
          <button
            className="button button--primary"
            disabled={!commandIsCopyable}
            onClick={copyCommand}
            type="button"
          >
            {t(locale, "copyCommand")}
          </button>
          <button className="button button--secondary" onClick={() => setActionMessage(onSaveDraft())} type="button">
            {t(locale, "saveDraft")}
          </button>
        </div>
        {actionMessage && (
          <div
            className={actionMessage.ok ? "action-message action-message--ok" : "action-message action-message--warn"}
            role="status"
          >
            <strong>{actionMessage.message}</strong>
            {actionMessage.issues.length > 0 && (
              <ul>
                {actionMessage.issues.slice(0, 6).map((issue) => (
                  <li key={issue}>{issue}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>

      <details className="card card--wide step step--advanced">
        <summary>
          <span className="step__n">4</span>
          {locale === "ko" ? "자세한 설정 (기본값으로 충분합니다)" : "Details (the defaults are fine)"}
        </summary>
        <div className="control-grid">
          <Field
            label={locale === "ko" ? "실험 이름" : "Experiment name"}
            hint={
              locale === "ko"
                ? "결과와 config 파일을 찾는 이름입니다. exp_ 로 시작하고 영소문자·숫자·밑줄만 씁니다."
                : "How results and the config file are found. It starts with exp_ and uses lower-case letters, digits and underscores."
            }
          >
            {(id) => (
              <input
                id={id}
                onChange={(event) => onChange({ ...control, experimentId: event.target.value })}
                placeholder="exp_ui_spoof_preserve_lab"
                value={control.experimentId}
              />
            )}
          </Field>
          <Field
            label={locale === "ko" ? "한 번에 보는 프레임" : "Frames per clip"}
            hint={
              locale === "ko"
                ? "모델이 한 번에 읽는 프레임 수입니다. 1이면 움직임을 보지 않습니다. 모델을 고르면 그 모델의 기본값으로 맞춰집니다."
                : "How many frames the model reads at once. One frame means no motion at all; picking a model sets its own default."
            }
          >
            {(id) => (
              <input
                id={id}
                max={16}
                min={1}
                onChange={(event) => onChange({ ...control, frames: Number(event.target.value) })}
                type="number"
                value={control.frames}
              />
            )}
          </Field>
          <Field label={locale === "ko" ? "배치 크기" : "Batch size"}>
            {(id) => (
              <input
                id={id}
                max={64}
                min={1}
                onChange={(event) => onChange({ ...control, batchSize: Number(event.target.value) })}
                type="number"
                value={control.batchSize}
              />
            )}
          </Field>
          <Field
            label={locale === "ko" ? "반복 횟수 (에폭)" : "Epochs"}
            hint={
              locale === "ko"
                ? "데이터를 몇 번 반복해서 볼지입니다. 짧게 점검만 하는 모드에서는 1로 고정됩니다."
                : "How many times the data is seen. The quick-check mode keeps it at 1."
            }
          >
            {(id) => (
              <input
                disabled={control.smokeMode}
                id={id}
                max={20}
                min={1}
                onChange={(event) => onChange({ ...control, epochs: Number(event.target.value) })}
                type="number"
                value={control.epochs}
              />
            )}
          </Field>
          <Field label={locale === "ko" ? "학습률" : "Learning rate"}>
            {(id) => (
              <input
                id={id}
                onChange={(event) => onChange({ ...control, learningRate: event.target.value })}
                value={control.learningRate}
              />
            )}
          </Field>
          <Field
            label={locale === "ko" ? "난수 시드" : "Seed"}
            hint={
              locale === "ko"
                ? "같은 시드면 같은 결과가 나옵니다. 결론을 낼 때는 시드를 여러 개 돌려 폭을 함께 봅니다."
                : "The same seed gives the same result. A conclusion needs several seeds, reported with their spread."
            }
          >
            {(id) => (
              <input
                id={id}
                max={999}
                min={1}
                onChange={(event) => onChange({ ...control, seed: Number(event.target.value) })}
                type="number"
                value={control.seed}
              />
            )}
          </Field>
          <Field
            label={locale === "ko" ? "임계값을 정하는 규칙" : "How the threshold is chosen"}
            hint={
              locale === "ko"
                ? "점수를 진짜/공격으로 가르는 기준을 어디서 정하는지입니다. 항상 검증 데이터에서만 정하고, 테스트에서는 절대 고르지 않습니다. EER은 두 오류가 같아지는 지점입니다."
                : "Where the cut between real and attack comes from. Always fitted on validation data, never chosen on test. EER is the point where the two error rates meet."
            }
          >
            {(id) => (
              <select
                id={id}
                onChange={(event) =>
                  onChange({ ...control, thresholdRule: event.target.value as ControlState["thresholdRule"] })
                }
                value={control.thresholdRule}
              >
                <option value="eer">{locale === "ko" ? "EER (두 오류가 같아지는 점)" : "EER (equal error rate)"}</option>
                <option value="bpcer_at_apcer">
                  {locale === "ko" ? "공격 통과율을 고정하고 맞추기" : "Fix the attack pass rate"}
                </option>
              </select>
            )}
          </Field>
          {adapting && (
            <Field
              label={locale === "ko" ? "적응 방법" : "Adaptation method"}
              hint={
                locale === "ko"
                  ? "학습된 모델을 새 환경에 맞추는 방식입니다. 위에서 고른 목적에 맞는 기본값이 들어가 있습니다."
                  : "How a trained model is moved to the new domain. The goal above picks a sensible default."
              }
            >
              {(id) => (
                <select
                  id={id}
                  onChange={(event) =>
                    onChange({ ...control, adaptationMethod: event.target.value as AdaptationMethod })
                  }
                  value={control.adaptationMethod}
                >
                  <option value="spoof_preserve">spoof_preserve</option>
                  <option value="full_finetune">full_finetune</option>
                  <option value="head_only">head_only</option>
                  <option value="prototype">prototype</option>
                </select>
              )}
            </Field>
          )}
          {adapting && (
            <Field
              label={locale === "ko" ? "어느 학습 결과에서 이어서 할까요" : "Which trained run to adapt"}
              hint={
                locale === "ko"
                  ? "적응은 이미 학습된 모델에서 출발합니다. 그 모델을 만든 실행의 ID입니다."
                  : "Adaptation starts from an already trained model; this is the id of the run that produced it."
              }
            >
              {(id) =>
                sourceRuns.length > 0 ? (
                  <select
                    id={id}
                    onChange={(event) => onChange({ ...control, sourceRunId: event.target.value })}
                    value={control.sourceRunId}
                  >
                    {sourceRuns.slice(0, 30).map((run) => (
                      <option key={run.runId} value={run.runId}>
                        {run.runId}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    id={id}
                    onChange={(event) => onChange({ ...control, sourceRunId: event.target.value })}
                    value={control.sourceRunId}
                  />
                )
              }
            </Field>
          )}
          <Field
            label={locale === "ko" ? "protocol 파일 이름" : "Protocol file name"}
            hint={
              locale === "ko"
                ? "데이터 구성은 커밋된 protocol 파일이 소유합니다. 위에서 고른 트리는 그 파일에 들어갈 초안이며, 이 UI가 파일을 만들지는 않습니다."
                : "A committed protocol file owns the data composition. The tree above drafts what goes in it; this UI does not write the file."
            }
          >
            {(id) => (
              <input
                id={id}
                onChange={(event) => onChange({ ...control, protocolId: event.target.value })}
                value={control.protocolId}
              />
            )}
          </Field>
          <label className="check-field check-field--large">
            <input
              checked={control.smokeMode}
              onChange={(event) =>
                onChange({
                  ...control,
                  smokeMode: event.target.checked,
                  epochs: event.target.checked ? 1 : control.epochs,
                })
              }
              type="checkbox"
            />
            {locale === "ko" ? "짧게 점검만 (스모크)" : "Quick check only (smoke)"}
          </label>
        </div>
        <pre className="yaml-preview">{yamlPatch}</pre>
      </details>

      <section className="card">
        <div className="section-heading">
          <h2>
            {locale === "ko" ? "이 구성과 관련된 논문" : "Papers for this configuration"}
            <Hint label={locale === "ko" ? "검색 설명" : "About these searches"}>
              {locale === "ko"
                ? "지금 고른 모델과 데이터로 만든 검색입니다. 수치를 인용할 때는 원문 PDF에서 확인하고 claims에 페이지까지 적습니다."
                : "A search built from the model and data selected here. Cite a number from the PDF, with a page, in claims."}
            </Hint>
          </h2>
        </div>
        <PaperLinks
          locale={locale}
          query={contextQuery({
            model: model?.paper,
            domains: [...trainSummary.domains, ...testSummary.domains],
            adaptation: adapting,
          })}
        />
      </section>

      <section className="card">
        <div className="section-heading">
          <h2>{locale === "ko" ? "저장된 초안" : "Saved drafts"}</h2>
        </div>
        <ol className="timeline-list">
          {recentDrafts.map((draft) => (
            <li key={draft.draftId}>
              <strong>{draft.experimentId}</strong>
              <span>{localeDate(locale, draft.updatedAt)}</span>
            </li>
          ))}
          {recentDrafts.length === 0 && (
            <li>{locale === "ko" ? "아직 저장 초안이 없습니다." : "No saved drafts yet."}</li>
          )}
        </ol>
        {!ControlStateSchema.safeParse(control).success && issues.length > 0 && (
          <div className="comparison-alert" role="status">
            <strong>{locale === "ko" ? "고칠 것" : "To fix"}</strong>
            <ul>
              {issues.slice(0, 5).map((issue) => (
                <li key={issue}>{issue}</li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </div>
  );
}

function StepHead({
  n,
  locale,
  ko,
  en,
  hintKo,
  hintEn,
}: {
  n: number;
  locale: Locale;
  ko: string;
  en: string;
  hintKo: string;
  hintEn: string;
}) {
  return (
    <div className="section-heading">
      <h2>
        <span className="step__n">{n}</span>
        {locale === "ko" ? ko : en}
        <Hint label={locale === "ko" ? "설명" : "More"}>{locale === "ko" ? hintKo : hintEn}</Hint>
      </h2>
    </div>
  );
}

function ModelPicker({
  modelId,
  locale,
  onPick,
}: {
  modelId: string;
  locale: Locale;
  onPick: (model: ModelEntry) => void;
}) {
  const current = modelById(modelId);
  const [group, setGroup] = useState(current?.group ?? "clip_3d");
  return (
    <div className="model-picker">
      <div className="chip-row" role="tablist" aria-label={locale === "ko" ? "모델 계열" : "Model kind"}>
        {MODEL_GROUP_ORDER.map((candidate) => (
          <button
            aria-selected={group === candidate}
            className={`chip${group === candidate ? " is-active" : ""}`}
            key={candidate}
            onClick={() => setGroup(candidate)}
            role="tab"
            type="button"
          >
            {MODEL_GROUP_LABELS[candidate][locale]}
          </button>
        ))}
      </div>
      <ul className="model-list">
        {modelsInGroup(group).map((model) => (
          <li key={model.id}>
            <div
              className={`model-card${modelId === model.id ? " is-active" : ""}`}
              onClick={(event) => {
                if (event.target instanceof Element && event.target.closest("button, a")) return;
                onPick(model);
              }}
            >
              <div className="model-card__head">
                <button
                  aria-pressed={modelId === model.id}
                  className="model-card__name"
                  onClick={() => onPick(model)}
                  type="button"
                >
                  {model.label}
                </button>
                <span className={`pill pill--${model.status}`}>
                  {model.status === "implemented"
                    ? locale === "ko"
                      ? "준비됨"
                      : "ready"
                    : locale === "ko"
                      ? "후보"
                      : "candidate"}
                </span>
              </div>
              <p className="model-card__why">{model.why[locale]}</p>
              <div className="model-card__facts">
                <span>
                  {model.frames === 1
                    ? locale === "ko"
                      ? "한 장"
                      : "1 frame"
                    : `${model.frames} ${locale === "ko" ? "프레임" : "frames"}`}
                </span>
                <span>{model.paramsM === null ? "—" : `${model.paramsM}M`}</span>
                <span>{model.library}</span>
                <span>{model.pretrain}</span>
                <PaperLinks compact locale={locale} query={`"${model.paper}"`} />
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function blockerText(locale: Locale, blocker: string): string {
  if (blocker.includes("data selection")) {
    return locale === "ko"
      ? "데이터 선택에 막힘 항목이 있습니다. 2단계의 빨간 줄을 먼저 해결하세요."
      : "The data selection has a blocking finding. Fix the red line in step 2 first.";
  }
  if (blocker.includes("research candidate")) {
    return locale === "ko"
      ? "이 모델은 아직 이 저장소에서 돌아가지 않습니다. 설정 초안은 저장할 수 있습니다."
      : "This model does not run in this repository yet. The config draft can still be saved.";
  }
  return locale === "ko" ? "설정값에 오류가 있습니다." : "Some values are invalid.";
}

// Safety copy contract: This UI does not launch training; YAML patch preview.
