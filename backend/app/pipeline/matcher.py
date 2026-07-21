"""Stage 3: CandidateProfile x CompanyProfile -> RankedOverlaps.

Two passes, mirroring company_intel's scrape/distil split:
  1. deterministic — generate candidate (claim, fact) bridges by normalized
     skill/keyword overlap (skill_aliases.yaml). Cheap and grounded; it narrows
     the NxM claim/fact space and gives the LLM concrete hints rather than noise.
  2. rubric (LLM)  — score bridges on a relevance rubric and emit RankedOverlaps
     plus one evidence-based fit score. The deterministic pass is hints only; the
     LLM still sees every claim and fact and may surface a bridge we didn't pre-score.
"""
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app.llm.client import complete_json
from app.models import CandidateProfile, Claim, CompanyProfile, Fact, RankedOverlaps

log = logging.getLogger("coldmail.matcher")

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "matcher.md"
ALIAS_PATH = Path(__file__).resolve().parent.parent / "data" / "skill_aliases.yaml"

MAX_BRIDGES = 20  # deterministic shortlist cap handed to the LLM as hints

_WORD = re.compile(r"[a-z0-9\+\#\.]+")


@lru_cache(maxsize=1)
def _alias_map() -> dict[str, str]:
    """alias/canonical (lowercased) -> canonical concept."""
    raw = yaml.safe_load(ALIAS_PATH.read_text(encoding="utf-8")) or {}
    m: dict[str, str] = {}
    for canon, aliases in raw.items():
        canon = canon.lower()
        m[canon] = canon
        for a in aliases or []:
            m[str(a).lower()] = canon
    return m


def _concepts(texts: list[str]) -> set[str]:
    """Normalize a bag of text into canonical concepts via the alias map."""
    amap = _alias_map()
    blob = " ".join(t.lower() for t in texts if t)
    found: set[str] = set()
    # multi-word aliases first (substring match)
    for alias, canon in amap.items():
        if " " in alias and alias in blob:
            found.add(canon)
    # single-token aliases
    for tok in _WORD.findall(blob):
        if tok in amap:
            found.add(amap[tok])
    return found


def _claim_concepts(claim: Claim) -> set[str]:
    return _concepts(list(claim.skills) + [claim.name, claim.summary, claim.achievement or ""])


def _fact_concepts(fact: Fact) -> set[str]:
    return _concepts([fact.statement, fact.quote])


@dataclass
class CandidateBridge:
    claim_id: str
    fact_id: str
    shared: list[str]
    raw: float


def deterministic_bridges(profile: CandidateProfile, company: CompanyProfile) -> list[CandidateBridge]:
    """(claim, fact) pairs sharing >=1 normalized concept, ranked by overlap size
    with a small boost when the claim also hits a company tech signal."""
    tech = _concepts(list(company.tech_signals))
    claim_c = {c.id: _claim_concepts(c) for c in profile.claims}
    bridges: list[CandidateBridge] = []
    for fact in company.facts:
        fc = _fact_concepts(fact)
        if not fc:
            continue
        for claim in profile.claims:
            shared = claim_c[claim.id] & fc
            if not shared:
                continue
            raw = len(shared) + (0.5 if claim_c[claim.id] & tech else 0.0)
            bridges.append(CandidateBridge(claim.id, fact.id, sorted(shared), raw))
    bridges.sort(key=lambda b: b.raw, reverse=True)
    return bridges[:MAX_BRIDGES]


def _render(profile: CandidateProfile, company: CompanyProfile, bridges: list[CandidateBridge]) -> str:
    lines = [f"CANDIDATE: {profile.full_name} — {profile.headline}", "", "CLAIMS:"]
    for c in profile.claims:
        skills = f" (skills: {', '.join(c.skills)})" if c.skills else ""
        lines.append(f"{c.id} [{c.type.value}/{c.strength.value}] {c.name}: {c.summary}{skills}")

    lines += ["", f"COMPANY: {company.name} ({company.domain})", company.one_liner, "", "FACTS:"]
    for f in company.facts:
        lines.append(f"{f.id} [{f.category.value}] {f.statement}")
    if company.tech_signals:
        lines.append("\nTECH SIGNALS: " + ", ".join(company.tech_signals))
    if company.hiring_signals:
        lines.append("HIRING SIGNALS: " + ", ".join(company.hiring_signals))

    if bridges:
        lines += ["", "SUGGESTED BRIDGES (deterministic hints — shared concepts, not final):"]
        for b in bridges:
            lines.append(f"{b.claim_id} x {b.fact_id}  shared: {', '.join(b.shared)}")
    return "\n".join(lines)


def match(profile: CandidateProfile, company: CompanyProfile) -> RankedOverlaps:
    """Full Stage 3: deterministic shortlist -> LLM rubric ranking."""
    bridges = deterministic_bridges(profile, company)
    log.info("deterministic bridges: %d (of %d claims x %d facts)",
             len(bridges), len(profile.claims), len(company.facts))
    system = PROMPT_PATH.read_text(encoding="utf-8")
    return complete_json(
        stage="matcher",
        system=system,
        user=_render(profile, company, bridges),
        schema=RankedOverlaps,
    )
