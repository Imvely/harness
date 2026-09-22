import { useMemo, useState } from "react";
import type {
  AdaptationMethod,
  ControlState,
  DemoRun,
  Locale,
  ModelFamily,
  MockDatabaseState,
} from "../types";
import { buildLaunchCommand, buildValidationCommand, buildYamlPatch } from "../db/controlPreview";
import { ControlStateSchema } from "../db/schema";
import { validateControlState } from "../db/mockDb";
import { localeDate, t } from "../i18n";
import { SelectBox } from "./FilterPanel";
import { Hint } from "./Hint";

type ControlActionResult = {
  ok: boolean;
  message: string;
  issues: string[];
};

export const initialControl: ControlState = {
  experimentId: "exp_ui_spoof_preserve_lab",
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
  const commandIsCopyable = ControlStateSchema.safeParse(control).success;
  const sourceRunIds = useMemo(
    () => sourceRuns.slice(0, 30).map((run) => run.runId),
    [sourceRuns],
  );
  const recentDrafts = database.drafts.slice(0, 4);

  const runAction = (action: () => ControlActionResult) => {
    const result = action();
    setActionMessage(result);
  };

  const copyCommand = async () => {
    if (!commandIsCopyable) {
      setActionMessage({
        ok: false,
        message: locale === "ko" ? "검증 오류를 먼저 고치세요." : "Fix validation errors first.",
        issues,
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

  return (
    <div className="page-grid page-grid--control">
      <section className="card card--wide">
        <div className="section-heading section-heading--row">
          <h2>
            {locale === "ko" ? "실험 설정 초안" : "Experiment draft"}
            <Hint label={locale === "ko" ? "이 화면이 하는 일" : "What this screen does"}>
              {locale === "ko"
                ? "This UI does not launch training. 여기서 하는 일은 초안 저장과 명령 미리보기뿐이고, 실제 실행은 터미널에서 검증 절차를 거쳐야 합니다."
                : "This UI does not launch training. It only saves drafts and previews commands; a real run goes through the validation procedure in a terminal."}
            </Hint>
          </h2>
          <span className="subtle">{locale === "ko" ? "학습은 시작하지 않습니다" : "Does not start training"}</span>
        </div>
        <div className="control-grid">
          <label className="field field--inline">
            {t(locale, "experimentId")}
            <input
              value={control.experimentId}
              onChange={(event) => onChange({ ...control, experimentId: event.target.value })}
              placeholder="exp_ui_spoof_preserve_lab"
            />
          </label>
          <SelectBox label={t(locale, "modelFamily")} value={control.modelFamily} values={["frame_baseline", "video_baseline"]} onChange={(value) => onChange({ ...control, modelFamily: value as ModelFamily })} />
          <NumberField label={locale === "ko" ? "프레임" : "Frames"} value={control.frames} min={1} max={16} onChange={(value) => onChange({ ...control, frames: value })} />
          <NumberField label={locale === "ko" ? "배치 크기" : "Batch size"} value={control.batchSize} min={1} max={64} onChange={(value) => onChange({ ...control, batchSize: value })} />
          <NumberField label={locale === "ko" ? "에폭" : "Epochs"} value={control.epochs} min={1} max={control.smokeMode ? 1 : 20} onChange={(value) => onChange({ ...control, epochs: value })} />
          <label className="field field--inline">
            {locale === "ko" ? "학습률" : "Learning rate"}
            <input value={control.learningRate} onChange={(event) => onChange({ ...control, learningRate: event.target.value })} />
          </label>
          <SelectBox label={t(locale, "adaptation")} value={control.adaptationMethod} values={["none", "full_finetune", "head_only", "prototype", "spoof_preserve"]} onChange={(value) => onChange({ ...control, adaptationMethod: value as AdaptationMethod })} />
          {sourceRunIds.length > 0 ? (
            <SelectBox label={t(locale, "sourceRunId")} value={control.sourceRunId} values={sourceRunIds} onChange={(value) => onChange({ ...control, sourceRunId: value })} />
          ) : (
            <label className="field field--inline">
              {t(locale, "sourceRunId")}
              <input value={control.sourceRunId} onChange={(event) => onChange({ ...control, sourceRunId: event.target.value })} />
            </label>
          )}
          <SelectBox label={t(locale, "protocol")} value={control.protocolId} values={["syn_a_to_b_bf_adapt_v1", "syn_a_to_b_v1"]} onChange={(value) => onChange({ ...control, protocolId: value })} />
          <SelectBox label={t(locale, "thresholdRule")} value={control.thresholdRule} values={["eer", "bpcer_at_apcer"]} onChange={(value) => onChange({ ...control, thresholdRule: value as ControlState["thresholdRule"] })} />
          <NumberField label={t(locale, "seed")} value={control.seed} min={1} max={999} onChange={(value) => onChange({ ...control, seed: value })} />
          <label className="check-field check-field--large">
            <input
              checked={control.smokeMode}
              onChange={(event) => onChange({ ...control, smokeMode: event.target.checked, epochs: event.target.checked ? 1 : control.epochs })}
              type="checkbox"
            />
            {locale === "ko" ? "스모크 모드 미리보기" : "Smoke mode preview"}
          </label>
        </div>
        <div className="button-row">
          <button className="button button--secondary" onClick={() => setActionMessage({ ok: issues.length === 0, message: issues.length === 0 ? (locale === "ko" ? "제어 값이 계약 검증을 통과했습니다." : "Control values passed contract validation.") : (locale === "ko" ? "저장 전에 제어 경고를 검토하세요." : "Review control warnings before saving."), issues })} type="button">
            {t(locale, "validateControls")}
          </button>
          <button className="button button--secondary" onClick={() => runAction(onSaveDraft)} type="button">
            {t(locale, "saveDraft")}
          </button>
        </div>
        {actionMessage && (
          <div className={actionMessage.ok ? "action-message action-message--ok" : "action-message action-message--warn"} role="status">
            <strong>{actionMessage.message}</strong>
            {actionMessage.issues.length > 0 && (
              <ul>
                {actionMessage.issues.map((issue) => (
                  <li key={issue}>{issue}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>
      <section className="command-card">
        <div className="section-heading">
          <h2>
            {locale === "ko" ? "실행 명령 (검증 후 복사)" : "Launch command (copy after validation)"}
            <Hint label={locale === "ko" ? "명령 설명" : "About the command"}>
              {locale === "ko"
                ? "첫 줄은 설정 검증, 둘째 줄은 실행입니다. 학습값은 명령행으로 넘기지 않으니, 검토 후 configs/exp/*.yaml에 반영하세요."
                : "The first line validates, the second launches. Training values are not passed on the command line; put them in configs/exp/*.yaml after review."}
            </Hint>
          </h2>
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
        </div>
      </section>
      <section className="card card--wide">
        <div className="section-heading">
          <h2>
            {t(locale, "configPatchPreview")}
            <Hint label={locale === "ko" ? "YAML 미리보기 설명" : "About the YAML preview"}>
              {locale === "ko"
                ? "configs/exp/*.yaml에 들어갈 내용 미리보기입니다. 파일은 직접 검토한 뒤 고치세요."
                : "What configs/exp/*.yaml would contain. Review it, then edit the file yourself."}
            </Hint>
          </h2>
        </div>
        <pre className="yaml-preview">{yamlPatch}</pre>
        {issues.length > 0 && (
          <div className="comparison-alert" role="status">
            <strong>Validation notes</strong>
            <ul>
              {issues.map((issue) => (
                <li key={issue}>{issue}</li>
              ))}
            </ul>
          </div>
        )}
      </section>
      <section className="card">
        <div className="section-heading">
          <h2>{locale === "ko" ? "저장된 초안" : "Saved drafts"}</h2>
        </div>
        <div className="mini-metrics mini-metrics--stacked">
          <div>
            <span>{locale === "ko" ? "저장 초안" : "Saved drafts"}</span>
            <strong>{database.drafts.length}</strong>
          </div>
        </div>
        <section className="note-panel">
          <h3>{t(locale, "recentDrafts")}</h3>
          <ol className="timeline-list">
            {recentDrafts.map((draft) => (
              <li key={draft.draftId}>
                <strong>{draft.experimentId}</strong>
                <span>{localeDate(locale, draft.updatedAt)}</span>
              </li>
            ))}
            {recentDrafts.length === 0 && <li>{locale === "ko" ? "아직 저장 초안이 없습니다." : "No saved drafts yet."}</li>}
          </ol>
        </section>
      </section>
      <section className="card">
        <div className="section-heading">
          <h2>{t(locale, "launchGuardrails")}</h2>
        </div>
        <ul className="guardrail-list">
          <li>{locale === "ko" ? "`execution.*` 변경은 `configs/exp/*.yaml`에만 둡니다." : "`execution.*` changes belong in `configs/exp/*.yaml` only."}</li>
          <li>{locale === "ko" ? "CLI는 `execution.mode`를 smoke로 낮추는 것만 허용합니다." : "CLI can only demote `execution.mode` to smoke."}</li>
          {/* Both of these were a ko/en ternary whose two branches held the same English
              sentence — the shape of a translation without the translation. */}
          <li>{locale === "ko" ? "스모크 한도는 max_batches ≤ 20, max_epochs = 1 안에 있어야 합니다." : "Smoke limits must stay within max_batches ≤ 20 and max_epochs = 1."}</li>
          <li>{locale === "ko" ? "전체 GPU 실행에는 사람의 승인 토큰과 게이트 근거가 필요합니다." : "Full GPU runs need human approval and gate evidence."}</li>
        </ul>
      </section>
    </div>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="field field--inline">
      {label}
      <input
        min={min}
        max={max}
        type="number"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

// Safety copy contract: This UI does not launch training; YAML patch preview.
