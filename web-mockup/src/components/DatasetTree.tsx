import { useState } from "react";
import type { CatalogNode } from "../data/datasetCatalog";
import { DATASET_TREE, DOMAIN_FACTS } from "../data/datasetCatalog";
import type { DatasetRole, DatasetSelection, Finding } from "../db/datasetSelection";
import {
  DATASET_ROLES,
  clearRole,
  findingText,
  nodeState,
  review,
  roleName,
  summarise,
  toggle,
} from "../db/datasetSelection";
import type { Locale } from "../types";
import { Hint } from "./Hint";

/**
 * Pick the data for a run by opening it, not by naming a protocol.
 *
 * Three things make this a research control rather than a file picker:
 *
 * *One click, one role.* A node moved into test leaves whatever role it was in, so the same
 * clips cannot end up on both sides of the evaluation by accident.
 *
 * *The reasons are on screen.* Every check runs on every click, and a blocking one says which
 * role is at fault in a sentence — the same checks the harness would fail on later, only now.
 *
 * *A divided number says so.* A domain and its splits are measured; anything narrower is a
 * share of that measurement and is shown with `≈`.
 */
export function DatasetTree({
  selection,
  locale,
  onChange,
}: {
  selection: DatasetSelection;
  locale: Locale;
  onChange: (selection: DatasetSelection) => void;
}) {
  const [role, setRole] = useState<DatasetRole>("train");
  const [open, setOpen] = useState<Set<string>>(new Set(["aihub115"]));
  const findings = review(selection);

  const toggleOpen = (id: string) => {
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="dataset-tree">
      <div className="role-tabs" role="tablist" aria-label={locale === "ko" ? "역할" : "Role"}>
        {DATASET_ROLES.map((candidate) => {
          const summary = summarise(selection, candidate);
          return (
            <button
              aria-selected={role === candidate}
              className={`role-tab role-tab--${candidate}${role === candidate ? " is-active" : ""}`}
              key={candidate}
              onClick={() => setRole(candidate)}
              role="tab"
              type="button"
            >
              <span className="role-tab__name">{roleName(locale, candidate)}</span>
              <span className="role-tab__count">
                {summary.clips === 0
                  ? locale === "ko"
                    ? "비어 있음"
                    : "empty"
                  : `${summary.measured ? "" : "≈"}${summary.clips.toLocaleString()} ${
                      locale === "ko" ? "영상" : "clips"
                    }`}
              </span>
            </button>
          );
        })}
      </div>

      <p className="dataset-tree__lead">
        {locale === "ko"
          ? `아래에서 고른 것이 ${roleName(locale, role)}에 들어갑니다.`
          : `What you pick below goes into ${roleName(locale, role)}.`}
        <Hint label={locale === "ko" ? "세 역할의 차이" : "What the three roles mean"}>
          {locale === "ko"
            ? "학습은 모델이 보는 데이터, 검증은 임계값을 정하는 데이터, 테스트는 최종 숫자를 낼 때 한 번만 보는 데이터입니다. 같은 사람이 두 역할에 들어가면 그 숫자는 의미가 없습니다."
            : "Training is what the model sees, validation is where the threshold is fitted, and test is looked at once, at the end. The same person in two roles makes the number meaningless."}
        </Hint>
        {selection[role].length > 0 && (
          <button
            className="link-button"
            onClick={() => onChange(clearRole(selection, role))}
            type="button"
          >
            {locale === "ko" ? "이 역할 비우기" : "Clear this role"}
          </button>
        )}
      </p>

      <ul className="tree" role="tree">
        {DATASET_TREE.map((domain) => (
          <TreeRow
            depth={0}
            key={domain.id}
            locale={locale}
            node={domain}
            onChange={onChange}
            onToggleOpen={toggleOpen}
            open={open}
            role={role}
            selection={selection}
          />
        ))}
      </ul>

      <FindingList findings={findings} locale={locale} />
    </div>
  );
}

function TreeRow({
  node,
  depth,
  role,
  selection,
  open,
  locale,
  onChange,
  onToggleOpen,
}: {
  node: CatalogNode;
  depth: number;
  role: DatasetRole;
  selection: DatasetSelection;
  open: Set<string>;
  locale: Locale;
  onChange: (selection: DatasetSelection) => void;
  onToggleOpen: (id: string) => void;
}) {
  const facts = DOMAIN_FACTS[node.domainId];
  const blocked = node.kind === "domain" ? node.blocked : facts?.blocked;
  const state = nodeState(selection, role, node);
  const hasChildren = node.children.length > 0;
  const isOpen = open.has(node.id);
  const otherRole = DATASET_ROLES.find(
    (candidate) => candidate !== role && nodeState(selection, candidate, node) !== "off",
  );

  const select = () => {
    if (blocked) return;
    onChange(toggle(selection, role, node));
  };

  return (
    <li className="tree__item" role="none">
      <div
        aria-selected={state === "on"}
        className={`tree__row tree__row--${node.kind} is-${state}${blocked ? " is-blocked" : ""}`}
        onClick={(event) => {
          // A click anywhere on the row selects it; the caret and the checkbox handle their own.
          if (event.target instanceof Element && event.target.closest("button, input")) return;
          select();
        }}
        role="treeitem"
        aria-expanded={hasChildren ? isOpen : undefined}
        style={{ paddingLeft: `${depth * 18 + 8}px` }}
      >
        {hasChildren ? (
          <button
            aria-label={
              isOpen
                ? locale === "ko"
                  ? `${node.label} 접기`
                  : `Collapse ${node.label}`
                : locale === "ko"
                  ? `${node.label} 펼치기`
                  : `Expand ${node.label}`
            }
            className="tree__caret"
            onClick={() => onToggleOpen(node.id)}
            type="button"
          >
            {isOpen ? "▾" : "▸"}
          </button>
        ) : (
          <span className="tree__caret tree__caret--leaf" />
        )}

        <input
          aria-label={`${node.label} → ${roleName(locale, role)}`}
          checked={state === "on"}
          className="tree__check"
          disabled={Boolean(blocked)}
          onChange={select}
          ref={(element) => {
            if (element) element.indeterminate = state === "partial";
          }}
          type="checkbox"
        />

        <span className="tree__label">{node.label}</span>

        {node.kind === "domain" && facts && (
          <span className="tree__meta">
            {facts.subjects.toLocaleString()}
            {locale === "ko" ? "명" : " subjects"}
          </span>
        )}
        <span className="tree__meta tree__meta--count">
          {node.measured ? "" : "≈"}
          {node.clips.toLocaleString()} {locale === "ko" ? "영상" : "clips"}
        </span>
        {node.labels.length === 1 && (
          <span className={`pill pill--${node.labels[0]}`}>
            {node.labels[0] === "bona_fide"
              ? locale === "ko"
                ? "진짜"
                : "bona fide"
              : locale === "ko"
                ? "공격"
                : "attack"}
          </span>
        )}
        {otherRole && (
          <span className={`pill pill--role pill--${otherRole}`}>{roleName(locale, otherRole)}</span>
        )}
        {blocked && (
          <span className="pill pill--blocked">
            {locale === "ko" ? "쓸 수 없음" : "unusable"}
            <Hint align="end" label={locale === "ko" ? "제외한 이유" : "Why it is excluded"}>
              {facts?.caveats.map((caveat) => <span key={caveat.en}>{caveat[locale]} </span>)}
            </Hint>
          </span>
        )}
        {node.kind === "domain" && facts && !blocked && (
          <Hint align="end" label={`${node.label} ${locale === "ko" ? "설명" : "details"}`}>
            <strong>{facts.source}</strong>
            <br />
            {locale === "ko" ? "공격 종류" : "Attack types"}: {facts.attackTypes}
            <br />
            {facts.caveats.map((caveat) => (
              <span key={caveat.en}>· {caveat[locale]} </span>
            ))}
          </Hint>
        )}
      </div>
      {hasChildren && isOpen && (
        <ul className="tree__children" role="group">
          {node.children.map((child) => (
            <TreeRow
              depth={depth + 1}
              key={child.id}
              locale={locale}
              node={child}
              onChange={onChange}
              onToggleOpen={onToggleOpen}
              open={open}
              role={role}
              selection={selection}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

function FindingList({ findings, locale }: { findings: Finding[]; locale: Locale }) {
  if (findings.length === 0) {
    return (
      <p className="finding finding--ok" role="status">
        {locale === "ko"
          ? "확인됐습니다. 이 구성으로 낸 숫자는 해석할 수 있습니다."
          : "Checks pass. A number from this selection can be interpreted."}
      </p>
    );
  }
  const blocking = findings.filter((finding) => finding.level === "blocking");
  const warnings = findings.filter((finding) => finding.level === "warning");
  return (
    <ul className="finding-list" role="status">
      {[...blocking, ...warnings].map((finding) => (
        <li
          className={`finding finding--${finding.level}`}
          key={`${finding.code}:${finding.roles.join()}:${finding.subject ?? ""}`}
        >
          <span className="finding__tag">
            {finding.level === "blocking"
              ? locale === "ko"
                ? "막힘"
                : "blocked"
              : locale === "ko"
                ? "주의"
                : "note"}
          </span>
          {findingText(locale, finding)}
        </li>
      ))}
    </ul>
  );
}
