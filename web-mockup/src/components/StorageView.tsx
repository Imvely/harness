import { useState } from "react";
import type { Locale, StorageDraft, StorageKind } from "../types";
import {
  storageCheckCommand,
  storageExportLines,
  storageProblems,
  storageRunCommand,
  storageYaml,
} from "../db/storagePreview";
import { Field } from "./Field";
import { Hint } from "./Hint";
import { t } from "../i18n";

/**
 * "My data is over there. How do I point the harness at it?"
 *
 * Three facts shape this screen. The first is that the answer is never one thing: one person
 * has an LMDB, another a directory, a third a server behind SSH, and the harness reads all
 * three (ADR-010). The second is that the screen cannot do it for them — ADR-006 lets this
 * dashboard exist because it reads a static file and runs nothing — so what it can do is
 * compose the exact text to paste, and say plainly that it is not running it.
 *
 * The third is the reason the first two are worth the effort: the choice does not change the
 * experiment. Storage is excluded from `science_hash`, so three people connecting three
 * different ways still produce runs that compare directly. That sentence is on screen, because
 * a researcher's first worry about "just point it somewhere else" is exactly whether their
 * numbers still mean the same thing.
 *
 * The layout is three steps rather than one form. A form with every backend's fields visible
 * asks the reader to work out which half applies to them; a step asks one question at a time.
 */

export const initialStorage: StorageDraft = {
  kind: "lmdb",
  rootEnvVar: "PAD_DATA_ROOT",
  lmdbPathEnvVar: "PAD_LMDB_PATH",
  keyPrefix: "",
  keySuffix: "",
  // The lab's video stores key frames as <video_id>#<index>; see configs/storage/lmdb.yaml.
  childSeparator: "#",
  lmdbLock: false,
  sftpHostEnvVar: "PAD_SFTP_HOST",
  sftpRootEnvVar: "PAD_SFTP_ROOT",
  sftpUserEnvVar: "PAD_SFTP_USER",
  sftpPasswordEnvVar: "",
  datasetId: "",
};

type KindCard = {
  kind: StorageKind;
  glyph: string;
  title: Record<Locale, string>;
  when: Record<Locale, string>;
};

/** Each card says what the backend IS and, more usefully, when it is the right one. */
const KIND_CARDS: KindCard[] = [
  {
    kind: "lmdb",
    glyph: "▤",
    title: { en: "LMDB store", ko: "LMDB 스토어" },
    when: {
      en: "Packed into one .lmdb folder or .mdb file",
      ko: ".lmdb 폴더나 .mdb 파일 하나로 묶여 있음",
    },
  },
  {
    kind: "local",
    glyph: "▭",
    title: { en: "Folder", ko: "폴더" },
    when: {
      en: "Files this computer can open, mounts included",
      ko: "이 컴퓨터에서 열리는 폴더 (마운트 포함)",
    },
  },
  {
    kind: "sftp",
    glyph: "⇅",
    title: { en: "SSH (SFTP)", ko: "SSH (SFTP)" },
    when: {
      en: "Only on another server, and it cannot be mounted",
      ko: "다른 서버에만 있고 마운트할 수 없음",
    },
  },
];

export function StorageView({
  draft,
  locale = "en",
  onChange,
}: {
  draft: StorageDraft;
  locale?: Locale;
  onChange: (next: StorageDraft) => void;
}) {
  const [showYaml, setShowYaml] = useState(false);
  const ko = locale === "ko";
  const problems = storageProblems(draft, ko ? "ko" : "en");
  const set = (patch: Partial<StorageDraft>) => onChange({ ...draft, ...patch });

  return (
    <div className="page-grid page-grid--storage">
      <section className="card card--wide">
        <div className="section-heading">
          <h2>
            <span className="step-number">1</span>
            {ko ? "데이터가 어디에 있나요?" : "Where is the data?"}
            <Hint label={ko ? "방식을 골라도 결과가 같은 이유" : "Why the choice does not change results"}>
              {ko
                ? "저장 방식은 실험의 과학적 내용이 아닙니다. storage 블록은 science_hash에서 제외되므로, 서로 다른 방식으로 읽어도 결과를 그대로 비교할 수 있습니다."
                : "Storage is not part of the experiment's science. The storage block is excluded from science_hash, so runs read three different ways still compare directly."}
            </Hint>
          </h2>
        </div>
        <div className="storage-kinds" role="radiogroup" aria-label={ko ? "저장 방식" : "Storage kind"}>
          {KIND_CARDS.map((card) => (
            <button
              aria-checked={draft.kind === card.kind}
              className={
                draft.kind === card.kind ? "storage-kind storage-kind--active" : "storage-kind"
              }
              key={card.kind}
              onClick={() => set({ kind: card.kind })}
              role="radio"
              type="button"
            >
              <span className="storage-kind__glyph" aria-hidden="true">
                {card.glyph}
              </span>
              <span className="storage-kind__title">{card.title[locale]}</span>
              <span className="storage-kind__when">{card.when[locale]}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="card card--wide">
        <div className="section-heading">
          <h2>
            <span className="step-number">2</span>
            {ko ? "셸에 위치 알려주기" : "Tell your shell where it is"}
            <Hint label={ko ? "왜 변수 이름만 적나요" : "Why only variable names"}>
              {ko
                ? "경로와 호스트는 환경변수 이름으로만 적습니다. 설정 파일은 git에 올라가므로, 실제 경로를 적으면 기록에 남고(계약 §34) 다른 사람 컴퓨터에서 쓸 수 없게 됩니다. 아래 export 값은 모양만 보여 주는 예시입니다."
                : "Paths and hosts are named, never written: config files are committed, so a literal path would land in git history (contract §34) and break on the next machine. The export values below only show the shape."}
            </Hint>
          </h2>
        </div>
        <div className="control-grid">{fields(draft, set, locale)}</div>
        <pre className="code-block code-block--light">{storageExportLines(draft)}</pre>
      </section>

      <section className="card card--wide">
        <div className="section-heading">
          <h2>
            <span className="step-number">3</span>
            {ko ? "읽히는지 확인" : "Prove it can be read"}
            <Hint label={ko ? "확인 명령이 하는 일" : "What the check does"}>
              {ko
                ? "직접 실행하면 저장소 연결 → manifest → 실제 샘플 읽기 순서로 확인하고, 처음 실패한 곳에서 멈춥니다. 데이터셋을 비우면 연결만 확인합니다."
                : "Run it yourself: it checks the backend, then the manifest, then a real sample, and stops at the first failure. With no dataset it only checks the connection."}
            </Hint>
          </h2>
          <span className="subtle">{ko ? "이 화면은 명령문만 만들고 실행하지 않습니다." : "This screen writes the command; it does not run it."}</span>
        </div>
        <Field label={ko ? "확인할 데이터셋 (선택)" : "Dataset to check (optional)"}>
          {(id) => (
            <input
              id={id}
              onChange={(event) => set({ datasetId: event.target.value })}
              placeholder="oulu_npu"
              value={draft.datasetId}
            />
          )}
        </Field>
        <pre className="code-block">{storageCheckCommand(draft)}</pre>
        <div className="command-actions">
          <button
            className="button button--primary"
            onClick={() => void navigator.clipboard?.writeText(storageCheckCommand(draft))}
            type="button"
          >
            {t(locale, "copyCommand")}
          </button>
        </div>
      </section>

      {/* Wide, not a half-column card: a launch command is one long line, and a reader who has
          to scroll sideways to see the end of it cannot check the end of it. */}
      <section className="card card--wide">
        <div className="section-heading">
          <h2>
            <span className="step-number">4</span>
            {ko ? "실험에 적용" : "Use it in a run"}
            <Hint label={ko ? "실험 파일을 안 고쳐도 되는 이유" : "Why no file edit is needed"}>
              {ko
                ? "storage는 명령행에서 바꿔도 되는 몇 안 되는 값입니다. science_hash에 들어가지 않기 때문입니다."
                : "storage is one of the few values the command line may set, because it does not enter science_hash."}
            </Hint>
          </h2>
        </div>
        <pre className="code-block code-block--light">
          {storageRunCommand(draft, "syn_e02_video_source_only")}
        </pre>
        {problems.length > 0 && (
          <div className="comparison-alert" role="status">
            <strong>{ko ? "확인할 점" : "Worth knowing"}</strong>
            <ul>
              {problems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="card card--wide">
        <div className="section-heading">
          <h2>{ko ? "설정 파일로 저장하기 (선택)" : "Save as a config file (optional)"}</h2>
        </div>
        <button
          aria-expanded={showYaml}
          className="button button--secondary"
          onClick={() => setShowYaml((open) => !open)}
          type="button"
        >
          {showYaml ? (ko ? "YAML 접기" : "Hide YAML") : ko ? "YAML 보기" : "Show YAML"}
        </button>
        {showYaml && <pre className="yaml-preview">{storageYaml(draft)}</pre>}
      </section>
    </div>
  );
}

/** Only the chosen backend's fields are rendered; the others would be noise to read past. */
function fields(
  draft: StorageDraft,
  set: (patch: Partial<StorageDraft>) => void,
  locale: Locale,
) {
  const ko = locale === "ko";
  if (draft.kind === "local") {
    return (
      <Field
        hint={ko ? "manifest의 relative_path가 이 폴더를 기준으로 합니다." : "The manifest's relative_path values are relative to this folder."}
        label={ko ? "폴더 변수" : "Folder variable"}
      >
        {(id) => <input id={id} onChange={(event) => set({ rootEnvVar: event.target.value })} value={draft.rootEnvVar} />}
      </Field>
    );
  }
  if (draft.kind === "lmdb") {
    return (
      <>
        <Field label={ko ? "스토어 변수" : "Store variable"}>
          {(id) => (
            <input id={id} onChange={(event) => set({ lmdbPathEnvVar: event.target.value })} value={draft.lmdbPathEnvVar} />
          )}
        </Field>
        <Field
          // The one LMDB mistake worth pre-empting: everything looks configured, every read
          // misses, and the symptom is thousands of identical not-found errors.
          hint={
            ko
              ? "manifest의 relative_path가 곧 키입니다. 스토어를 만들 때 붙인 접두사가 manifest에 없을 때만 적으세요. 3단계가 이 불일치를 짚어 줍니다."
              : "The manifest's relative_path IS the key. Fill this only if the store was built with a prefix the manifest lacks; step 3 names that mismatch."
          }
          label={ko ? "키 접두사 (보통 비움)" : "Key prefix (usually empty)"}
        >
          {(id) => (
            <input id={id} onChange={(event) => set({ keyPrefix: event.target.value })} placeholder="oulu_npu/" value={draft.keyPrefix} />
          )}
        </Field>
        <Field label={ko ? "키 접미사" : "Key suffix"}>
          {(id) => (
            <input id={id} onChange={(event) => set({ keySuffix: event.target.value })} placeholder=".jpg" value={draft.keySuffix} />
          )}
        </Field>
        <Field
          hint={
            ko
              ? "clip 키와 프레임 번호 사이의 문자입니다. 연구실 LMDB는 clip#00012 형태라 #입니다. clip/00012 형태면 /로 바꾸세요."
              : "The character between a clip's key and its frame number. The lab's stores use clip#00012, so #. Use / for clip/00012."
          }
          label={ko ? "프레임 키 구분자" : "Frame key separator"}
        >
          {(id) => (
            <input id={id} onChange={(event) => set({ childSeparator: event.target.value })} placeholder="#" value={draft.childSeparator} />
          )}
        </Field>
        <label className="check-field">
          <input checked={draft.lmdbLock} onChange={(event) => set({ lmdbLock: event.target.checked })} type="checkbox" />
          <span>{ko ? "아직 스토어를 쓰는 중 (lock)" : "Still being written (lock)"}</span>
        </label>
      </>
    );
  }
  return (
    <>
      <Field label={ko ? "호스트 변수" : "Host variable"}>
        {(id) => <input id={id} onChange={(event) => set({ sftpHostEnvVar: event.target.value })} value={draft.sftpHostEnvVar} />}
      </Field>
      <Field label={ko ? "원격 폴더 변수" : "Remote folder variable"}>
        {(id) => <input id={id} onChange={(event) => set({ sftpRootEnvVar: event.target.value })} value={draft.sftpRootEnvVar} />}
      </Field>
      <Field label={ko ? "계정 변수" : "Username variable"}>
        {(id) => <input id={id} onChange={(event) => set({ sftpUserEnvVar: event.target.value })} value={draft.sftpUserEnvVar} />}
      </Field>
      <Field
        hint={
          ko
            ? "비밀번호 자체는 어디에도 적지 않습니다. 비워 두고 ssh-agent 키를 쓰는 쪽이 가장 안전합니다."
            : "The password itself is never written anywhere. Leaving this empty and using an ssh-agent key is safest."
        }
        label={ko ? "비밀번호 변수 이름 (선택)" : "Password variable NAME (optional)"}
      >
        {(id) => (
          <input
            id={id}
            onChange={(event) => set({ sftpPasswordEnvVar: event.target.value })}
            placeholder="PAD_SFTP_PASSWORD"
            value={draft.sftpPasswordEnvVar}
          />
        )}
      </Field>
    </>
  );
}
