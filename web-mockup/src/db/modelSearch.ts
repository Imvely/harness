/**
 * Finding a model that is not in the list yet.
 *
 * A fixed catalogue goes stale the week after it is written, and the architecture worth trying is
 * usually the one published since. So: a search against the Hugging Face hub, which allows
 * browser requests and needs no key, plus the pages where a model's code and numbers live.
 *
 * What comes back is a hub record, not a verdict. Downloads and likes say what is popular, never
 * what detects a spoof, and this module does not rank by them — it reports them and leaves the
 * judgement to a person, who then has to read the paper (research contract section 23).
 */

import type { CustomModel } from "./modelStudio";
import type { SearchLink } from "./literatureSearch";
import { searchLinks } from "./literatureSearch";

export interface HubModel {
  /** The hub id, `owner/name`, which is also what a loader is given. */
  id: string;
  downloads: number | null;
  likes: number | null;
  /** Hub tags: the library, the task, the dataset. Used to guess how to load it. */
  tags: string[];
  pipeline: string | null;
  updatedAt: string | null;
}

/** Hugging Face model search. `video` and `image-classification` are the useful filters here. */
export function hubSearchUrl(query: string, options: { limit?: number; videoOnly?: boolean } = {}): string {
  const trimmed = query.trim();
  if (trimmed.length === 0) throw new Error("a model search needs a query");
  const params = new URLSearchParams({
    search: trimmed,
    limit: String(options.limit ?? 12),
    sort: "downloads",
    direction: "-1",
  });
  if (options.videoOnly) params.set("filter", "video-classification");
  return `https://huggingface.co/api/models?${params.toString()}`;
}

export function hubPage(id: string): string {
  return `https://huggingface.co/${id}`;
}

/** Hub records are third-party data: read only the fields we use, and trust none of the types. */
export function parseHubModels(payload: unknown): HubModel[] {
  if (!Array.isArray(payload)) return [];
  const models: HubModel[] = [];
  for (const item of payload) {
    if (typeof item !== "object" || item === null) continue;
    const record = item as Record<string, unknown>;
    const id = typeof record.id === "string" ? record.id : typeof record.modelId === "string" ? record.modelId : null;
    if (!id) continue;
    models.push({
      id,
      downloads: typeof record.downloads === "number" ? record.downloads : null,
      likes: typeof record.likes === "number" ? record.likes : null,
      tags: Array.isArray(record.tags) ? record.tags.filter((tag): tag is string => typeof tag === "string") : [],
      pipeline: typeof record.pipeline_tag === "string" ? record.pipeline_tag : null,
      updatedAt: typeof record.lastModified === "string" ? record.lastModified : null,
    });
  }
  return models;
}

/** Which loader a hub record needs, from its own tags rather than from its name. */
export function sourceFor(model: HubModel): CustomModel["source"] {
  if (model.tags.includes("timm")) return "timm";
  return "huggingface";
}

/** Frames a hub record expects: a video model reads several, an image model one. */
export function framesFor(model: HubModel): number {
  const video =
    model.pipeline === "video-classification" ||
    model.tags.some((tag) => tag.includes("video") || tag.includes("videomae") || tag.includes("timesformer"));
  return video ? 16 : 1;
}

/** Where to look when the hub is not the right place: code, benchmarks, the paper. */
export function modelLinks(name: string): SearchLink[] {
  return [
    {
      provider: "paperswithcode",
      label: "Hugging Face",
      url: `https://huggingface.co/models?search=${encodeURIComponent(name.trim())}`,
      note: {
        ko: "사전학습 가중치와 로딩 코드가 있습니다. 여기 있는 id를 그대로 등록하면 됩니다.",
        en: "Pretrained weights and loading code. The id here is what you register.",
      },
    },
    ...searchLinks(name, ["paperswithcode", "arxiv", "scholar"]),
  ];
}
