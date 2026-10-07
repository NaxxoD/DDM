# JAEHA — Matrice empirique curriculum (position × adversaire)

Runs phase 2 analysés : **2**

Valeurs : WR moyen (n = nombre de fois en cette position)

| Pos | claude        | mistral       | grok          | gemini        | chatgpt       | sonnet        | opus          |
|-----|:--------------:|:--------------:|:--------------:|:--------------:|:--------------:|:--------------:|:--------------:|
|  0  | 72.0%(n=1)    | 76.8%(n=1)    |   —           | 76.2%(n=1)    |   —           |   —           |   —           |
|  1  |   —           |   —           |   —           | 79.8%(n=2)    |   —           |   —           | 67.5%(n=1)    |
|  2  |   —           |   —           |   —           |   —           |   —           | 66.5%(n=1)    | 62.5%(n=2)    |
|  3  | 71.2%(n=1)    |   —           | 66.0%(n=1)    |   —           |   —           | 65.8%(n=1)    |   —           |
|  4  |   —           | 70.2%(n=1)    |   —           |   —           | 69.8%(n=2)    |   —           |   —           |
|  5  |   —           |   —           | 75.8%(n=2)    |   —           |   —           | 71.5%(n=1)    |   —           |
|  6  | 72.5%(n=1)    | 69.5%(n=1)    |   —           |   —           | 69.5%(n=1)    |   —           |   —           |

## Meilleure position par adversaire

| Adversaire | Meilleure pos | WR moyen | Runs |
|------------|---------------|----------|------|
| claude     | stage 6       | 72.5%   | 1    |
| mistral    | stage 0       | 76.8%   | 1    |
| grok       | stage 5       | 75.8%   | 2    |
| gemini     | stage 1       | 79.8%   | 2    |
| chatgpt    | stage 4       | 69.8%   | 2    |
| sonnet     | stage 5       | 71.5%   | 1    |
| opus       | stage 1       | 67.5%   | 1    |

## Ordre optimal suggéré (basé sur meilleure position empirique)

```
mistral → gemini → opus → chatgpt → grok → sonnet → claude
```

*Dernière mise à jour : 2026-04-23*
