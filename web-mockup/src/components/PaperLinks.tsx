import { useState } from "react";
import type { SearchLink } from "../db/literatureSearch";
import { searchLinks, semanticScholarApiUrl } from "../db/literatureSearch";
import type { Locale } from "../types";
import { Hint } from "./Hint";

/**
 * The searches that find a paper, and an optional live lookup.
 *
 * A title in a table is unverifiable without retyping it somewhere else, so every title carries
 * its searches. The live lookup is the same query against Semantic Scholar's open API: it needs
 * the network, it can be rate limited, and a failure has to leave the page working — so it is a
 * button, never something the page does on load, and it fails to a sentence rather than an error.
 *
 * What comes back is a search result, not a citation. A number still reaches `claims.jsonl` from
 * the PDF, by hand, with a page reference (research contract section 23).
 */
export function PaperLinks({
  query,
  locale,
  compact = false,
}: {
  query: string;
  locale: Locale;
  /** Inline row of links, for a card that is already dense. */
  compact?: boolean;
}) {
  const links = searchLinks(query);
  if (compact) {
    return (
      <span className="paper-links paper-links--compact">
        {links.slice(0, 3).map((link) => (
          <LinkOut key={link.provider} link={link} />
        ))}
      </span>
    );
  }
  return (
    <div className="paper-links">
      <p className="paper-links__query">
        <code>{query}</code>
      </p>
      <div className="chip-row">
        {links.map((link) => (
          <LinkOut key={link.provider} link={link} locale={locale} withHint />
        ))}
      </div>
      <LiveLookup locale={locale} query={query} />
    </div>
  );
}

/** Just the links, for a panel that already says what they are for. */
export function PaperLinkRow({ links, locale }: { links: SearchLink[]; locale: Locale }) {
  return (
    <div className="chip-row">
      {links.map((link) => (
        <LinkOut key={`${link.provider}:${link.label}`} link={link} locale={locale} withHint />
      ))}
    </div>
  );
}

function LinkOut({
  link,
  locale,
  withHint = false,
}: {
  link: SearchLink;
  locale?: Locale;
  withHint?: boolean;
}) {
  return (
    <span className="link-out">
      <a className="chip chip--link" href={link.url} rel="noreferrer noopener" target="_blank">
        {link.label}
      </a>
      {withHint && locale && (
        <Hint align="start" label={link.label}>
          {link.note[locale]}
        </Hint>
      )}
    </span>
  );
}

interface Paper {
  paperId: string;
  title: string;
  year: number | null;
  venue: string | null;
  citationCount: number | null;
  authors: { name: string }[];
  externalIds: { ArXiv?: string; DOI?: string } | null;
  openAccessPdf: { url: string } | null;
}

function LiveLookup({ query, locale }: { query: string; locale: Locale }) {
  const [state, setState] = useState<"idle" | "loading" | "done" | "failed">("idle");
  const [papers, setPapers] = useState<Paper[]>([]);

  const lookup = async () => {
    setState("loading");
    try {
      const response = await fetch(semanticScholarApiUrl(query));
      if (!response.ok) throw new Error(String(response.status));
      const body = (await response.json()) as { data?: Paper[] };
      setPapers(body.data ?? []);
      setState("done");
    } catch {
      // Offline, rate limited, or blocked. None of those are worth an error state on a page
      // whose links still work.
      setState("failed");
    }
  };

  return (
    <div className="live-lookup">
      <button className="button button--secondary button--small" onClick={lookup} type="button">
        {state === "loading"
          ? locale === "ko"
            ? "찾는 중…"
            : "Looking…"
          : locale === "ko"
            ? "여기서 바로 찾아보기"
            : "Look it up here"}
      </button>
      {state === "failed" && (
        <p className="subtle">
          {locale === "ko"
            ? "지금은 불러올 수 없습니다(네트워크 또는 요청 제한). 위 링크는 그대로 씁니다."
            : "Could not fetch just now (network or rate limit). The links above still work."}
        </p>
      )}
      {state === "done" && papers.length === 0 && (
        <p className="subtle">{locale === "ko" ? "결과가 없습니다." : "No results."}</p>
      )}
      {papers.length > 0 && (
        <ul className="lookup-list">
          {papers.map((paper) => (
            <li key={paper.paperId}>
              <a
                href={
                  paper.externalIds?.ArXiv
                    ? `https://arxiv.org/abs/${paper.externalIds.ArXiv}`
                    : paper.openAccessPdf?.url ??
                      `https://www.semanticscholar.org/paper/${paper.paperId}`
                }
                rel="noreferrer noopener"
                target="_blank"
              >
                {paper.title}
              </a>
              <span className="subtle">
                {[
                  paper.authors?.[0]?.name,
                  paper.year ?? null,
                  paper.venue || null,
                  paper.citationCount === null
                    ? null
                    : `${paper.citationCount.toLocaleString()}${locale === "ko" ? "회 인용" : " citations"}`,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
