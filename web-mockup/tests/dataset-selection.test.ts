import { describe, expect, it } from "bun:test";
import {
  DATASET_TREE,
  DOMAIN_FACTS,
  NODE_INDEX,
  divide,
  findNode,
  leafIds,
} from "../src/data/datasetCatalog";
import {
  EMPTY_SELECTION,
  collapse,
  expand,
  findingText,
  isRunnable,
  nodeState,
  review,
  selectionYaml,
  summarise,
  toggle,
} from "../src/db/datasetSelection";
import { buildLaunchCommand, buildYamlPatch, launchBlocker } from "../src/db/controlPreview";
import { initialControl } from "../src/components/ControlView";
import { MODEL_CATALOG, isRunnableModel, modelById, modelsInGroup } from "../src/data/modelCatalog";
import {
  arxivId,
  contextQuery,
  datasetLinks,
  datasetPage,
  paperLinks,
  searchLinks,
  searchUrl,
  semanticScholarApiUrl,
} from "../src/db/literatureSearch";

const node = (id: string) => {
  const found = findNode(id);
  if (!found) throw new Error(`no such node: ${id}`);
  return found;
};

describe("the catalogue keeps its measured totals", () => {
  it("divides a total into shares that add back up to it", () => {
    expect(divide(10, [1, 1, 1])).toEqual([4, 3, 3]);
    expect(divide(9625, [1, 1, 1]).reduce((a, b) => a + b, 0)).toBe(9625);
    expect(divide(0, [1, 2])).toEqual([0, 0]);
    expect(divide(5, [])).toEqual([]);
  });

  it("splits sum to the domain the store scan measured", () => {
    for (const domain of DATASET_TREE) {
      const splitClips = domain.children.reduce((total, split) => total + split.clips, 0);
      const splitFrames = domain.children.reduce((total, split) => total + split.frames, 0);
      expect(splitClips).toBe(domain.clips);
      expect(splitFrames).toBe(domain.frames);
    }
  });

  it("marks a divided number as not measured, so the UI can say so", () => {
    expect(node("aihub115").measured).toBe(true);
    expect(node("aihub115/train").measured).toBe(true);
    expect(node("aihub115/train/Light_01_High").measured).toBe(false);
    expect(node("aihub115/train/Light_01_High/real_01").measured).toBe(false);
  });

  it("keeps aihub114 visible but unusable, with the reason attached", () => {
    const excluded = node("aihub114");
    expect(excluded.blocked).toBe("camera_predicts_label");
    expect(DOMAIN_FACTS.aihub114.caveats.length).toBeGreaterThan(0);
    // The five we do use are not blocked.
    const usable = DATASET_TREE.filter((domain) => domain.blocked === undefined);
    expect(usable.map((domain) => domain.id).sort()).toEqual([
      "aihub115",
      "casia_cefa",
      "casia_surf",
      "idiap_replayattack",
      "siw_mv2",
    ]);
  });

  it("gives every node a unique path-shaped id", () => {
    const ids = [...NODE_INDEX.keys()];
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids.every((id) => /^[A-Za-z0-9_][A-Za-z0-9_./ -]*$/.test(id))).toBe(true);
  });
});

describe("selecting a node", () => {
  it("stands for every leaf under it, and collapses back to the parent", () => {
    const selection = toggle(EMPTY_SELECTION, "train", node("aihub115/train"));
    expect(selection.train).toEqual(["aihub115/train"]);
    expect(expand(selection, "train").length).toBe(leafIds(node("aihub115/train")).length);
    expect(nodeState(selection, "train", node("aihub115/train"))).toBe("on");
    expect(nodeState(selection, "train", node("aihub115"))).toBe("partial");
    expect(nodeState(selection, "dev", node("aihub115/train"))).toBe("off");
  });

  it("moves a node out of the role it was in, so one click cannot use it twice", () => {
    const train = toggle(EMPTY_SELECTION, "train", node("aihub115/train"));
    const moved = toggle(train, "test", node("aihub115/train"));
    expect(moved.train).toEqual([]);
    expect(moved.test).toEqual(["aihub115/train"]);
  });

  it("toggles off when it is already fully selected", () => {
    const on = toggle(EMPTY_SELECTION, "train", node("casia_cefa/train"));
    expect(toggle(on, "train", node("casia_cefa/train")).train).toEqual([]);
  });

  it("collapses a complete set of children into the parent id", () => {
    const leaves = leafIds(node("casia_cefa/train"));
    expect(collapse(leaves)).toEqual(["casia_cefa/train"]);
    // One leaf short stays as leaves rather than claiming the whole parent.
    expect(collapse(leaves.slice(1))).not.toEqual(["casia_cefa/train"]);
  });

  it("counts clips and frames of what is selected", () => {
    const selection = toggle(EMPTY_SELECTION, "train", node("aihub115/train"));
    const summary = summarise(selection, "train");
    expect(summary.clips).toBe(node("aihub115/train").clips);
    expect(summary.domains).toEqual(["aihub115"]);
    expect(summary.measured).toBe(true);
    expect(summarise(EMPTY_SELECTION, "test").clips).toBe(0);
  });
});

describe("the checks that decide whether a number would mean anything", () => {
  const codes = (selection: Parameters<typeof review>[0]) =>
    review(selection).map((finding) => finding.code);

  it("blocks an empty role", () => {
    expect(codes(EMPTY_SELECTION)).toEqual([
      "role_empty",
      "role_empty",
      "role_empty",
    ]);
    expect(isRunnable(EMPTY_SELECTION)).toBe(false);
  });

  it("blocks the same people appearing in two roles", () => {
    let selection = toggle(EMPTY_SELECTION, "train", node("aihub115/train/Light_01_High"));
    selection = toggle(selection, "test", node("aihub115/train/Light_02_Mid"));
    const overlap = review(selection).find((finding) => finding.code === "subject_in_two_roles");
    expect(overlap?.level).toBe("blocking");
    expect(overlap?.subject).toBe("aihub115/train");
    // The sentence names the fix, not the code.
    expect(findingText("en", overlap!)).toContain("Remove one side");
    expect(findingText("ko", overlap!)).toContain("같은 사람");
  });

  it("blocks a role that holds only one class", () => {
    const selection = toggle(EMPTY_SELECTION, "test", node("casia_cefa/dev/Real"));
    expect(codes(selection)).toContain("one_label_only");
  });

  it("blocks a domain whose camera predicts the label", () => {
    const selection = toggle(EMPTY_SELECTION, "train", node("aihub114/train"));
    expect(codes(selection)).toContain("blocked_domain");
  });

  it("warns, but does not block, when train and test share a domain", () => {
    let selection = toggle(EMPTY_SELECTION, "train", node("casia_surf/train"));
    selection = toggle(selection, "dev", node("casia_surf/dev"));
    selection = toggle(selection, "test", node("casia_surf/test"));
    const finding = review(selection).find((f) => f.code === "domain_in_train_and_test");
    expect(finding?.level).toBe("warning");
    expect(isRunnable(selection)).toBe(true);
  });

  it("warns when a domain records no frame timing", () => {
    const selection = toggle(EMPTY_SELECTION, "train", node("aihub115/train"));
    const finding = review(selection).find((f) => f.code === "timing_unknown");
    expect(finding?.subject).toBe("aihub115");
    expect(findingText("en", finding!)).toContain("optical flow");
  });

  it("warns when every test attack is the same instrument", () => {
    let selection = toggle(EMPTY_SELECTION, "train", node("aihub115/train"));
    selection = toggle(selection, "dev", node("aihub115/dev"));
    selection = toggle(selection, "test", node("casia_cefa/train"));
    expect(codes(selection)).toContain("single_attack_type");
  });

  it("accepts the default selection the screen opens with", () => {
    expect(isRunnable(initialControl.datasets)).toBe(true);
    const warnings = review(initialControl.datasets);
    expect(warnings.every((finding) => finding.level === "warning")).toBe(true);
  });

  it("writes the selection as a protocol block", () => {
    const yaml = selectionYaml(initialControl.datasets);
    expect(yaml).toContain("protocol:");
    expect(yaml).toContain("- aihub115/train");
    expect(selectionYaml(EMPTY_SELECTION)).toContain("[]");
  });
});

describe("the command is blocked for a reason a person can act on", () => {
  it("runs with the default configuration", () => {
    expect(launchBlocker(initialControl)).toBeNull();
    expect(buildLaunchCommand(initialControl)).toContain("scripts/adapt.py");
  });

  it("refuses when the data selection has a blocking finding", () => {
    const control = { ...initialControl, datasets: EMPTY_SELECTION };
    expect(launchBlocker(control)).toContain("data selection");
    expect(buildLaunchCommand(control)).toContain("BLOCKED");
  });

  it("refuses a model this repository has no adapter for", () => {
    const control = { ...initialControl, modelId: "videomae_b" };
    expect(launchBlocker(control)).toContain("research candidate");
    // The draft still records the intent, as a comment rather than an override.
    expect(buildYamlPatch(control)).toContain("no adapter yet");
  });

  it("uses train.py rather than adapt.py for a baseline", () => {
    const control = { ...initialControl, goal: "baseline" as const, adaptationMethod: "none" as const };
    expect(buildLaunchCommand(control)).toContain("scripts/train.py");
  });

  it("puts the selected splits in the config draft as comments", () => {
    const patch = buildYamlPatch(initialControl);
    expect(patch).toContain("# protocol:");
    expect(patch).toContain("#     - idiap_replayattack/test");
    expect(patch).toContain("goal: adapt_real_only");
  });
});

describe("the model catalogue", () => {
  it("says which models this repository can actually run", () => {
    expect(isRunnableModel("video_baseline")).toBe(true);
    expect(isRunnableModel("x3d_m")).toBe(false);
    expect(isRunnableModel("not_a_model")).toBe(false);
  });

  it("offers more than the two baselines, across the families worth trying", () => {
    expect(MODEL_CATALOG.length).toBeGreaterThan(8);
    expect(modelsInGroup("clip_transformer").length).toBeGreaterThan(2);
    expect(modelsInGroup("clip_3d").length).toBeGreaterThan(2);
  });

  it("orders a family by cost, cheapest first", () => {
    const params = modelsInGroup("clip_3d").map((model) => model.paramsM ?? Infinity);
    expect([...params].sort((a, b) => a - b)).toEqual(params);
  });

  it("gives every model a paper title to search for and a real library", () => {
    for (const model of MODEL_CATALOG) {
      expect(model.paper.length).toBeGreaterThan(10);
      expect(model.library.length).toBeGreaterThan(2);
      expect(model.why.ko.length).toBeGreaterThan(10);
      expect(model.why.en.length).toBeGreaterThan(10);
    }
    expect(modelById("video_baseline")?.frames).toBeGreaterThan(1);
    expect(modelById("frame_baseline")?.frames).toBe(1);
  });
});

describe("links out to where a claim can be checked", () => {
  it("builds an encoded search for every provider", () => {
    const links = searchLinks('"X3D: Expanding Architectures"');
    expect(links.length).toBe(5);
    for (const link of links) {
      expect(link.url.startsWith("https://")).toBe(true);
      expect(link.url).toContain("X3D");
      expect(link.url).not.toContain(" ");
    }
    expect(searchUrl("arxiv", "face anti-spoofing")).toBe(
      "https://arxiv.org/search/?searchtype=all&query=face%20anti-spoofing",
    );
  });

  it("refuses an empty query rather than opening a site with nothing in it", () => {
    expect(() => searchUrl("scholar", "   ")).toThrow();
  });

  it("goes straight to the abstract when an arXiv id is known", () => {
    expect(arxivId("arXiv:2203.12602v3")).toBe("2203.12602");
    expect(arxivId("no id here")).toBeNull();
    const links = paperLinks("VideoMAE", "arXiv:2203.12602");
    expect(links[0].url).toBe("https://arxiv.org/abs/2203.12602");
    expect(links.some((link) => link.provider === "scholar")).toBe(true);
  });

  it("links a dataset to its distribution page when that page is established", () => {
    expect(datasetLinks("aihub115")[0].url).toContain("dataSetSn=161");
    expect(datasetPage("aihub114")).toContain("dataSetSn=168");
    // Where no page is established, a search stands in rather than a guessed URL.
    expect(datasetPage("siw_mv2")).toBeNull();
    const links = datasetLinks("siw_mv2");
    expect(links.length).toBeGreaterThan(1);
    expect(links.every((link) => link.url.includes("SiW-Mv2"))).toBe(true);
  });

  it("builds the search from what is selected", () => {
    const query = contextQuery({
      model: "SlowFast Networks for Video Recognition",
      domains: ["idiap_replayattack"],
      adaptation: true,
    });
    expect(query).toContain("domain adaptation");
    expect(query).toContain("SlowFast");
    expect(semanticScholarApiUrl(query)).toContain("api.semanticscholar.org");
    expect(semanticScholarApiUrl(query)).toContain("citationCount");
  });
});
