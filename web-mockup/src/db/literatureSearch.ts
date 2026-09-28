/**
 * Links out to the places a claim can be checked, built from what is on screen.
 *
 * A paper title in a table is a dead end: verifying it means retyping it into another site. So
 * every title, model and dataset here carries the searches that find it — arXiv, Google
 * Scholar, Semantic Scholar, Papers with Code, DBLP — plus, for the sites whose canonical URL
 * is known, the page itself.
 *
 * Two rules:
 *
 * **A search, not a guess.** A dataset or paper gets a hardcoded URL only when that URL is
 * established. Otherwise it gets a search, because a wrong link that looks authoritative is
 * worse than one more click.
 *
 * **Reading is not citing.** These links open a search; nothing here decides what a paper says.
 * A number from a paper still enters `claims.jsonl` by hand, from the PDF, with a page
 * reference (research contract section 23).
 */

export type SearchProvider =
  | "arxiv"
  | "scholar"
  | "semantic_scholar"
  | "paperswithcode"
  | "dblp";

export interface SearchLink {
  provider: SearchProvider;
  label: string;
  url: string;
  /** What this provider is good for, ko/en — shown in the hint, not as body text. */
  note: { ko: string; en: string };
}

const PROVIDERS: Record<
  SearchProvider,
  { label: string; url: (query: string) => string; note: { ko: string; en: string } }
> = {
  arxiv: {
    label: "arXiv",
    url: (query) => `https://arxiv.org/search/?searchtype=all&query=${encodeURIComponent(query)}`,
    note: {
      ko: "원문 PDF가 바로 있습니다. 수치를 인용할 때는 여기서 확인하세요.",
      en: "The PDF itself. Check a number here before citing it.",
    },
  },
  scholar: {
    label: "Google Scholar",
    url: (query) => `https://scholar.google.com/scholar?q=${encodeURIComponent(query)}`,
    note: {
      ko: "인용 수와 인용한 논문 목록을 봅니다. 후속 연구를 찾는 데 가장 빠릅니다.",
      en: "Citation counts and who cited it — the fastest way to find follow-up work.",
    },
  },
  semantic_scholar: {
    label: "Semantic Scholar",
    url: (query) => `https://www.semanticscholar.org/search?q=${encodeURIComponent(query)}`,
    note: {
      ko: "인용 맥락(무엇을 근거로 인용했는지)을 보여 줍니다. 수치의 출처를 거슬러 갈 때 씁니다.",
      en: "Shows citation context — what a paper was cited *for*, which is how you trace a number back.",
    },
  },
  paperswithcode: {
    label: "Papers with Code",
    url: (query) => `https://paperswithcode.com/search?q=${encodeURIComponent(query)}`,
    note: {
      ko: "공개 구현과 벤치마크 표를 봅니다. 재현 가능성을 먼저 확인할 때 씁니다.",
      en: "Public implementations and benchmark tables, for checking whether a result is reproducible.",
    },
  },
  dblp: {
    label: "DBLP",
    url: (query) => `https://dblp.org/search?q=${encodeURIComponent(query)}`,
    note: {
      ko: "어느 학회·연도에 실렸는지 정확히 확인합니다. 인용 서식을 만들 때 씁니다.",
      en: "Exactly which venue and year, which is what a citation needs.",
    },
  },
};

export const SEARCH_PROVIDERS: SearchProvider[] = [
  "arxiv",
  "scholar",
  "semantic_scholar",
  "paperswithcode",
  "dblp",
];

export function searchUrl(provider: SearchProvider, query: string): string {
  const trimmed = query.trim();
  if (trimmed.length === 0) throw new Error("a search needs a query");
  return PROVIDERS[provider].url(trimmed);
}

export function searchLinks(query: string, providers = SEARCH_PROVIDERS): SearchLink[] {
  return providers.map((provider) => ({
    provider,
    label: PROVIDERS[provider].label,
    url: searchUrl(provider, query),
    note: PROVIDERS[provider].note,
  }));
}

/** An arXiv id in a string, if there is one: `arXiv:2203.12602`, `2203.12602v2`, a full URL. */
export function arxivId(text: string): string | null {
  const match = text.match(/(\d{4}\.\d{4,5})(v\d+)?/);
  return match ? match[1] : null;
}

/** A DOI in a string, if there is one. */
export function doiFrom(text: string): string | null {
  const match = text.match(/10\.\d{4,9}\/[^\s"<>]+/);
  return match ? match[0] : null;
}

/** Links for one paper: the page itself when an id is known, then the searches. */
export function paperLinks(title: string, identifier?: string): SearchLink[] {
  const links: SearchLink[] = [];
  const id = identifier ? arxivId(identifier) : null;
  const doi = identifier && !id ? doiFrom(identifier) : null;
  if (doi) {
    links.push({
      provider: "dblp",
      label: "DOI",
      url: `https://doi.org/${doi}`,
      note: {
        ko: "출판사 페이지로 갑니다. 최종본 서식과 페이지 번호가 여기 있습니다.",
        en: "The publisher page, which has the final wording and page numbers.",
      },
    });
  }
  if (id) {
    links.push({
      provider: "arxiv",
      label: `arXiv:${id}`,
      url: `https://arxiv.org/abs/${id}`,
      note: {
        ko: "이 논문의 초록 페이지입니다.",
        en: "This paper's abstract page.",
      },
    });
  }
  const providers = id ? SEARCH_PROVIDERS.filter((provider) => provider !== "arxiv") : SEARCH_PROVIDERS;
  return [...links, ...searchLinks(`"${title}"`, providers)];
}

/**
 * Semantic Scholar's search API, which allows browser requests and needs no key.
 *
 * Used for an optional live lookup: a rate limit or an offline machine has to leave the page
 * working, so a caller treats a failure as "no results yet", never as an error state.
 */
export function semanticScholarApiUrl(query: string, limit = 5): string {
  const fields = "title,year,authors,venue,citationCount,externalIds,openAccessPdf,abstract";
  return `https://api.semanticscholar.org/graph/v1/paper/search?query=${encodeURIComponent(
    query.trim(),
  )}&limit=${limit}&fields=${fields}`;
}

/** Dataset pages that are established, by domain id. Everything else gets a search. */
const DATASET_PAGES: Record<string, string> = {
  aihub115:
    "https://aihub.or.kr/aihubdata/data/view.do?currMenu=115&topMenu=100&dataSetSn=161",
  aihub114:
    "https://aihub.or.kr/aihubdata/data/view.do?currMenu=115&topMenu=100&dataSetSn=168",
};

/** What each domain is called in the literature, which is what a search has to use. */
const DATASET_QUERIES: Record<string, string> = {
  aihub115: "AI Hub liveness detection face video dataset Korea",
  aihub114: "AI Hub face recognition video dataset Korea",
  siw_mv2: "SiW-Mv2 spoof in the wild face anti-spoofing dataset",
  idiap_replayattack: "Replay-Attack database face spoofing Idiap Chingovska",
  casia_surf: "CASIA-SURF multi-modal face anti-spoofing dataset",
  casia_cefa: "CASIA-CeFA cross-ethnicity face anti-spoofing dataset",
};

export function datasetPage(domainId: string): string | null {
  return DATASET_PAGES[domainId] ?? null;
}

export function datasetLinks(domainId: string): SearchLink[] {
  const query = DATASET_QUERIES[domainId] ?? domainId;
  const page = datasetPage(domainId);
  const links: SearchLink[] = [];
  if (page) {
    links.push({
      provider: "arxiv",
      label: domainId.startsWith("aihub") ? "AI Hub 데이터 페이지" : "Dataset page",
      url: page,
      note: {
        ko: "배포 페이지입니다. 라이선스와 신청 조건이 여기 있습니다.",
        en: "The distribution page, which is where the licence and application terms are.",
      },
    });
  }
  return [...links, ...searchLinks(query, ["scholar", "semantic_scholar", "paperswithcode"])];
}

/**
 * The search that finds work on exactly what is selected right now.
 *
 * Built from the study's own terms rather than free text, so the query a reader runs is the
 * same one the next reader runs.
 */
export function contextQuery(parts: {
  topic?: string;
  model?: string;
  domains?: string[];
  adaptation?: boolean;
}): string {
  const terms = [parts.topic ?? "face anti-spoofing presentation attack detection"];
  if (parts.adaptation) terms.push("domain adaptation");
  if (parts.model) terms.push(parts.model);
  for (const domain of parts.domains ?? []) {
    const query = DATASET_QUERIES[domain];
    if (query) terms.push(query.split(" ").slice(0, 2).join(" "));
  }
  return terms.join(" ");
}
