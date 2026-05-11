# Regulations Corpus

Short citation snippets used as supplementary context by the Compliance Agent.

Format: one JSON file per source (`hipaa_regs.json`, `gdpr_regs.json`, etc.).
Each entry:

```json
{
  "citation": "45 CFR 164.504(e)",
  "title": "Business Associate Contracts",
  "text": "A covered entity may permit a business associate to..."
}
```

Optional but useful — judges asking "where did this judgment come from?" can be
shown the actual regulatory text Shield AI cited.
