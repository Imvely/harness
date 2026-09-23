import type { StorageDraft, StorageKind } from "../types";

/**
 * Turn a storage choice into the exact text a person has to run.
 *
 * Kept apart from the view, and pure, for two reasons. It is the part that can be wrong in a
 * way nobody notices — an `export` line naming a variable the Python side does not read is
 * indistinguishable on screen from a correct one — so it is the part worth testing. And the
 * screen must only ever *compose*: ADR-006 allows this dashboard to exist precisely because it
 * reads static data and runs nothing, so every command here is text to copy.
 *
 * The variable names below mirror `configs/storage/*.yaml`. A test asserts they still match,
 * because the failure mode otherwise is silent: the UI keeps printing an old name long after
 * the config was renamed, and the person following it gets "environment variable not set".
 */

/** Variables the chosen backend reads, in the order to set them. */
export function storageEnvVars(draft: StorageDraft): string[] {
  if (draft.kind === "local") return [draft.rootEnvVar];
  if (draft.kind === "lmdb") return [draft.lmdbPathEnvVar];
  const names = [draft.sftpHostEnvVar, draft.sftpRootEnvVar, draft.sftpUserEnvVar];
  // Optional on purpose: an empty password variable means key authentication through an
  // ssh-agent, which leaves no secret for anything here to mishandle. Listing it anyway would
  // send people looking for a password they do not need.
  if (draft.sftpPasswordEnvVar.trim()) names.push(draft.sftpPasswordEnvVar.trim());
  return names;
}

/** A placeholder that shows the SHAPE of each value without inventing anyone's path. */
export function envPlaceholder(name: string, kind: StorageKind): string {
  if (kind === "lmdb") return "/path/to/<dataset>.lmdb";
  if (kind === "local") return "/path/to/processed";
  if (name.toLowerCase().includes("host")) return "gpu-node.your-lab";
  if (name.toLowerCase().includes("user")) return "your-account";
  if (name.toLowerCase().includes("root")) return "/srv/datasets";
  return "<value>";
}

export function storageExportLines(draft: StorageDraft): string {
  return storageEnvVars(draft)
    .map((name) => `export ${name}=${envPlaceholder(name, draft.kind)}`)
    .join("\n");
}

/** The one command that answers "can this machine read this dataset". */
export function storageCheckCommand(draft: StorageDraft): string {
  const dataset = cliToken(draft.datasetId);
  const suffix = dataset ? ` --dataset-id ${dataset}` : "";
  return `uv run --no-sync python scripts/check_storage.py --storage ${draft.kind}${suffix}`;
}

/**
 * How the choice reaches a run.
 *
 * `storage=` is a plain CLI override and needs no experiment edit, because the storage block is
 * excluded from `science_hash`: two people reading one dataset two ways still produce runs that
 * compare directly (ADR-010).
 */
export function storageRunCommand(draft: StorageDraft, experimentName: string): string {
  const name = cliToken(experimentName) || "<experiment>";
  return `uv run --no-sync python scripts/train.py +exp=${name} storage=${draft.kind}`;
}

/** The YAML the choice corresponds to, for someone who wants a named config of their own. */
export function storageYaml(draft: StorageDraft): string {
  const header = [
    "# configs/storage/<name>.yaml",
    "# Locations are variable NAMES, never values: this file is committed, and so is the",
    "# frozen resolved spec (contract §34).",
  ].join("\n");
  if (draft.kind === "local") {
    return `${header}\nkind: local\nroot_env_var: ${draft.rootEnvVar}`;
  }
  if (draft.kind === "lmdb") {
    return [
      header,
      "kind: lmdb",
      `path_env_var: ${draft.lmdbPathEnvVar}`,
      `key_prefix: ${yamlString(draft.keyPrefix)}`,
      `key_suffix: ${yamlString(draft.keySuffix)}`,
      "key_encoding: utf-8",
      `child_separator: ${yamlString(draft.childSeparator)}`,
      `lock: ${draft.lmdbLock}`,
      "readahead: false",
      "max_readers: 2048",
    ].join("\n");
  }
  return [
    header,
    "kind: sftp",
    `host_env_var: ${draft.sftpHostEnvVar}`,
    `remote_root_env_var: ${draft.sftpRootEnvVar}`,
    `username_env_var: ${draft.sftpUserEnvVar}`,
    `password_env_var: ${draft.sftpPasswordEnvVar.trim() ? draft.sftpPasswordEnvVar.trim() : "null"}`,
    "key_filename_env_var: null",
    "known_hosts_env_var: null",
    "port: 22",
    "timeout: 20.0",
  ].join("\n");
}

/** Reasons this draft cannot work yet, in the order they should be fixed. */
export function storageProblems(draft: StorageDraft, locale: "en" | "ko"): string[] {
  const problems: string[] = [];
  for (const name of storageEnvVars(draft)) {
    if (!/^[A-Z][A-Z0-9_]*$/.test(name)) {
      problems.push(
        locale === "ko"
          ? `환경변수 이름 "${name}"은 대문자·숫자·밑줄만 쓸 수 있습니다.`
          : `Environment variable name "${name}" must be upper case letters, digits and underscores.`,
      );
    }
  }
  if (draft.kind === "lmdb" && draft.lmdbLock) {
    problems.push(
      locale === "ko"
        ? "lock: true는 스토어를 아직 쓰는 중일 때만 맞고, 그 경우 DataLoader worker를 쓸 수 없습니다(training.num_workers: 0)."
        : "lock: true is only correct while the store is still being written, and it rules out DataLoader workers (training.num_workers: 0).",
    );
  }
  if (draft.kind === "lmdb" && (!draft.childSeparator || draft.childSeparator.includes("\\"))) {
    problems.push(
      locale === "ko"
        ? "프레임 키 구분자가 비어 있거나 역슬래시를 포함합니다. 연구실 LMDB는 #입니다."
        : "The frame key separator is empty or contains a backslash. The lab's stores use #.",
    );
  }
  if (draft.kind === "sftp") {
    problems.push(
      locale === "ko"
        ? "가능하면 sshfs로 마운트하고 local을 쓰세요. SFTP는 읽을 때마다 객체 전체를 worker 메모리에 올립니다."
        : "Prefer mounting with sshfs and using local. SFTP pulls each whole object into the worker's memory.",
    );
  }
  return problems;
}

function cliToken(value: string): string {
  return value.trim().replace(/[^A-Za-z0-9_.:/-]/g, "");
}

function yamlString(value: string): string {
  return value ? JSON.stringify(value) : '""';
}
