"""Renders the eval harness output as a single self-contained HTML page.

One section per stage per company, with the raw output, the LLM telemetry, and an
explicit weaknesses list — so it's obvious at a glance which stage is the weak link.
"""
import html
import json

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#0f1115;color:#e6e8ee;font:15px/1.6 ui-sans-serif,system-ui,"Segoe UI",Roboto,sans-serif}
@media(prefers-color-scheme:light){body{background:#f7f8fa;color:#14171f}
 .card,.stage{background:#fff!important;border-color:#dde1e9!important}
 pre{background:#f0f2f6!important}
 th{color:#5b6478!important}}
.wrap{max-width:1100px;margin:0 auto;padding:28px 20px 80px}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.02em}
h2{font-size:20px;margin:32px 0 10px;padding-bottom:6px;border-bottom:1px solid #2a2f3a}
h3{font-size:16px;margin:18px 0 8px}
h4{font-size:13px;margin:12px 0 6px;text-transform:uppercase;letter-spacing:.06em;color:#8b93a7}
.muted{color:#8b93a7}.small{font-size:13px}
.card,.stage{background:#171a21;border:1px solid #2a2f3a;border-radius:10px;padding:14px 16px;margin:12px 0}
.stage.fail{border-color:#f87171}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.badge{font-size:11px;padding:2px 8px;border-radius:20px;border:1px solid #2a2f3a}
.ok{color:#4ade80;border-color:#4ade80}.bad{color:#f87171;border-color:#f87171}
.warn{color:#fbbf24;border-color:#fbbf24}.info{color:#6ea8fe;border-color:#6ea8fe}
pre{background:#1e222b;border-radius:8px;padding:10px 12px;overflow-x:auto;font-size:12px;
 font-family:ui-monospace,Consolas,monospace;white-space:pre-wrap;word-break:break-word}
table{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #2a2f3a;vertical-align:top}
th{color:#8b93a7;font-weight:500}
ul{margin:6px 0;padding-left:20px}
.weak{background:rgba(251,191,36,.10);border-left:3px solid #fbbf24;padding:8px 12px;border-radius:0 6px 6px 0;margin:8px 0}
.weak.none{background:rgba(74,222,128,.08);border-left-color:#4ade80}
.id{background:#1e222b;border-radius:4px;padding:0 5px;font-size:11px;color:#6ea8fe;
 font-family:ui-monospace,monospace;margin-right:5px}
.email{background:#1e222b;border-radius:8px;padding:14px 16px;white-space:pre-wrap;font-size:14px;line-height:1.65}
details summary{cursor:pointer;font-size:13px;color:#8b93a7;margin:6px 0}
.kpi{display:flex;gap:22px;flex-wrap:wrap;margin:10px 0}
.kpi div{text-align:center}.kpi .n{font-size:26px;font-weight:600;color:#6ea8fe;display:block}
.kpi .l{font-size:11px;color:#8b93a7;text-transform:uppercase;letter-spacing:.05em}
"""


def e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _warnings_block(warnings: list[str], label="Weaknesses") -> str:
    if not warnings:
        return f'<div class="weak none small">✓ {label}: none detected</div>'
    items = "".join(f"<li>{e(w)}</li>" for w in warnings)
    return f'<div class="weak small"><b>{label} ({len(warnings)})</b><ul>{items}</ul></div>'


def _llm_block(calls: list[dict]) -> str:
    if not calls:
        return ""
    rows = "".join(
        f"<tr><td>{e(c['stage'])}</td><td>{e(c['model'])}</td><td>key #{e(c['key_index'])}</td>"
        f"<td>{e(c['duration_s'])}s</td><td>{e(c['input_chars'])} chars</td>"
        f"<td>{'rot ' + str(c['quota_rotations']) if c['quota_rotations'] else ''}"
        f"{' retry ' + str(c['transient_retries']) if c['transient_retries'] else ''}</td>"
        f"<td>{'<span class=badge.ok>ok</span>' if c['ok'] else e(c['error'])}</td></tr>"
        for c in calls
    )
    return (f'<details><summary>LLM telemetry ({len(calls)} call(s))</summary><table>'
            f"<tr><th>stage</th><th>model</th><th>key</th><th>time</th><th>input</th>"
            f"<th>retries</th><th>result</th></tr>{rows}</table></details>")


def _stage_header(s: dict) -> str:
    status = '<span class="badge ok">OK</span>' if s["ok"] else '<span class="badge bad">FAIL</span>'
    return (f'<div class="row"><h3 style="margin:0">{e(s["name"])}</h3>{status}'
            f'<span class="muted small">{e(s["duration_s"])}s</span></div>')


def _render_resume(stage: dict, profile: dict) -> str:
    claims = "".join(
        f'<tr><td><span class="id">{e(c["id"])}</span></td><td class="small">{e(c["type"])}</td>'
        f'<td><span class="badge {"ok" if c["strength"]=="quantified" else "warn" if c["strength"]=="vague" else "info"}">'
        f'{e(c["strength"])}</span></td><td><b>{e(c["name"])}</b><br><span class="small muted">{e(c["summary"])}</span>'
        f'{"<br><span class=small>outcome: " + e(c["achievement"]) + "</span>" if c.get("achievement") else ""}</td></tr>'
        for c in profile["claims"]
    )
    return f"""<div class="stage{'' if stage['ok'] else ' fail'}">
      {_stage_header(stage)}
      <p class="small muted">{e(profile['full_name'])} — {e(profile['headline'])}</p>
      <p class="small"><b>Primary skills:</b> {e(', '.join(profile['primary_skills']))}</p>
      <table><tr><th>ID</th><th>type</th><th>strength</th><th>claim</th></tr>{claims}</table>
      {_warnings_block(stage.get('warnings', []))}
      {_llm_block(stage.get('llm_calls', []))}
    </div>"""


def _render_company_stage(s: dict) -> str:
    o = s.get("output") or {}
    body = ""
    if not s["ok"]:
        body = f'<pre>{e(s["error"])}</pre>'
    elif s["name"] == "company_intel":
        p = o["profile"]
        facts = "".join(
            f'<tr><td><span class="id">{e(f["id"])}</span></td><td class="small muted">{e(f["category"])}</td>'
            f'<td>{e(f["statement"])}<br><span class="small muted">“{e(f["quote"])[:110]}” — '
            f'<a href="{e(f["source_url"])}" style="color:#6ea8fe">src</a></span></td></tr>'
            for f in p["facts"])
        man = "".join(
            f'<tr><td><span class="badge {"ok" if m["status"]=="ok" else "warn"}">{e(m["status"])}</span></td>'
            f'<td class="small">{e(m["method"])}</td><td class="small">{e(m["char_count"])}</td>'
            f'<td class="small">{e(m["priority"])}</td><td class="small muted">{e(m["url"])}</td></tr>'
            for m in o["manifest"])
        body = f"""<div class="kpi">
            <div><span class="n">{e(o['tier'])}</span><span class="l">tier</span></div>
            <div><span class="n">{e(o['pages'])}</span><span class="l">pages</span></div>
            <div><span class="n">{e(o['total_chars'])}</span><span class="l">chars</span></div>
            <div><span class="n">{len(p['facts'])}</span><span class="l">facts</span></div></div>
          <p class="small"><b>{e(p['name'])}</b> — {e(p['one_liner'])}</p>
          <table><tr><th>ID</th><th>cat</th><th>fact</th></tr>{facts}</table>
          <p class="small"><b>Tech:</b> {e(', '.join(p['tech_signals']) or '—')}</p>
          <p class="small"><b>Hiring:</b> {e(', '.join(p['hiring_signals']) or '—')}</p>
          <details><summary>scrape manifest</summary><table>
            <tr><th>status</th><th>method</th><th>chars</th><th>bucket</th><th>url</th></tr>{man}</table></details>"""
    elif s["name"] == "matcher":
        ov = o["overlaps"]
        det = "".join(f'<li class="small"><span class="id">{e(b["claim_id"])}×{e(b["fact_id"])}</span>'
                      f'shared: {e(", ".join(b["shared"]))}</li>' for b in o["deterministic_bridges"])
        rows = "".join(
            f'<tr><td><b>{o2["score"]:.2f}</b></td><td><span class="id">{e(o2["claim_id"])}×{e(o2["fact_id"])}</span></td>'
            f'<td class="small muted">{e(o2["kind"])}</td><td class="small">{e(o2["rationale"])}</td></tr>'
            for o2 in ov["overlaps"])
        body = f"""<div class="kpi"><div><span class="n">{e(ov['fit_score'])}</span><span class="l">fit /100</span></div>
            <div><span class="n">{len(ov['overlaps'])}</span><span class="l">ranked</span></div>
            <div><span class="n">{len(o['deterministic_bridges'])}</span><span class="l">det. bridges</span></div></div>
          <p class="small muted">{e(ov['fit_summary'])}</p>
          <table><tr><th>score</th><th>bridge</th><th>kind</th><th>rationale</th></tr>{rows}</table>
          <details><summary>deterministic pass (hints fed to the LLM)</summary><ul>{det or '<li class="small">none</li>'}</ul></details>"""
    elif s["name"] == "planner":
        br = "".join(f'<li class="small"><span class="id">{e(b["claim_id"])}×{e(b["fact_id"])}</span>{e(b["point"])}</li>'
                     for b in o["bridges"])
        ex = "".join(f"<li class='small'>{e(x)}</li>" for x in o.get("excluded_notable", []))
        body = f"""<p><b>Angle:</b> {e(o['angle'])}</p>
          <p class="small"><b>Hook:</b> {e(o['opening_hook'])}</p>
          <h4>bridges</h4><ul>{br}</ul>
          <p class="small"><b>CTA:</b> {e(o['call_to_action'])}</p>
          <p class="small"><b>Tone:</b> {e(o['tone'])} · <b>target:</b> {e(o['word_target'])} words</p>
          <h4>excluded_notable</h4><ul>{ex or "<li class='small bad'>empty</li>"}</ul>
          <details><summary>banned phrases ({len(o.get('banned_phrases', []))})</summary>
            <p class="small muted">{e('; '.join(o.get('banned_phrases', [])))}</p></details>"""
    elif s["name"] == "writer":
        d = o["draft"]
        cw = o["closed_world"]
        body = f"""<p class="small muted">closed world: claims {e(', '.join(cw['claims']))} · facts {e(', '.join(cw['facts']))}
            — the writer saw nothing else</p>
          <p><b>Subject:</b> {e(d['subject'])}</p>
          <div class="email">{e(d['body'])}</div>"""
    elif s["name"] == "verifier":
        v = o
        checks = "".join(
            f'<tr><td>{"✓" if c["supported"] else "✗"}</td>'
            f'<td>{("<span class=id>" + e(c["evidence_id"]) + "</span>") if c.get("evidence_id") else ""}</td>'
            f'<td class="small">{e(c["sentence"])}{("<br><em class=bad>" + e(c["issue"]) + "</em>") if c.get("issue") else ""}</td></tr>'
            for c in v["claim_checks"])
        vb = {"pass": "ok", "revise": "warn", "fail": "bad"}.get(v["verdict"], "info")
        fmt = ""
        if v.get("format_issues"):
            items = "".join(f"<li>{e(x)}</li>" for x in v["format_issues"])
            fmt = f'<div class="weak small"><b>Format issues</b><ul>{items}</ul></div>'
        body = f"""<div class="row"><span class="badge {vb}">{e(v['verdict']).upper()}</span>
            <span class="small">grounded={e(v['grounded'])} · {e(v['word_count'])} words
            {'(ok)' if v['within_word_target'] else '(OUT OF RANGE)'}</span></div>
          {fmt}
          <table><tr><th></th><th>evidence</th><th>sentence</th></tr>{checks}</table>
          <p class="small muted">{e(v['notes'])}</p>"""

    return (f'<div class="stage{"" if s["ok"] else " fail"}">{_stage_header(s)}{body}'
            f'{_warnings_block(s.get("warnings", []))}{_llm_block(s.get("llm_calls", []))}</div>')


def render_html(report: dict) -> str:
    prof = report["profile"]
    parts = [f"""<!doctype html><html><head><meta charset="utf-8">
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <title>coldmail — pipeline eval</title><style>{CSS}</style></head><body><div class="wrap">
      <h1>coldmail — pipeline evaluation</h1>
      <p class="muted small">{e(report['started'])} · resume: <code>{e(report['resume'])}</code>
       · {len(report['companies'])} companies</p>"""]

    # summary table
    rows = "".join(
        f'<tr><td><b>{e(c["domain"])}</b></td>'
        f'<td>{e(c.get("fit_score", "—"))}</td>'
        f'<td><span class="badge {{"pass":"ok","revise":"warn","fail":"bad"}}.get(c.get("verdict"),"info")">'
        f'{e(c.get("verdict", "—"))}</span></td>'
        f'<td>{sum(len(s.get("warnings", [])) for s in c["stages"])}</td>'
        f'<td>{sum(1 for s in c["stages"] if not s["ok"])}</td>'
        f'<td class="small muted">{round(sum(s["duration_s"] for s in c["stages"]), 1)}s</td></tr>'
        for c in report["companies"])
    # fix the f-string class interpolation above by rebuilding cleanly
    rows = ""
    for c in report["companies"]:
        vb = {"pass": "ok", "revise": "warn", "fail": "bad"}.get(c.get("verdict"), "info")
        warns = sum(len(s.get("warnings", [])) for s in c["stages"])
        fails = sum(1 for s in c["stages"] if not s["ok"])
        secs = round(sum(s["duration_s"] for s in c["stages"]), 1)
        rows += (f'<tr><td><b>{e(c["domain"])}</b></td><td>{e(c.get("fit_score","—"))}</td>'
                 f'<td><span class="badge {vb}">{e(c.get("verdict","—"))}</span></td>'
                 f'<td>{warns}</td><td>{fails}</td><td class="small muted">{secs}s</td></tr>')

    parts.append(f"""<div class="card"><h3 style="margin-top:0">Summary</h3><table>
      <tr><th>company</th><th>fit</th><th>verdict</th><th>weaknesses</th><th>stage failures</th><th>time</th></tr>
      {rows}</table></div>""")

    parts.append("<h2>Stage 1 — Resume extraction</h2>")
    parts.append(_render_resume(report["resume_stage"], prof))

    for c in report["companies"]:
        parts.append(f'<h2>{e(c["domain"])} <span class="muted small">{e(c["url"])}</span></h2>')
        if not c["stages"]:
            parts.append('<div class="stage fail"><p>no stages ran</p></div>')
        for s in c["stages"]:
            parts.append(_render_company_stage(s))

    parts.append("</div></body></html>")
    return "".join(parts)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    Path(sys.argv[2]).write_text(render_html(data), encoding="utf-8")
    print(f"wrote {sys.argv[2]}")
