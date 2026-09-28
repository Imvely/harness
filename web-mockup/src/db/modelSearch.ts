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
  /**
   * arXiv ids the hub record itself names (`arxiv:2203.12602` tags).
   *
   * This is the difference between a link and a guess: when the record says which paper it is,
   * the abstract page can be linked directly. When it does not, there is no arXiv button — a
   * search box on arXiv fed a checkpoint name like `videomae-base-finetuned-kinetics` returns
   * nothing, and a button that reliably returns nothing is worse than no button.
   */
  arxivIds: string[];
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
    const tags = Array.isArray(record.tags)
      ? record.tags.filter((tag): tag is string => typeof tag === "string")
      : [];
    models.push({
      id,
      downloads: typeof record.downloads === "number" ? record.downloads : null,
      likes: typeof record.likes === "number" ? record.likes : null,
      tags,
      pipeline: typeof record.pipeline_tag === "string" ? record.pipeline_tag : null,
      updatedAt: typeof record.lastModified === "string" ? record.lastModified : null,
      arxivIds: tags
        .filter((tag) => tag.startsWith("arxiv:"))
        .map((tag) => tag.slice("arxiv:".length))
        .filter((id) => /^\d{4}\.\d{4,5}$/.test(id)),
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

/**
 * Links that are known to exist for this record, and nothing else.
 *
 * Every result used to carry the same four buttons — Hugging Face, Papers with Code, arXiv,
 * Scholar — which said nothing about where the model actually is, and three of the four were a
 * search seeded with a checkpoint name. Here a link appears only when the hub record establishes
 * it: its own page, and the paper it names in an `arxiv:` tag.
 */
export function hubLinks(model: HubModel): SearchLink[] {
  const links: SearchLink[] = [
    {
      provider: "paperswithcode",
      label: "Hugging Face",
      url: hubPage(model.id),
      note: {
        ko: "이 모델의 허브 페이지입니다. 가중치와 로딩 코드가 여기 있습니다.",
        en: "This model's hub page, with its weights and loading code.",
      },
    },
  ];
  for (const id of model.arxivIds) {
    links.push({
      provider: "arxiv",
      label: `arXiv:${id}`,
      url: `https://arxiv.org/abs/${id}`,
      note: {
        ko: "이 모델 카드가 밝힌 논문입니다.",
        en: "The paper this model card names.",
      },
    });
  }
  return links;
}

/**
 * Searches for a model whose paper is not established: two places, clearly a search.
 *
 * Kept separate from :func:`hubLinks` and shown behind a disclosure, so a real page and a query
 * never sit side by side looking like the same thing. The query is the model's own name, not
 * whatever was typed into the search box.
 */
export function modelSearchLinks(name: string): SearchLink[] {
  const trimmed = name.trim();
  if (trimmed.length === 0) return [];
  return searchLinks(trimmed, ["paperswithcode", "scholar"]);
}

/** The name to search with: a hub id's last segment, or a dotted path's class name. */
export function searchName(ref: string): string {
  return ref.trim().split("/").slice(-1)[0].split(".").slice(-1)[0];
}

/**
 * Links for a model somebody registered here.
 *
 * A hub model has a page; a class in this repository has none, and searching the web for
 * `MyNet` would only produce noise, so it gets no links at all.
 */
export function customLinks(model: CustomModel): SearchLink[] {
  if (model.source === "huggingface") {
    return [
      {
        provider: "paperswithcode",
        label: "Hugging Face",
        url: hubPage(model.ref),
        note: {
          ko: "등록할 때 쓴 허브 id의 페이지입니다.",
          en: "The page of the hub id this was registered with.",
        },
      },
    ];
  }
  if (model.source === "timm") {
    return [
      {
        provider: "paperswithcode",
        label: "timm",
        url: `https://huggingface.co/models?library=timm&search=${encodeURIComponent(model.ref)}`,
        note: {
          ko: "timm 가중치 목록에서 이 이름을 찾습니다.",
          en: "Finds this name among the timm weights.",
        },
      },
    ];
  }
  return [];
}
