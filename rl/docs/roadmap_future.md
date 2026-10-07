# DDM RL — Roadmap idées futures

> Idées notées pour plus tard, hors priorités immédiates (post-Neosia, post-frontend Phase 4).
> Chaque entrée doit décrire : la valeur ajoutée, le coût, et **quand** la déclencher.

---

## 1. Specialist agents (40 / 13 / 8 variantes)

> Idée née le 2026-05-09 lors de l'investigation Jaeha.

### Concept

Au lieu de 4-5 agents généralistes (Jin/Jio/Cross/Jaeha) entraînés sur draft random,
créer des **agents spécialistes par combo (faction × champion)**.

3 variantes possibles :

| Variante | Nb agents | Spécialisation | Coût training |
|---|--:|---|--:|
| **Lean** | 8 | Par faction (champion random) | 8 × 500k = ~14h |
| **Mid** | 13 | 8 factions + 5 champions | 13 × 500k = ~22h |
| **Deluxe** | 40 | Combo complet (faction × champion) | 40 × 500k = ~70h |

### Valeur ajoutée

1. **Carte empirique du balance** : si f5+B specialist plafonne à 90% WR avec infinite training
   pendant que f3+E plafonne à 35%, on identifie les configs structurellement faibles → outil
   de game design data-driven.

2. **Détection killer counters** : un specialist peut révéler des matchups précis
   (ex: f7+D à 70% global mais 10% contre f1 → f1 hard-counter à f7+D).

3. **Skill ceiling par combo** : mesurer combien chaque combo peut "monter" avec
   training illimité.

4. **Mode draft compétitif** : permet un système type e-sport où chaque joueur
   sélectionne le specialist optimal pour son combo tiré.

5. **Ensemble runtime** : au moment du draft, charger le specialist correspondant.
   Probablement +5-10 pts vs le meilleur généraliste actuel.

### Limitations / risques

- **Pas de transfert** : un specialist f5+B est inutile en f3+E.
- **Maintenance lourde** : 40 checkpoints à re-sync à chaque migration moteur.
- **Diminishing returns** probable après 200-300k steps par specialist.
- **Pas un meilleur sparring** pour les généralistes (random draft les rend déjà robustes).

### Quand le déclencher

- ✅ Quand le moteur est **stable depuis longtemps** (sinon retraining 40 fois)
- ✅ Quand on prépare un **patch balance majeur** et qu'on veut une carte avant/après
- ✅ Quand DDM rentre en **mode compétitif** (tournament, e-sport, tier list, meta)
- ✅ Pour une **publication / blog post** sur le balance d'un jeu via RL
- ❌ Tant que la priorité est gameplay / Neosia / frontend
- ❌ Tant que l'engine évolue encore régulièrement

### Recommandation pratique

Si jamais c'est lancé un jour, commencer par la **variante Lean (8 specialists par faction)**.
Couvre le balance le plus important (factions) pour 14h de compute. Décide ensuite
si on monte au Mid ou Deluxe.

### Implémentation prévue

- Réutiliser `train_ppo.py` avec `--faction-rl X --champion-rl Y` (déjà supporté)
- Adapter `bracket.py` pour gérer 40 candidats (pour l'instant 4 hardcodés)
- Nouveau script `tools/scripts/balance_map.py` pour visualiser la matrice 8×5 des
  WR plafond par specialist

---

## 2. Zenom — meta-agent (ensemble + adaptive)

> Idée née le 2026-05-09 lors de la discussion sur la hiérarchie des agents.
> Initialement nommée Sephira, renommée Zenom.

### Concept

Zenom est le **6e agent RL**, conçu pour être **robuste max contre toute la roster**
existante. Deux versions à explorer (peuvent être faites séparément ou combinées).

### Version A — Ensemble exploiter (pragmatique, ~1 semaine)

Agent entraîné contre la **roster complète en random** :
- greedy bot
- 7 profils LLM scriptés
- Jin / Jio / Cross / Jaeha
- Neosia (si déjà entraîné)
- = jusqu'à 13 adversaires

Chaque épisode tire un opponent aléatoire selon une distribution uniforme (ou
pondérée par difficulté). L'agent apprend **une seule policy robuste à tous**.

**Valeur ajoutée** :
- Pas de matchup faible exploitable par construction
- Champion ultime du bracket (probablement)
- Skill ceiling brut de la pipeline RL pour DDM
- Mode "Insane" pour joueur humain en Phase 4 frontend

**Coût technique** :
- Étendre `train_ppo.py` pour accepter pool d'opponents (mix LLM + RL)
- Mécanisme de hot-swap d'opponent par épisode
- Pour les RL opponents : load checkpoints en mémoire, predict pendant training
- Latence : non triviale (predict d'un PPO opponent ajoute ~1ms par tour)
- Estimé : ~2-3 jours de dev infra + ~1M-1.5M steps de training (~12-20h)

**Limitations** :
- Pas mieux qu'un Jio sur un opponent spécifique (généraliste pur)
- Diminishing returns après ~1M steps probable
- Doit attendre que Neosia existe (sinon roster incomplète)

### Version B — Meta-game adaptive (ambitieuse, ~2-3 semaines)

Agent qui **détecte le type d'adversaire** en début de partie et **adapte sa
stratégie**. Architecture plus complexe que PPO standard.

**Approches possibles** :

1. **LSTM/Transformer policy** : la policy a une mémoire récurrente. Au cours
   des premiers tours, elle observe les patterns adverses (timing d'invocation,
   choix d'attaques, mouvement) et infère implicitement le type d'opponent.

2. **Hierarchical RL** : Zenom a N sub-policies (une par "type" d'opponent
   prédéfini). Une meta-policy choisit la sub-policy active au tour 5-10
   selon les observations accumulées.

3. **Population-based training** : Zenom est en fait un ensemble de policies,
   et un selector apprend à choisir la bonne au runtime.

**Valeur ajoutée vs version A** :
- Vraie adaptation, pas juste robustesse moyenne
- Peut potentiellement battre des opponents spécifiques mieux qu'un specialist
- Recherche pure : démontre qu'un agent peut "lire" un autre agent

**Coût technique** :
- Sortir de stable_baselines3 PPO standard (peut-être passer à RLlib ou custom)
- Architecture neural plus complexe
- Training plus long (LSTM = harder convergence)
- Estimé : ~1-2 semaines de dev + ~2-3M steps de training (~30-40h)

**Limitations** :
- Risque de ne pas converger (LSTM RL est notoirement difficile)
- Évaluation plus complexe (faut tester contre opponents jamais vus)
- Maintenance lourde si l'architecture custom

### Quand le déclencher

- ✅ Après Neosia (pour avoir la roster complète)
- ✅ Quand le moteur est stable
- ✅ Quand tu veux un "boss final" pour le frontend ou un agent benchmark ultime
- ✅ Pour le sparring de futurs agents (Zenom comme adversaire des suivants)
- ❌ Si Jio + Neosia couvrent déjà tes besoins de "meilleur agent"

### Recommandation pratique

Faire la **Version A en premier** (ensemble exploiter pragmatique). Elle donne
80% du bénéfice pour 30% du coût. La Version B (meta-game adaptive) ne se
justifie que si :
- Tu veux faire de la recherche pure RL
- Version A plafonne à un niveau insatisfaisant
- Tu as l'envie / le temps pour une architecture custom

### Hiérarchie de la roster (à terme)

```
greedy bot                    (baseline)
   ↓
7 profils LLM scriptés        (curriculum + référence)
   ↓
RL Jin/Jio/Cross/Jaeha        (challengers généralistes)
   ↓
Neosia                        (specialist anti-LLM)
   ↓
Zenom                         (meta-agent ensemble / adaptive)
```

Zenom = sommet de la pyramide. Tout ce qui vient après devra le battre.

---

## (espace pour futures idées)
