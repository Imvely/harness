import { useState } from "react";
import type { CustomModel, HeadKind, Locale, ModelSpec, TemporalOp } from "../types";
import type { ModelEntry, ModelGroup } from "../data/modelCatalog";
import { MODEL_GROUP_LABELS, MODEL_GROUP_ORDER, modelsInGroup } from "../data/modelCatalog";
import {
  HEAD_KINDS,
  HEAD_LABELS,
  HEAD_WHY,
  SOURCE_LABELS,
  TEMPORAL_LABELS,
  TEMPORAL_OPS,
  TEMPORAL_WHY,
  asEntry,
  customFromRef,
  describeSpec,
  entryFor,
  scaffoldCommand,
  specId,
  specIssueText,
  specIssues,
} from "../db/modelStudio";
import type { HubModel } from "../db/modelSearch";
import {
  customLinks,
  framesFor,
  hubLinks,
  hubPage,
  hubSearchUrl,
  modelSearchLinks,
  parseHubModels,
  searchName,
  sourceFor,
} from "../db/modelSearch";
import { Field } from "./Field";
import { Hint } from "./Hint";
import { PaperLinkRow, PaperLinks } from "./PaperLinks";

/**
 * Three ways to answer "which model", because a study needs all three.
 *
 * *From the list* is the common case. *Composed* is the real work — a backbone with something on
 * top of it, which is how most PAD architectures differ from each other. *Found* is what keeps
 * the screen from going stale: search the hub, add what comes back, and it joins the list.
 *
 * Nothing here pretends a found model can run. A composition whose backbone has no adapter shows
 * the one command that creates one, so the gap is a next step rather than a dead end.
 */
export function ModelStudio({
  spec,
  custom,
  locale,
  onChange,
  onAddModel,
  onRemoveModel,
}: {
  spec: ModelSpec;
  custom: CustomModel[];
  locale: Locale;
  onChange: (spec: ModelSpec) => void;
  onAddModel: (model: CustomModel) => void;
  onRemoveModel: (id: string) => void;
}) {
  const [tab, setTab] = useState<"list" | "compose" | "find">("list");
  const issues = specIssues(spec, custom);
  const backbone = entryFor(spec.backboneId, custom);

  return (
    <div className="model-studio">
      <div className="chip-row" role="tablist" aria-label={locale === "ko" ? "모델 고르는 방법" : "How to choose"}>
        {(
          [
            ["list", locale === "ko" ? "목록에서 고르기" : "From the list"],
            ["compose", locale === "ko" ? "조합하기" : "Compose"],
            ["find", locale === "ko" ? "찾아서 추가" : "Find and add"],
          ] as const
        ).map(([id, label]) => (
          <button
            aria-selected={tab === id}
            className={`chip${tab === id ? " is-active" : ""}`}
            key={id}
            onClick={() => setTab(id)}
            role="tab"
            type="button"
          >
            {label}
          </button>
        ))}
      </div>

      <p className="spec-line">
        <strong>{describeSpec(spec, locale, custom)}</strong>
        <code>{specId(spec)}</code>
      </p>

      {issues.length > 0 && (
        <ul className="finding-list">
          {issues.map((issue) => (
            <li className={`finding finding--${issue.level}`} key={issue.code}>
              <span className="finding__tag">
                {issue.level === "blocking"
                  ? locale === "ko"
                    ? "막힘"
                    : "blocked"
                  : locale === "ko"
                    ? "주의"
                    : "note"}
              </span>
              {specIssueText(locale, issue)}
            </li>
          ))}
        </ul>
      )}

      {issues.some((issue) => issue.code === "no_adapter") && (
        <div className="scaffold">
          <p className="subtle">
            {locale === "ko" ? "이 조합으로 시작하는 명령" : "The command that starts this off"}
            <Hint align="start" label={locale === "ko" ? "무엇을 하나요" : "What it does"}>
              {locale === "ko"
                ? "이 조합의 config 파일을 만들고, 아직 없는 것(백본 로더, smoke test)을 목록으로 알려 줍니다. 그것들이 채워지고 검증을 통과하면 이 화면에서 '준비됨'이 됩니다."
                : "It writes the config for this composition and lists what is still missing (the backbone loader, a smoke test). Once those exist and validation passes, this reads as ready."}
            </Hint>
          </p>
          <pre>{scaffoldCommand(spec, custom)}</pre>
        </div>
      )}

      {tab === "list" && (
        <ModelList
          custom={custom}
          locale={locale}
          onPick={(entry) =>
            onChange({ ...spec, backboneId: entry.id, frames: Math.min(64, Math.max(1, entry.frames)) })
          }
          onRemove={onRemoveModel}
          selectedId={spec.backboneId}
        />
      )}

      {tab === "compose" && (
        <Composer backbone={backbone} custom={custom} locale={locale} onChange={onChange} spec={spec} />
      )}

      {tab === "find" && <Finder custom={custom} locale={locale} onAdd={onAddModel} />}
    </div>
  );
}

function ModelList({
  selectedId,
  custom,
  locale,
  onPick,
  onRemove,
}: {
  selectedId: string;
  custom: CustomModel[];
  locale: Locale;
  onPick: (entry: ModelEntry) => void;
  onRemove: (id: string) => void;
}) {
  const selected = entryFor(selectedId, custom);
  const [group, setGroup] = useState<ModelGroup>(selected?.group ?? "clip_3d");
  const entries = group === "custom" ? custom.map(asEntry) : modelsInGroup(group);
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
            {candidate === "custom" && custom.length > 0 && ` (${custom.length})`}
          </button>
        ))}
      </div>
      {entries.length === 0 && (
        <p className="subtle">
          {locale === "ko"
            ? "아직 추가한 모델이 없습니다. '찾아서 추가'에서 검색해 넣으세요."
            : "Nothing added yet. Search for one under 'Find and add'."}
        </p>
      )}
      <ul className="model-list">
        {entries.map((model) => (
          <li key={model.id}>
            <div
              className={`model-card${selectedId === model.id ? " is-active" : ""}`}
              onClick={(event) => {
                if (event.target instanceof Element && event.target.closest("button, a")) return;
                onPick(model);
              }}
            >
              <div className="model-card__head">
                <button
                  aria-pressed={selectedId === model.id}
                  className="model-card__name"
                  onClick={() => onPick(model)}
                  type="button"
                >
                  {model.label}
                </button>
                <span className={`pill pill--${model.status}`}>{statusWord(locale, model.status)}</span>
                {model.group === "custom" && (
                  <button className="link-button" onClick={() => onRemove(model.id)} type="button">
                    {locale === "ko" ? "목록에서 빼기" : "Remove"}
                  </button>
                )}
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
              </div>
              <EntryLinks
                entry={model}
                locale={locale}
                own={custom.find((candidate) => candidate.id === model.id)}
              />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Composer({
  spec,
  backbone,
  custom,
  locale,
  onChange,
}: {
  spec: ModelSpec;
  backbone: ModelEntry | undefined;
  custom: CustomModel[];
  locale: Locale;
  onChange: (spec: ModelSpec) => void;
}) {
  return (
    <div className="composer">
      <ol className="composer__chain">
        <li>
          <span className="composer__slot">{locale === "ko" ? "백본" : "Backbone"}</span>
          <select
            aria-label={locale === "ko" ? "백본" : "Backbone"}
            onChange={(event) => onChange({ ...spec, backboneId: event.target.value })}
            value={spec.backboneId}
          >
            {MODEL_GROUP_ORDER.map((group) => {
              const entries = group === "custom" ? custom.map(asEntry) : modelsInGroup(group);
              if (entries.length === 0) return null;
              return (
                <optgroup key={group} label={MODEL_GROUP_LABELS[group][locale]}>
                  {entries.map((entry) => (
                    <option key={entry.id} value={entry.id}>
                      {entry.label}
                      {entry.status === "implemented" ? " ✓" : ""}
                    </option>
                  ))}
                </optgroup>
              );
            })}
          </select>
          <span className="subtle">
            {backbone
              ? `${backbone.frames === 1 ? (locale === "ko" ? "한 장씩" : "one frame") : locale === "ko" ? "클립 단위" : "a clip"} · ${backbone.library}`
              : ""}
          </span>
        </li>
        <li>
          <span className="composer__slot">{locale === "ko" ? "시간 처리" : "Time"}</span>
          <select
            aria-label={locale === "ko" ? "시간 처리" : "Time"}
            onChange={(event) => onChange({ ...spec, temporal: event.target.value as TemporalOp })}
            value={spec.temporal}
          >
            {TEMPORAL_OPS.map((op) => (
              <option key={op} value={op}>
                {TEMPORAL_LABELS[op][locale]}
              </option>
            ))}
          </select>
          <span className="subtle">{TEMPORAL_WHY[spec.temporal][locale]}</span>
        </li>
        <li>
          <span className="composer__slot">{locale === "ko" ? "머리 (예측)" : "Head"}</span>
          <select
            aria-label={locale === "ko" ? "머리" : "Head"}
            onChange={(event) => onChange({ ...spec, head: event.target.value as HeadKind })}
            value={spec.head}
          >
            {HEAD_KINDS.map((head) => (
              <option key={head} value={head}>
                {HEAD_LABELS[head][locale]}
              </option>
            ))}
          </select>
          <span className="subtle">{HEAD_WHY[spec.head][locale]}</span>
        </li>
        <li>
          <span className="composer__slot">{locale === "ko" ? "프레임 수" : "Frames"}</span>
          <input
            aria-label={locale === "ko" ? "프레임 수" : "Frames"}
            max={16}
            min={1}
            onChange={(event) => onChange({ ...spec, frames: Number(event.target.value) })}
            type="number"
            value={spec.frames}
          />
          <span className="subtle">
            {locale === "ko"
              ? "3fps 그리드에서 8프레임은 약 2.7초입니다."
              : "On the 3 fps grid, 8 frames is about 2.7 seconds."}
          </span>
        </li>
      </ol>
    </div>
  );
}

function Finder({
  custom,
  locale,
  onAdd,
}: {
  custom: CustomModel[];
  locale: Locale;
  onAdd: (model: CustomModel) => void;
}) {
  const [query, setQuery] = useState("video anti-spoofing");
  const [videoOnly, setVideoOnly] = useState(true);
  const [state, setState] = useState<"idle" | "loading" | "done" | "failed">("idle");
  const [results, setResults] = useState<HubModel[]>([]);
  const [manualRef, setManualRef] = useState("");
  const [manualSource, setManualSource] = useState<CustomModel["source"]>("local");
  const [manualFrames, setManualFrames] = useState(8);
  const already = new Set(custom.map((model) => model.ref));

  const search = async () => {
    setState("loading");
    try {
      const response = await fetch(hubSearchUrl(query, { videoOnly }));
      if (!response.ok) throw new Error(String(response.status));
      setResults(parseHubModels(await response.json()));
      setState("done");
    } catch {
      setState("failed");
    }
  };

  return (
    <div className="finder">
      <div className="finder__search">
        <Field
          label={locale === "ko" ? "모델 검색" : "Search for a model"}
          hint={
            locale === "ko"
              ? "Hugging Face 허브를 검색합니다. 내려받기 수는 인기일 뿐이고 위조 탐지 성능과는 무관합니다 — 논문을 읽고 판단하세요."
              : "Searches the Hugging Face hub. Downloads mean popularity, not spoof detection; read the paper before believing anything."
          }
        >
          {(id) => (
            <input
              id={id}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") search();
              }}
              value={query}
            />
          )}
        </Field>
        <label className="check-field">
          <input checked={videoOnly} onChange={(event) => setVideoOnly(event.target.checked)} type="checkbox" />
          {locale === "ko" ? "영상 분류 모델만" : "Video models only"}
        </label>
        <button className="button button--primary button--small" onClick={search} type="button">
          {state === "loading" ? (locale === "ko" ? "찾는 중…" : "Searching…") : locale === "ko" ? "검색" : "Search"}
        </button>
      </div>

      {state === "failed" && (
        <p className="subtle">
          {locale === "ko"
            ? "허브를 불러올 수 없습니다(네트워크 또는 요청 제한). 아래에서 직접 등록할 수 있습니다."
            : "Could not reach the hub (network or rate limit). You can register one by hand below."}
        </p>
      )}
      {state === "done" && results.length === 0 && (
        <p className="subtle">{locale === "ko" ? "결과가 없습니다." : "No results."}</p>
      )}

      {results.length > 0 && (
        <ul className="hub-list">
          {results.map((model) => (
            <li className="hub-card" key={model.id}>
              <a className="hub-card__id" href={hubPage(model.id)} rel="noreferrer noopener" target="_blank">
                {model.id}
              </a>
              <dl className="hub-card__facts">
                {model.pipeline && (
                  <div>
                    <dt>{locale === "ko" ? "용도" : "Task"}</dt>
                    <dd>{model.pipeline}</dd>
                  </div>
                )}
                <div>
                  <dt>{locale === "ko" ? "내려받기" : "Downloads"}</dt>
                  <dd>{model.downloads === null ? "—" : model.downloads.toLocaleString()}</dd>
                </div>
                {model.tags.length > 0 && (
                  <div>
                    <dt>{locale === "ko" ? "태그" : "Tags"}</dt>
                    <dd>{model.tags.filter((tag) => !tag.startsWith("arxiv:")).slice(0, 5).join(", ")}</dd>
                  </div>
                )}
              </dl>
              <PaperLinkRow links={hubLinks(model)} locale={locale} />
              <details className="hub-card__search">
                <summary>{locale === "ko" ? "다른 곳에서 검색" : "Search elsewhere"}</summary>
                <p className="subtle">
                  {locale === "ko"
                    ? "아래는 이 모델 이름으로 검색하는 링크입니다. 그 사이트에 이 모델이 있다는 뜻은 아닙니다."
                    : "These search for this name. They do not mean the model is registered there."}
                </p>
                <PaperLinkRow links={modelSearchLinks(searchName(model.id))} locale={locale} />
              </details>
              <button
                className="button button--secondary button--small"
                disabled={already.has(model.id)}
                onClick={() =>
                  onAdd(
                    customFromRef(sourceFor(model), model.id, {
                      frames: framesFor(model),
                      note: model.arxivIds[0] ? `arXiv:${model.arxivIds[0]}` : (model.pipeline ?? ""),
                    }),
                  )
                }
                type="button"
              >
                {already.has(model.id)
                  ? locale === "ko"
                    ? "이미 추가됨"
                    : "already added"
                  : locale === "ko"
                    ? "목록에 추가"
                    : "Add to list"}
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="finder__manual">
        <p className="subtle">
          {locale === "ko" ? "직접 만든 모델 등록" : "Register a model of your own"}
          <Hint align="start" label={locale === "ko" ? "무엇을 적나요" : "What to enter"}>
            {locale === "ko"
              ? "이 저장소 안의 클래스면 src 기준 점 경로(pad_research.models.my_net.MyNet), 허브 모델이면 그 id를 적습니다."
              : "A class in this repository takes its dotted path (pad_research.models.my_net.MyNet); a hub model takes its id."}
          </Hint>
        </p>
        <div className="finder__manual-row">
          <select
            aria-label={locale === "ko" ? "출처" : "Source"}
            onChange={(event) => setManualSource(event.target.value as CustomModel["source"])}
            value={manualSource}
          >
            {(Object.keys(SOURCE_LABELS) as CustomModel["source"][]).map((source) => (
              <option key={source} value={source}>
                {SOURCE_LABELS[source]}
              </option>
            ))}
          </select>
          <input
            aria-label={locale === "ko" ? "모델 경로 또는 id" : "Path or hub id"}
            onChange={(event) => setManualRef(event.target.value)}
            placeholder={
              manualSource === "local" ? "pad_research.models.my_net.MyNet" : "owner/model-name"
            }
            value={manualRef}
          />
          <input
            aria-label={locale === "ko" ? "프레임 수" : "Frames"}
            max={64}
            min={1}
            onChange={(event) => setManualFrames(Number(event.target.value))}
            type="number"
            value={manualFrames}
          />
          <button
            className="button button--secondary button--small"
            disabled={manualRef.trim().length === 0}
            onClick={() => {
              onAdd(customFromRef(manualSource, manualRef, { frames: manualFrames, note: "added by hand" }));
              setManualRef("");
            }}
            type="button"
          >
            {locale === "ko" ? "등록" : "Register"}
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Links for one list entry: a page when there is one, a search only when a title makes it useful.
 *
 * A catalogue entry names a paper, so searching for that exact title finds it. A model somebody
 * registered has a hub page or nothing at all — a class in this repository is not on arXiv, and a
 * button that searches for `MyNet` only wastes a click.
 */
function EntryLinks({
  entry,
  own,
  locale,
}: {
  entry: ModelEntry;
  own: CustomModel | undefined;
  locale: Locale;
}) {
  if (own) {
    const links = customLinks(own);
    if (links.length === 0) return null;
    return <PaperLinkRow links={links} locale={locale} />;
  }
  return <PaperLinks compact locale={locale} query={`"${entry.paper}"`} />;
}

function statusWord(locale: Locale, status: ModelEntry["status"]): string {
  if (status === "implemented") return locale === "ko" ? "준비됨" : "ready";
  if (status === "user_added") return locale === "ko" ? "내가 추가" : "added here";
  return locale === "ko" ? "후보" : "candidate";
}
