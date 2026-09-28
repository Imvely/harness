import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  envPlaceholder,
  storageCheckCommand,
  storageEnvVars,
  storageExportLines,
  storageProblems,
  storageRunCommand,
  storageYaml,
} from "../src/db/storagePreview";
import { initialStorage } from "../src/components/StorageView";
import type { StorageDraft } from "../src/types";

const CONFIG_DIR = join(import.meta.dir, "..", "..", "configs", "storage");

function draft(patch: Partial<StorageDraft> = {}): StorageDraft {
  return { ...initialStorage, ...patch };
}

describe("the variable names on screen match the ones Python reads", () => {
  // The failure this prevents is silent: the screen keeps printing an old name long after the
  // config was renamed, and the person following it gets "environment variable not set".
  test.each([
    ["local", "root_env_var"],
    ["lmdb", "path_env_var"],
  ] as const)("%s names the variable its config declares", (kind, field) => {
    const yaml = readFileSync(join(CONFIG_DIR, `${kind}.yaml`), "utf8");
    const declared = yaml.match(new RegExp(`^${field}:\\s*(\\S+)`, "m"))?.[1];
    expect(declared).toBeTruthy();
    expect(storageEnvVars(draft({ kind }))).toContain(declared!);
  });

  test("sftp names all three of its required variables", () => {
    const yaml = readFileSync(join(CONFIG_DIR, "sftp.yaml"), "utf8");
    for (const field of ["host_env_var", "remote_root_env_var", "username_env_var"]) {
      const declared = yaml.match(new RegExp(`^${field}:\\s*(\\S+)`, "m"))?.[1];
      expect(storageEnvVars(draft({ kind: "sftp" }))).toContain(declared!);
    }
  });
});

describe("what the screen tells you to export", () => {
  test("an unset optional password is not listed as something to set", () => {
    // Listing it would send people hunting for a password they do not need: an empty value
    // means key authentication through an ssh-agent.
    expect(storageEnvVars(draft({ kind: "sftp" }))).not.toContain("PAD_SFTP_PASSWORD");
    expect(
      storageEnvVars(draft({ kind: "sftp", sftpPasswordEnvVar: "PAD_SFTP_PASSWORD" })),
    ).toContain("PAD_SFTP_PASSWORD");
  });

  test("placeholders show a shape rather than inventing someone's path", () => {
    expect(envPlaceholder("PAD_LMDB_PATH", "lmdb")).toContain(".lmdb");
    expect(storageExportLines(draft({ kind: "local" }))).toBe(
      "export PAD_DATA_ROOT=/path/to/processed",
    );
  });
});

describe("the check command", () => {
  test("carries the dataset when one is named", () => {
    expect(storageCheckCommand(draft({ datasetId: "oulu_npu" }))).toContain(
      "--dataset-id oulu_npu",
    );
  });

  test("omits the flag entirely when none is named", () => {
    // `--dataset-id ""` would be a different, worse command than leaving it off.
    expect(storageCheckCommand(draft({ datasetId: "  " }))).not.toContain("--dataset-id");
  });

  test("strips shell metacharacters from anything typed into it", () => {
    const command = storageCheckCommand(draft({ datasetId: "a; rm -rf /" }));
    expect(command).not.toContain(";");
  });
});

describe("the run command", () => {
  test("passes storage as a CLI override and edits no experiment file", () => {
    // Allowed precisely because storage is excluded from science_hash (ADR-010); execution.*
    // is not, and must never appear here.
    const command = storageRunCommand(draft({ kind: "lmdb" }), "syn_e02_video_source_only");
    expect(command).toContain("storage=lmdb");
    expect(command).toContain("+exp=syn_e02_video_source_only");
    expect(command).not.toContain("execution.");
  });
});

describe("the YAML it drafts", () => {
  test("contains variable names and no locations", () => {
    const yaml = storageYaml(draft({ kind: "sftp", sftpPasswordEnvVar: "" }));
    expect(yaml).toContain("host_env_var: PAD_SFTP_HOST");
    expect(yaml).toContain("password_env_var: null");
    // A literal path or hostname here would land in a committed file (contract §34).
    for (const line of yaml.split("\n").filter((l) => !l.startsWith("#"))) {
      expect(line).not.toMatch(/:\s*\//);
      expect(line).not.toContain("@");
    }
  });

  test("the frame key separator matches the shipped config and is quoted", () => {
    // Unquoted, `#` would start a YAML comment and the separator would silently be null.
    const yaml = readFileSync(join(CONFIG_DIR, "lmdb.yaml"), "utf8");
    const declared = yaml.match(/^child_separator:\s*"([^"]+)"/m)?.[1];
    expect(declared).toBe("#");
    expect(initialStorage.childSeparator).toBe(declared!);
    expect(storageYaml(draft({ kind: "lmdb" }))).toContain('child_separator: "#"');
  });

  test("quotes an LMDB key prefix so a trailing slash survives", () => {
    expect(storageYaml(draft({ kind: "lmdb", keyPrefix: "oulu_npu/" }))).toContain(
      'key_prefix: "oulu_npu/"',
    );
  });
});

describe("what it warns about", () => {
  test("a write lock is called out as ruling out DataLoader workers", () => {
    const problems = storageProblems(draft({ kind: "lmdb", lmdbLock: true }), "en");
    expect(problems.join(" ")).toContain("num_workers");
  });

  test("an empty frame key separator is called out", () => {
    expect(storageProblems(draft({ kind: "lmdb", childSeparator: "" }), "en").join(" ")).toContain(
      "separator",
    );
    expect(storageProblems(draft({ kind: "lmdb" }), "en").join(" ")).not.toContain("separator");
  });

  test("SFTP always recommends mounting instead", () => {
    expect(storageProblems(draft({ kind: "sftp" }), "en").join(" ")).toContain("sshfs");
  });

  test("a lower-case variable name is rejected before it reaches a shell", () => {
    expect(storageProblems(draft({ kind: "local", rootEnvVar: "pad_data_root" }), "en")).toHaveLength(
      1,
    );
  });

  test("a finished LMDB store has nothing to warn about", () => {
    expect(storageProblems(draft({ kind: "lmdb" }), "en")).toEqual([]);
  });
});
