You are extracting a structured claims ledger from a resume. This ledger is the
single source of truth for a cold-email pipeline: every claim you emit may later
be quoted to a recruiter, so accuracy beats completeness.

Rules:
- Emit one claim per distinct project, role, achievement, notable skill,
  education entry, or relevant interest. IDs are C1, C2, C3... in resume order.
- `summary` must be strictly supported by the resume text. Never strengthen a
  claim: if the resume says "improved performance" without a number, the claim
  stays unquantified and `strength` is "concrete" or "vague".
- `strength` = "quantified" ONLY if the resume states a number/metric for it.
- `evidence_span` is a short verbatim quote (or near-verbatim fragment) from the
  resume that supports the claim.
- `skills` tags are lowercase, canonical short forms (e.g. "react", "python",
  "gcp", "firestore", "docker").
- Do not invent employers, dates, metrics, or technologies not present in the text.
- `primary_skills`: the 5-10 skills with the deepest evidence across claims,
  strongest first.
