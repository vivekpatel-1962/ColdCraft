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

Contact and links (from the header and the "LINKS EMBEDDED IN THE RESUME" block):
- `contact.email`, `contact.phone`, `contact.location` (city, country as written).
- `contact.linkedin`: the linkedin.com profile URL. `contact.github`: the GitHub
  PROFILE URL (github.com/<user>), NOT a single repository. `contact.portfolio`: a
  personal website if present.
- A repository URL that clearly belongs to one project (the "near text" hint names
  the project, or the path matches the project name) goes on THAT claim's `link`
  field — not in contact. A generic github.com/<user> profile is contact.github.
- Never invent or guess a URL. Only use links that actually appear in the resume.
- `status`: one phrase capturing the candidate's current situation if the resume
  makes it clear (e.g. "final-year CS undergrad, graduating 2027"). Null otherwise.
