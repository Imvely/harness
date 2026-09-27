import { describe, expect, it } from "bun:test";
import {
  DEFAULT_SPEC,
  allModels,
  asEntry,
  customFromRef,
  describeSpec,
  entryFor,
  scaffoldCommand,
  specId,
  specIsRunnable,
  specIssueText,
  specIssues,
  specOf,
  specYaml,
} from "../src/db/modelStudio";
import { framesFor, hubPage, hubSearchUrl, modelLinks, parseHubModels, sourceFor } from "../src/db/modelSearch";
import { addCustomModel, createInitialMockDatabase, removeCustomModel, validateControlState } from "../src/db/mockDb";
import { buildLaunchCommand, buildYamlPatch, launchBlocker } from "../src/db/controlPreview";
import { initialControl } from "../src/components/ControlView";
import { demoRuns } from "../src/data/demoRuns";
import type { CustomModel, ModelSpec } from "../src/types";

const own: CustomModel = {
  id: "own_my_net",
  label: "MyNet",
  source: "local",
  ref: "pad_research.models.my_net.MyNet",
  frames: 8,
  paramsM: 4.2,
  note: "my own",
  addedAt: "2026-09-28T00:00:00.000Z",
};

const spec = (overrides: Partial<ModelSpec> = {}): ModelSpec => ({ ...DEFAULT_SPEC, ...overrides });

describe("a model is a composition", () => {
  it("names itself from its parts, and stays config-safe", () => {
    expect(specId(spec())).toBe("video_baseline_t8");
    expect(specId(spec({ backboneId: "frame_baseline", temporal: "mean", head: "mlp", frames: 8 }))).toBe(
      "frame_baseline_mean_mlp_t8",
    );
    expect(specId(spec({ backboneId: "frame_baseline", frames: 1 }))).toBe("frame_baseline");
    expect(/^[a-z0-9_]+$/.test(specId(spec()))).toBe(true);
  });

  it("reads back as a sentence in both languages", () => {
    expect(describeSpec(spec(), "ko")).toContain("→");
    expect(describeSpec(spec(), "en")).toContain("frames");
    expect(describeSpec(spec({ backboneId: own.id }), "en", [own])).toContain("MyNet");
  });

  it("writes a model block a config can hold", () => {
    const yaml = specYaml(spec({ backboneId: own.id, temporal: "mean", head: "mlp" }), [own]);
    expect(yaml).toContain("source: local");
    expect(yaml).toContain("ref: pad_research.models.my_net.MyNet");
    expect(yaml).toContain("temporal: mean");
    expect(yaml).toContain("head: mlp");
  });

  it("comes out of a control state without being stored twice", () => {
    expect(specOf(initialControl)).toEqual({
      backboneId: initialControl.modelId,
      temporal: initialControl.temporal,
      head: initialControl.head,
      frames: initialControl.frames,
    });
  });
});

describe("a combination that cannot work says so before anything is trained", () => {
  const codes = (value: ModelSpec, custom: CustomModel[] = []) =>
    specIssues(value, custom).map((issue) => issue.code);

  it("blocks several frames through a backbone that reads one", () => {
    const issues = specIssues(spec({ backboneId: "frame_baseline", frames: 8, temporal: "none" }));
    const blocking = issues.find((issue) => issue.code === "frame_backbone_needs_time");
    expect(blocking?.level).toBe("blocking");
    expect(blocking?.part).toBe("temporal");
    expect(specIssueText("en", blocking!)).toContain("throws the rest away");
    // With a temporal step it is fine.
    expect(codes(spec({ backboneId: "frame_baseline", frames: 8, temporal: "mean" }))).not.toContain(
      "frame_backbone_needs_time",
    );
  });

  it("warns when pooling is put on top of a backbone that already reads time", () => {
    const issues = specIssues(spec({ backboneId: "video_baseline", temporal: "mean" }));
    expect(issues.find((issue) => issue.code === "clip_backbone_time_twice")?.level).toBe("warning");
    // Attention over frames is a real choice on a clip model, not a redundancy.
    expect(codes(spec({ backboneId: "video_baseline", temporal: "attention" }))).not.toContain(
      "clip_backbone_time_twice",
    );
  });

  it("warns that a pixel-wise head needs the spatial map it no longer has", () => {
    expect(codes(spec({ backboneId: "video_baseline", head: "pixelwise" }))).toContain(
      "pixelwise_after_pooling",
    );
    expect(codes(spec({ backboneId: "frame_baseline", frames: 1, head: "pixelwise" }))).not.toContain(
      "pixelwise_after_pooling",
    );
  });

  it("blocks a backbone with no adapter here, and names the command that creates one", () => {
    const candidate = spec({ backboneId: "x3d_m", frames: 16 });
    expect(specIsRunnable(candidate)).toBe(false);
    expect(codes(candidate)).toContain("no_adapter");
    const command = scaffoldCommand(candidate);
    expect(command).toContain("scripts/new_model.py");
    expect(command).toContain("--backbone pytorchvideo:x3d_m");
    expect(command).toContain("--frames 16");
  });

  it("blocks a backbone that is not in any list", () => {
    expect(codes(spec({ backboneId: "does_not_exist" }))).toEqual(["unknown_backbone"]);
    expect(specIsRunnable(spec({ backboneId: "does_not_exist" }))).toBe(false);
  });

  it("lets the two implemented baselines through", () => {
    expect(specIsRunnable(spec())).toBe(true);
    expect(specIsRunnable(spec({ backboneId: "frame_baseline", frames: 1 }))).toBe(true);
  });

  it("scaffolds a model of one's own from its own source and ref", () => {
    const command = scaffoldCommand(spec({ backboneId: own.id, temporal: "mean" }), [own]);
    expect(command).toContain("--backbone local:pad_research.models.my_net.MyNet");
    expect(command).toContain("--temporal mean");
  });
});

describe("a model added here joins the list", () => {
  it("turns a reference into a config-safe id", () => {
    const added = customFromRef("huggingface", "MCG-NJU/videomae-base", { frames: 16 });
    expect(added.id).toBe("own_mcg_nju_videomae_base");
    expect(added.label).toBe("videomae-base");
    expect(added.frames).toBe(16);
    expect(() => customFromRef("timm", "   ")).toThrow();
  });

  it("appears beside the catalogue entries", () => {
    expect(allModels([own]).some((model) => model.id === own.id)).toBe(true);
    expect(entryFor(own.id, [own])?.status).toBe("user_added");
    expect(asEntry(own).group).toBe("custom");
    expect(asEntry(own).library).toBe("this repository");
  });

  it("is stored, audited, and refused when it repeats or is malformed", () => {
    const db = createInitialMockDatabase(demoRuns, "demo");
    expect(db.customModels).toEqual([]);
    const first = addCustomModel(db, own);
    expect(first.item?.id).toBe(own.id);
    expect(first.state.customModels.length).toBe(1);
    expect(first.state.auditLog[0].kind).toBe("model_added");

    const again = addCustomModel(first.state, own);
    expect(again.item).toBeNull();
    expect(again.issues[0]).toContain("already in the list");

    // A reference with a space in it would reach a command line.
    const bad = addCustomModel(first.state, { ...own, id: "own_bad", ref: "rm -rf /" });
    expect(bad.item).toBeNull();
    expect(bad.issues.length).toBeGreaterThan(0);

    const removed = removeCustomModel(first.state, own.id);
    expect(removed.state.customModels).toEqual([]);
    expect(removed.state.auditLog[0].kind).toBe("model_removed");
    expect(removeCustomModel(db, "own_nothing").issues[0]).toContain("not in the list");
  });

  it("cannot run until an adapter exists, and the draft says how", () => {
    const control = { ...initialControl, modelId: own.id };
    expect(launchBlocker(control, [own])).toContain("research candidate");
    expect(buildLaunchCommand(control, [own])).toContain("BLOCKED");
    const patch = buildYamlPatch(control, [own]);
    expect(patch).toContain("create it with: uv run");
    expect(patch).toContain("ref: pad_research.models.my_net.MyNet");
    expect(validateControlState(control, [own]).join(" ")).toContain("no adapter");
  });
});

describe("finding a model that is not in the list yet", () => {
  it("builds a hub search that can be narrowed to video models", () => {
    const url = hubSearchUrl("anti-spoofing", { videoOnly: true, limit: 5 });
    expect(url).toContain("https://huggingface.co/api/models?");
    expect(url).toContain("search=anti-spoofing");
    expect(url).toContain("filter=video-classification");
    expect(url).toContain("limit=5");
    expect(hubSearchUrl("x")).not.toContain("filter=");
    expect(() => hubSearchUrl("  ")).toThrow();
    expect(hubPage("owner/name")).toBe("https://huggingface.co/owner/name");
  });

  it("reads only the fields it uses out of a third-party payload", () => {
    const parsed = parseHubModels([
      { id: "a/b", downloads: 12, likes: 3, tags: ["video", 7], pipeline_tag: "video-classification" },
      { modelId: "c/d" },
      { nope: true },
      "not an object",
    ]);
    expect(parsed.map((model) => model.id)).toEqual(["a/b", "c/d"]);
    expect(parsed[0].tags).toEqual(["video"]);
    expect(parsed[1].downloads).toBeNull();
    expect(parseHubModels({ data: [] })).toEqual([]);
  });

  it("decides how to load a record from its own tags, not from its name", () => {
    expect(sourceFor({ id: "a/b", downloads: null, likes: null, tags: ["timm"], pipeline: null, updatedAt: null })).toBe(
      "timm",
    );
    expect(sourceFor({ id: "a/b", downloads: null, likes: null, tags: [], pipeline: null, updatedAt: null })).toBe(
      "huggingface",
    );
    expect(
      framesFor({ id: "a/b", downloads: null, likes: null, tags: [], pipeline: "video-classification", updatedAt: null }),
    ).toBeGreaterThan(1);
    expect(framesFor({ id: "a/b", downloads: null, likes: null, tags: [], pipeline: null, updatedAt: null })).toBe(1);
  });

  it("offers the pages where a model's code and numbers are", () => {
    const links = modelLinks("videomae-base");
    expect(links[0].url).toContain("huggingface.co/models?search=");
    expect(links.some((link) => link.url.includes("paperswithcode"))).toBe(true);
    expect(links.every((link) => !link.url.includes(" "))).toBe(true);
  });
});
