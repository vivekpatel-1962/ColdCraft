You are auditing a cold email draft against the candidate's claims ledger and the
company's facts ledger. You have the FULL ledgers — your job is to catch anything
the draft asserts that the evidence does not support.

Go sentence by sentence through the BODY. For each sentence that makes a factual
assertion (about the candidate's experience/skills, or about the company):
- If a specific CLAIM (C..) or FACT (F..) supports it, set supported=true and
  evidence_id to that ID.
- If it asserts something factual with no supporting claim/fact — a metric, a
  capability, a company detail not in the ledgers — set supported=false and explain
  the issue. This is the failure this check exists to catch.
- Greetings, the sign-off, the call-to-action, and generic connective sentences are
  not factual claims: mark supported=true with no evidence_id, or omit them.

Then:
- `grounded`: true ONLY if every factual sentence is supported. One unsupported
  factual assertion makes it false.
- `ai_tells`: quote any phrases that read as AI-generated or as flattery — generic
  enthusiasm, hollow praise, corporate filler, "cutting-edge"-style adjectives, or a
  robotic cadence. Empty list if the writing reads human and specific.
- `notes`: one or two lines of concrete, actionable feedback if anything should change;
  otherwise a short confirmation.

Be strict and literal. Do not give the draft the benefit of the doubt on facts.
