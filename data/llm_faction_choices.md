# LLM Faction Choices — DDM

Choix de faction/champion des 10 profils LLM (prompt_standard.md + ddm_context.md).

| Modèle | Rang | Faction principale | Champion | Second choix | Champion alt |
|--------|------|-------------------|----------|--------------|--------------|
| Gemini | F | 4 — Cyborgs | D — Architecte Zero | 3 — Reptiliens | B — Reine Nythra |
| Haiku 4.5 | F | 7 — Égyptiens | D — Serapia | 3 — Reptiliens | B — Reine Nythra |
| GLM-4 | E | 3 — Reptiliens | A — Seigneur Pyroscale | 6 — Lycans | E — Gardien Céleste |
| Mistral | E | 4 — Cyborgs | B — Analyste du Code | 1 — Humains | A — Archonte du Bastion |
| Grok | E | 5 — Orcs | A — Chef de Guerre Grok | 2 — Démons | C — Incarnation de la Rage |
| Qwen3 | D | 8 — Abominations | E — Manipulateur d'Espace | 8 — Abominations | C — Chaos Élémentaire |
| ChatGPT | D | 4 — Cyborgs | B — Analyste du Code | 3 — Reptiliens | B — Reine Nythra |
| Deepseek | D | 6 — Lycans | A — Alpha Lunaire | 3 — Reptiliens | B — Reine Nythra |
| Sonnet 4.6 | C | 4 — Cyborgs | B — Analyste du Code | 7 — Égyptiens | D — Serapia |
| Opus 4.7 | B | 4 — Cyborgs | D — Architecte Zero | 3 — Reptiliens | D — Grande Sorcière Venina |

## Observations

- **Reptiliens 3** = alternatif favori (5 votes sur 10, toujours avec Nythra sauf Opus qui prend Venina)
- **Humains 1** et **Démons 2** n'apparaissent qu'en second choix (Mistral + Grok) — jamais en principal
- **Qwen3** reste dans les Abominations même en alternatif (change juste de champion C)
- **Cyborgs 4** dominent le choix principal (5 modèles) mais disparaissent complètement en alternatif
- **Analyste du Code (4B)** = champion le plus choisi (Mistral, ChatGPT, Sonnet)
- **Architecte Zero (4D)** = second champion Cyborg (Gemini, Opus, Grok en principal Orcs)

## Distribution factions (choix principal)

| Faction | Count | Modèles |
|---------|-------|---------|
| 4 — Cyborgs | 5 | Gemini, Mistral, ChatGPT, Sonnet, Opus |
| 3 — Reptiliens | 1 | GLM-4 |
| 5 — Orcs | 1 | Grok |
| 6 — Lycans | 1 | Deepseek |
| 7 — Égyptiens | 1 | Haiku |
| 8 — Abominations | 1 | Qwen3 |
| 1 — Humains | 0 | — |
| 2 — Démons | 0 | — |
