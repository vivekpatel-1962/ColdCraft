"""CLI: python -m scripts.eval_run <resume_path> <company_url> [<company_url> ...] [--out DIR]

End-to-end evaluation harness. Runs every stage from resume extraction onward for
each company, records per-stage timing/model/telemetry and full outputs, flags
weaknesses, then writes report.json + report.html.

The point is diagnosis: see each stage's output side by side across companies so
it's obvious which stage is the weak link.
"""
import json
import logging
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("coldmail.eval")

from app.llm import telemetry  # noqa: E402
from app.models import CandidateProfile, CompanyProfile  # noqa: E402
from app.pipeline.company_intel import (  # noqa: E402
    CompanyScrapeError,
    analyze_company,
    domain_of,
)
from app.pipeline.matcher import deterministic_bridges, match  # noqa: E402
from app.pipeline.planner import plan as make_plan  # noqa: E402
from app.pipeline.resume_analyzer import analyze_resume  # noqa: E402
from app.pipeline.verifier import verify  # noqa: E402
from app.pipeline.writer import _selected_evidence, write  # noqa: E402
from scripts.eval_report import render_html  # noqa: E402


@dataclass
class StageRecord:
    name: str
    ok: bool
    duration_s: float
    output: dict | None = None
    error: str | None = None
    llm_calls: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def run_stage(name: str, fn, *args, **kwargs) -> tuple[StageRecord, object]:
    """Run one stage, capturing timing, LLM telemetry, and any exception."""
    telemetry.drain()  # isolate this stage's calls
    t0 = time.monotonic()
    try:
        result = fn(*args, **kwargs)
        rec = StageRecord(name=name, ok=True, duration_s=round(time.monotonic() - t0, 2),
                          llm_calls=[c.as_dict() for c in telemetry.drain()])
        log.info("stage %-18s OK   %.1fs", name, rec.duration_s)
        return rec, result
    except Exception as e:
        rec = StageRecord(name=name, ok=False, duration_s=round(time.monotonic() - t0, 2),
                          error=f"{type(e).__name__}: {e}",
                          llm_calls=[c.as_dict() for c in telemetry.drain()])
        log.error("stage %-18s FAIL %.1fs — %s", name, rec.duration_s, rec.error)
        log.debug(traceback.format_exc())
        return rec, None


# ---------- weakness detection (what the report highlights) ----------

def audit_resume(profile: CandidateProfile) -> list[str]:
    w = []
    vague = [c.id for c in profile.claims if c.strength.value == "vague"]
    if vague:
        w.append(f"{len(vague)} vague claim(s): {', '.join(vague)} — no metric, weak for the planner")
    if not any(c.achievement for c in profile.claims):
        w.append("no claim has an achievement/outcome — emails will lack impact statements")
    quant = sum(1 for c in profile.claims if c.strength.value == "quantified")
    if quant < 2:
        w.append(f"only {quant} quantified claim(s) — thin evidence base")
    return w


def audit_company(company: CompanyProfile, tier: str, manifest: list) -> list[str]:
    w = []
    if tier != "rich":
        w.append(f"profile_tier={tier} — thin scrape, ledger may be incomplete")
    if len(company.facts) < 5:
        w.append(f"only {len(company.facts)} facts extracted — summarizer under-harvested")
    cats = {f.category.value for f in company.facts}
    if len(cats) < 3:
        w.append(f"facts span only {len(cats)} categories ({', '.join(sorted(cats))}) — narrow ledger")
    if not company.tech_signals:
        w.append("no tech_signals — matcher loses stack-overlap signal")
    if not company.hiring_signals:
        w.append("no hiring_signals — matcher loses the strongest relevance signal")
    jina = sum(1 for m in manifest if m.get("method") == "jina")
    if jina:
        w.append(f"{jina} page(s) needed the JS-render fallback")
    thin = [m["url"] for m in manifest if m.get("status") != "ok"]
    if thin:
        w.append(f"{len(thin)} page(s) returned thin/error")
    return w


def audit_match(overlaps, det_bridges, profile, company) -> list[str]:
    w = []
    if overlaps.fit_score < 50:
        w.append(f"low fit_score={overlaps.fit_score}")
    if len(overlaps.overlaps) < 3:
        w.append(f"only {len(overlaps.overlaps)} overlap(s) ranked — weak bridge pool")
    if not det_bridges:
        w.append("deterministic pass found 0 bridges — skill_aliases.yaml missed this domain")
    top = overlaps.overlaps[0].score if overlaps.overlaps else 0
    if top < 0.7:
        w.append(f"best overlap only {top:.2f} — no strong anchor for the angle")
    # IDs must exist
    cids = {c.id for c in profile.claims}
    fids = {f.id for f in company.facts}
    bad = [f"{o.claim_id}x{o.fact_id}" for o in overlaps.overlaps
           if o.claim_id not in cids or o.fact_id not in fids]
    if bad:
        w.append(f"HALLUCINATED IDs in overlaps: {', '.join(bad)}")
    return w


def audit_plan(plan, overlaps) -> list[str]:
    w = []
    if len(plan.bridges) < 2:
        w.append(f"only {len(plan.bridges)} bridge(s) — plan wants 2-3")
    if not plan.excluded_notable:
        w.append("excluded_notable empty — planner skipped the focus-forcing step")
    if not plan.banned_phrases:
        w.append("banned_phrases empty — writer has no style guardrail")
    ranked = {(o.claim_id, o.fact_id) for o in overlaps.overlaps}
    off = [f"{b.claim_id}x{b.fact_id}" for b in plan.bridges if (b.claim_id, b.fact_id) not in ranked]
    if off:
        w.append(f"bridge(s) not from ranked overlaps: {', '.join(off)}")
    return w


def audit_draft(draft, report, plan) -> list[str]:
    w = []
    if not report.grounded:
        bad = [c.sentence for c in report.claim_checks if not c.supported]
        w.append(f"UNGROUNDED: {len(bad)} unsupported sentence(s)")
    if not report.within_word_target:
        w.append(f"word_count={report.word_count} outside 90-140")
    if report.banned_hits:
        w.append(f"used banned phrases: {', '.join(report.banned_hits)}")
    if report.ai_tells:
        w.append(f"AI-tells: {', '.join(report.ai_tells)}")
    if report.opener_repetition:
        w.append(report.opener_repetition)
    # did the writer actually use every bridge's evidence?
    body = draft.body.lower()
    if len(draft.subject.split()) > 8:
        w.append(f"subject is {len(draft.subject.split())} words (target <= 8)")
    if "hope this" in body or "reaching out" in body:
        w.append("classic cold-email filler detected")
    return w


# ---------- main ----------

def eval_company(url: str, profile: CandidateProfile, history: list[str]) -> dict:
    """Run stages 2-6 for one company. Returns a dict for the report."""
    entry: dict = {"url": url, "domain": domain_of(url), "stages": [], "warnings": {}}

    rec, res = run_stage("company_intel", analyze_company, url, None)
    entry["stages"].append(rec)
    if not rec.ok:
        return entry
    _cp_id, company, scrape = res
    manifest = [m.model_dump() for m in scrape.manifest]
    rec.output = {
        "tier": scrape.tier.value,
        "pages": len(scrape.pages),
        "total_chars": scrape.total_chars,
        "manifest": manifest,
        "profile": company.model_dump(mode="json"),
    }
    rec.warnings = audit_company(company, scrape.tier.value, manifest)
    entry["company"] = company.model_dump(mode="json")

    det = deterministic_bridges(profile, company)
    rec_m, overlaps = run_stage("matcher", match, profile, company)
    entry["stages"].append(rec_m)
    if not rec_m.ok:
        return entry
    rec_m.output = {
        "deterministic_bridges": [
            {"claim_id": b.claim_id, "fact_id": b.fact_id, "shared": b.shared} for b in det
        ],
        "overlaps": overlaps.model_dump(mode="json"),
    }
    rec_m.warnings = audit_match(overlaps, det, profile, company)

    rec_p, plan = run_stage("planner", make_plan, profile, company, overlaps)
    entry["stages"].append(rec_p)
    if not rec_p.ok:
        return entry
    rec_p.output = plan.model_dump(mode="json")
    rec_p.warnings = audit_plan(plan, overlaps)

    rec_w, draft = run_stage("writer", write, plan, profile, company)
    entry["stages"].append(rec_w)
    if not rec_w.ok:
        return entry
    claims, facts = _selected_evidence(plan, profile, company)
    rec_w.output = {
        "draft": draft.model_dump(mode="json"),
        "closed_world": {"claims": [c.id for c in claims], "facts": [f.id for f in facts]},
    }

    rec_v, report = run_stage("verifier", verify, draft, profile, company, plan, history)
    entry["stages"].append(rec_v)
    if rec_v.ok:
        rec_v.output = report.model_dump(mode="json")
        rec_v.warnings = audit_draft(draft, report, plan)
        entry["verdict"] = report.verdict.value
        entry["fit_score"] = overlaps.fit_score
        history.append(draft.opening_line)
    return entry


def main() -> None:
    args = [a for a in sys.argv[1:]]
    out_dir = Path("../data/eval")
    if "--out" in args:
        i = args.index("--out")
        out_dir = Path(args[i + 1])
        del args[i:i + 2]
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)

    resume_path, urls = Path(args[0]), args[1:]
    if not resume_path.exists():
        print(f"Resume not found: {resume_path}")
        sys.exit(1)
    out_dir = (Path(__file__).resolve().parent.parent / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    report: dict = {"resume": str(resume_path), "companies": [], "started": time.strftime("%Y-%m-%d %H:%M:%S")}

    # ---- stage 1: resume ----
    log.info("=== resume extraction ===")
    rec, res = run_stage("resume_analyzer", analyze_resume, resume_path)
    if not rec.ok:
        print(f"Resume stage failed: {rec.error}")
        sys.exit(2)
    _pid, profile = res
    rec.output = profile.model_dump(mode="json")
    rec.warnings = audit_resume(profile)
    report["resume_stage"] = rec
    report["profile"] = profile.model_dump(mode="json")

    # ---- stages 2-6 per company ----
    history: list[str] = []
    for url in urls:
        log.info("=== %s ===", url)
        report["companies"].append(eval_company(url, profile, history))

    # ---- write outputs ----
    def enc(o):
        if isinstance(o, StageRecord):
            return {"name": o.name, "ok": o.ok, "duration_s": o.duration_s, "output": o.output,
                    "error": o.error, "llm_calls": o.llm_calls, "warnings": o.warnings}
        raise TypeError(type(o))

    (out_dir / "report.json").write_text(json.dumps(report, indent=2, default=enc), encoding="utf-8")
    html = render_html(json.loads(json.dumps(report, default=enc)))
    (out_dir / "report.html").write_text(html, encoding="utf-8")

    print(f"\nReport written:\n  {out_dir / 'report.html'}\n  {out_dir / 'report.json'}")
    for c in report["companies"]:
        warns = sum(len(s.warnings) for s in c["stages"])
        print(f"  {c['domain']:<20} verdict={c.get('verdict','-'):<7} fit={c.get('fit_score','-'):<4} warnings={warns}")


if __name__ == "__main__":
    main()
