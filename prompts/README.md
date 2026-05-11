# Prompts

Versioned prompt templates. Use semver in filenames so we can roll back if a
later version regresses.

Naming: `<agent>_<version>.txt`

```
extraction_v1.0.0.txt
risk_v1.0.0.txt
risk_v1.1.0.txt   # tweak that improved high-severity recall
compliance_v1.0.0.txt
analytics_v1.0.0.txt
```

Each agent's module hashes the prompt at runtime and writes the hash into
`agent_outputs.prompt_hash` so audit reports can prove which prompt produced
which decision.
