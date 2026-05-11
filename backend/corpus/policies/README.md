# Policy Corpus

Build 8–10 policy snippets per framework (Day 1 PM, Person B).

One JSON file per framework: `hipaa.json`, `soc2.json`, `gdpr.json`.

Shape:

```json
{
  "framework": "HIPAA",
  "snippets": [
    {
      "requirement": "BAA language",
      "text": "Contracts processing PHI must include a Business Associate Agreement..."
    },
    {
      "requirement": "Breach notification",
      "text": "Breach notification timeline must not exceed 60 days..."
    }
  ]
}
```
