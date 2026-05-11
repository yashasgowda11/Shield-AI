# Past Contracts Corpus

Build 8–10 mock past contracts here (Day 1 PM, Person B).

Each file: one JSON document with shape:

```json
{
  "id": "C-0001",
  "vendor": "Acme Corp",
  "type": "MSA",
  "parties": ["Acme Corp", "Customer Inc."],
  "signed_at": "2024-03-15",
  "clauses": [
    {"number": "1.1", "title": "Scope", "text": "..."},
    {"number": "7.2", "title": "Liability", "text": "..."}
  ],
  "risk_findings": [
    {"clause_ref": "7.2", "risk": "Unlimited liability", "severity": "High"}
  ]
}
```

