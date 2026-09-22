import { useState } from "react";
import type { Locale, StorageDraft, StorageKind } from "../types";
import {
  storageCheckCommand,
  storageExportLines,
  storageProblems,
  storageRunCommand,
  storageYaml,
} from "../db/storagePreview";
import { Term } from "./Glossary";
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
      en: "The dataset is packed into one .lmdb directory or .mdb file.",
      ko: "데이터셋이 .lmdb 디렉터리나 .mdb 파일 하나로 묶여 있을 때.",
    },
  },
  {
    kind: "local",
    glyph: "▭",
    title: { en: "Folder", ko: "폴더" },
    when: {
      en: "Files on a disk this machine can already see — including an NFS, SMB or sshfs mount.",
      ko: "이 컴퓨터가 이미 볼 수 있는 디스크의 파일 — NFS·SMB·sshfs 마운트 포함.",
    },
  },
  {
    kind: "sftp",
    glyph: "⇅",
    title: { en: "SSH (SFTP)", ko: "SSH (SFTP)" },
    when: {
      en: "The data is only on another machine and you cannot mount it. Slower; prefer a mount.",
      ko: "데이터가 다른 서버에만 있고 마운트할 수 없을 때. 느립니다 — 가능하면 마운트를 쓰세요.",
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
          <p className="eyebrow">{ko ? "1단계" : "Step 1"}</p>
          <h2>{ko ? "데이터가 어디에 있나요?" : "Where is the data?"}</h2>
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
        <p className="subtle">
          {ko
            ? "이 선택은 실험의 과학적 내용이 아닙니다. storage 블록은 "
            : "This choice is not part of the experiment's science. The storage block is excluded from "}
          <Term id="science-hash" locale={locale}>
            science_hash
          </Term>
          {ko
            ? "에서 제외되므로, 세 사람이 서로 다른 방식으로 읽어도 결과를 그대로 비교할 수 있습니다."
            : ", so three people reading three different ways still produce directly comparable runs."}
        </p>
      </section>

      <section className="card card--wide">
        <div className="section-heading">
          <p className="eyebrow">{ko ? "2단계" : "Step 2"}</p>
          <h2>{ko ? "셸에서 값을 알려주세요" : "Tell your shell where it is"}</h2>
        </div>
        <p className="subtle">
          {ko
            ? "경로와 호스트는 환경변수 이름으로만 설정에 적습니다. configs/와 고정된 spec은 커밋되기 때문에, 실제 값이 들어가면 머신 경로가 git 기록에 남고(계약 §34) 그 spec은 다음 사람의 컴퓨터에서 쓸 수 없게 됩니다."
            : "Paths and hosts are named in the config, never written into it. configs/ and the frozen spec are committed, so a literal value would put a machine path in git history (contract §34) and make the spec unusable on the next person's machine."}
        </p>
        <div className="control-grid">{fields(draft, set, locale)}</div>
        <pre className="command-card__code">{storageExportLines(draft)}</pre>
        <p className="subtle">
          {ko
            ? "위 값은 예시 모양입니다. 실제 경로로 바꿔서 실행할 셸에 붙여 넣으세요."
            : "The values above show the shape only. Replace them with your real path in the shell you launch from."}
        </p>
      </section>

      <section className="command-card">
        <div className="section-heading">
          <p className="eyebrow">{ko ? "3단계" : "Step 3"}</p>
          <h2>{ko ? "읽히는지 먼저 확인" : "Prove it can be read"}</h2>
        </div>
        <p className="subtle subtle--inverse">
          {ko
            ? "이 화면은 명령문을 만들어 보여줄 뿐 실행하지 않습니다. 아래를 직접 실행하면 백엔드 연결, manifest, 실제 샘플 읽기를 차례로 확인하고 처음 실패한 곳에서 멈춥니다."
            : "This screen composes commands and never runs them. Run this yourself: it checks the backend, the manifest and a real sample in that order, and stops at the first failure."}
        </p>
        <label className="field field--inline">
          <span>{ko ? "확인할 데이터셋 (선택)" : "Dataset to prove (optional)"}</span>
          <input
            onChange={(event) => set({ datasetId: event.target.value })}
            placeholder="oulu_npu"
            value={draft.datasetId}
          />
        </label>
        <pre>{storageCheckCommand(draft)}</pre>
        <p className="subtle subtle--inverse">
          {ko
            ? "데이터셋을 비워 두면 백엔드에 닿는지만 확인합니다. 그것은 '데이터를 읽을 수 있다'보다 약한 결론입니다."
            : "With no dataset it only checks that the backend is reachable, which is weaker than proving the data is readable."}
        </p>
        <div className="command-actions">
          <button
            className="button button--secondary"
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
          <p className="eyebrow">{ko ? "그다음" : "Then"}</p>
          <h2>{ko ? "실험에 적용하기" : "Use it in a run"}</h2>
        </div>
        <p className="subtle">
          {ko
            ? "실험 파일을 고칠 필요가 없습니다. storage는 CLI에서 바꿔도 되는 몇 안 되는 값입니다 — science_hash에 들어가지 않기 때문입니다."
            : "No experiment file needs editing. storage is one of the few values the CLI may set, precisely because it does not enter science_hash."}
        </p>
        <pre className="command-card__code">
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
          <p className="eyebrow">{ko ? "선택" : "Optional"}</p>
          <h2>{ko ? "이 설정을 파일로 두기" : "Keep this as a named config"}</h2>
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
      <label className="field">
        <span>{ko ? "폴더를 가리키는 변수" : "Variable naming the folder"}</span>
        <input
          onChange={(event) => set({ rootEnvVar: event.target.value })}
          value={draft.rootEnvVar}
        />
        <small>
          {ko
            ? "manifest의 relative_path가 이 폴더를 기준으로 합니다."
            : "The manifest's relative_path values are relative to this folder."}
        </small>
      </label>
    );
  }
  if (draft.kind === "lmdb") {
    return (
      <>
        <label className="field">
          <span>{ko ? "스토어를 가리키는 변수" : "Variable naming the store"}</span>
          <input
            onChange={(event) => set({ lmdbPathEnvVar: event.target.value })}
            value={draft.lmdbPathEnvVar}
          />
        </label>
        <label className="field">
          <span>{ko ? "키 접두사 (보통 비움)" : "Key prefix (usually empty)"}</span>
          <input
            onChange={(event) => set({ keyPrefix: event.target.value })}
            placeholder="oulu_npu/"
            value={draft.keyPrefix}
          />
          <small>
            {/* The one LMDB mistake worth pre-empting on screen: everything looks configured,
                every read misses, and the symptom is thousands of identical not-found errors. */}
            {ko
              ? "manifest의 relative_path가 곧 키입니다. 스토어를 만들 때 붙인 접두사가 manifest에 없다면 여기에 적으세요 — 3단계가 바로 이 불일치를 짚어 줍니다."
              : "The manifest's relative_path IS the key. If the store was built with a prefix the manifest does not carry, put it here — step 3 names exactly this mismatch."}
          </small>
        </label>
        <label className="field">
          <span>{ko ? "키 접미사" : "Key suffix"}</span>
          <input
            onChange={(event) => set({ keySuffix: event.target.value })}
            placeholder=".jpg"
            value={draft.keySuffix}
          />
        </label>
        <label className="field">
          <span>{ko ? "프레임 키 구분자" : "Frame key separator"}</span>
          <input
            onChange={(event) => set({ childSeparator: event.target.value })}
            placeholder="#"
            value={draft.childSeparator}
          />
          <small>
            {ko
              ? "clip 키와 프레임 번호 사이의 문자입니다. 연구실 LMDB는 clip#00012 형태라 #입니다. clip/00012 형태면 /로 바꾸세요."
              : "The character between a clip's key and its frame number. The lab's stores use clip#00012, so #. Use / for clip/00012."}
          </small>
        </label>
        <label className="check-field">
          <input
            checked={draft.lmdbLock}
            onChange={(event) => set({ lmdbLock: event.target.checked })}
            type="checkbox"
          />
          <span>
            {ko
              ? "아직 스토어를 쓰는 중입니다 (lock)"
              : "Something is still writing this store (lock)"}
          </span>
        </label>
      </>
    );
  }
  return (
    <>
      <label className="field">
        <span>{ko ? "호스트 변수" : "Host variable"}</span>
        <input
          onChange={(event) => set({ sftpHostEnvVar: event.target.value })}
          value={draft.sftpHostEnvVar}
        />
      </label>
      <label className="field">
        <span>{ko ? "원격 폴더 변수" : "Remote folder variable"}</span>
        <input
          onChange={(event) => set({ sftpRootEnvVar: event.target.value })}
          value={draft.sftpRootEnvVar}
        />
      </label>
      <label className="field">
        <span>{ko ? "계정 변수" : "Username variable"}</span>
        <input
          onChange={(event) => set({ sftpUserEnvVar: event.target.value })}
          value={draft.sftpUserEnvVar}
        />
      </label>
      <label className="field">
        <span>{ko ? "비밀번호 변수 이름 (비우면 ssh-agent 키)" : "Password variable NAME (empty = ssh-agent key)"}</span>
        <input
          onChange={(event) => set({ sftpPasswordEnvVar: event.target.value })}
          placeholder="PAD_SFTP_PASSWORD"
          value={draft.sftpPasswordEnvVar}
        />
        <small>
          {ko
            ? "비밀번호 자체는 어디에도 적지 않습니다. 비워 두고 ssh-agent 키를 쓰는 쪽이 가장 안전합니다."
            : "The password itself is never written anywhere. Leaving this empty and using an ssh-agent key is the safest route."}
        </small>
      </label>
    </>
  );
}
