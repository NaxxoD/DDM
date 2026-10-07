# DDM — Vue d'ensemble des Agents RL
> Dernière mise à jour : 2026-05-09
> Couvre : Jin, Jio, Cross, Jaeha, (Neosia - design)

---

## 1. Architecture globale du système

### Adversaires disponibles
| Type | Entités | Rôle |
|---|---|---|
| Greedy bot | 1 | Baseline brute, sélection faction aléatoire, optimisation locale pure |
| Profils LLM | 7 | Scripts distillés depuis vrais modèles (claude, mistral, grok, gemini, chatgpt, sonnet, opus) |
| Agents RL | 5 (4 actifs + Neosia) | Cibles finales du système |

### Niveaux LLM de référence (WR vs greedy)
| Niveau | Profils | WR approx | Mécanique clé |
|---|---|---|---|
| Baseline | Haiku/Gemini | 47–54% | force_hq + kill shot simple |
| Intermédiaire | ChatGPT/Mistral | 57% | CAP threshold + scoring offensif |
| Avancé | Sonnet/Opus | 62–67% | Threat-weighted (Sonnet) / Advance-first (Opus) |

### Infrastructure technique
- **Framework** : Stable Baselines 3 — PPO (Proximal Policy Optimization)
- **Parallélisation** : SubprocVecEnv 4 workers (process séparés pour isoler les globals)
- **Observation** : vecteur numérique — plateau, pool ressources, HP QG, positions unités
- **Reward** : `ddm_reward_v2.py` — multi-signal (voir section reward)
- **Draft** : full blind + passif — faction/champion assignés aléatoirement, hors action space et hors observation
- **Logging** : CSV + MD par run, distrib.csv par faction/champion, nommage opponent-scoped

### Système de reward (signaux clés)
| Signal | Poids | Direction |
|---|---|---|
| `qg_damage` | +0.05/pt | Dégâts QG adverse |
| `kill_enemy` | +0.10 | Kill ennemi |
| `mate_threat` | +0.30 | Unité adjacente au QG adverse |
| `new_infiltrator` | +0.25 one-shot | Détection défensive |
| `intercept_kill` | +0.35 | Kill suite à interception |
| `lose_self` | -0.15 | Perte alliée |
| `my_hq_reachable` | -0.40 | QG allié exposé |
| `void_action` | -0.05 | Tour sans action |
| `turn_tax` | -0.001 | Malus par tour (incite à finir) |

---

## 2. Les 5 agents

---

### Jin — Spécialiste curriculum standard
**Seed** : 42

**Rôle** : Agent de référence, curriculum easy → hard. Établit le comportement de base d'un entraînement progressif.

**Curriculum v1** : `claude → mistral → grok → gemini → chatgpt → sonnet → opus`
150k steps/stage, 7 stages, 1,050k steps total

**Résultats v1.5** (hard → easy inversé) :
| Stage | Adversaire | WR final | Top Factions | Top Champions |
|---|---|---|---|---|
| 0 | opus | 60.5% | 4 / 1 / 6 | C / E / B |
| 1 | sonnet | 72.2% | 2 / 4 / 5 | C / E / A |
| 2 | chatgpt | 74.8% | 2 / 5 / 4 | C / E / D |
| 3 | gemini | 74.0% | 5 / 2 / 7 | C / E / D |
| 4 | grok | 80.0% | 5 / 2 / 7 | C / E / D |
| 5 | mistral | 68.5% | 5 / 2 / 7 | C / D / E |
| 6 | claude | 62.5% | 2 / 5 / 7 | C / D / E |

**v2 (terminé)** — 4 variantes × 950k steps :
- v2a : sonnet → claude → mistral → sonnet → chatgpt → gemini → grok → sonnet
- v2b : sonnet → grok → gemini → sonnet → chatgpt → mistral → claude → sonnet *(eval réalisée)*
- v2c : opus → claude → mistral → opus → chatgpt → gemini → grok → opus
- v2d : opus → grok → gemini → opus → chatgpt → mistral → claude → opus

**Eval multiseed 2026-05-08** : aucune variante v2 ne surpasse v1 pour Jin.
- v1 : 72.1% (best f8+B 90%)
- v2b : 72.1% (best f5+B 86.7%) — net nul, perd pic
- v2c : 62.9% (best f1+E 76.7%) — clairement mauvais
- v2d : 72.3% (best f1+D 83.3%) — marginal, +0.2 pt non significatif

**Décision** : Jin garde son checkpoint v1 (`jin/jin_claude_final.zip`) en production. Hypothèse : Jin a sur-convergé en v1 sur exploits f8+B et f4+D, les anchors interleaved les détruisent sans remplacer.

**Observations** : Faction 5 et champions C/E/D dominants. Opus = mur systématique (~60%). Hard→easy donne +9% sur opus mais au coût du reste.

---

### Jio — Mesure de variance
**Seed** : 137

**Rôle** : Clone curriculum de Jin. Même entraînement, seed différent. Sert à mesurer la variance naturelle entre deux agents identiquement entraînés, et à distinguer les comportements stables des artefacts de seed.

**Curriculum** : identique à Jin (toutes versions)

**Résultats v1.5** (hard → easy) :
| Stage | Adversaire | WR final | Top Factions | Top Champions |
|---|---|---|---|---|
| 0 | opus | 61.3% | 2 / 1 / 5 | A / D / B |
| 1 | sonnet | 62.3% | 1 / 4 / 5 | A / D / E |
| 2 | chatgpt | 65.8% | 5 / 1 / 2 | A / D / E |
| 3 | gemini | 75.8% | 5 / 1 / 2 | D / B / A |
| 4 | grok | 70.2% | 5 / 2 / 4 | D / A / E |
| 5 | mistral | 69.8% | 5 / 2 / 6 | D / A / C |
| 6 | claude | 70.5% | 5 / 7 / 6 | D / C / A |

**Observations** : Même curriculum que Jin mais champion préférentiel différent (D au lieu de C) — confirme que les préférences faction/champion émergent du seed, pas uniquement du curriculum. WR globalement +4–8% sur Jin en v1.5 hard→easy.

---

### Cross — Curriculum inversé
**Seed** : 99

**Rôle** : Mesure l'impact de l'ordre d'exposition. Commence par le plus fort (opus) au lieu du plus faible (claude). Variable expérimentale principale de v1/v1.5.

**Curriculum v1.5** (easy → hard, inverse de son défaut) : `claude → mistral → grok → gemini → chatgpt → sonnet → opus`

**Résultats v1.5** (easy → hard) :
| Stage | Adversaire | WR final | Top Factions | Top Champions |
|---|---|---|---|---|
| 0 | claude | 69.5% | 1 / 2 / 4 | C / B / A |
| 1 | mistral | 72.5% | 2 / 4 / 7 | B / A / C |
| 2 | grok | 72.5% | 2 / 5 / 4 | B / A / C |
| 3 | gemini | 76.8% | 2 / 5 / 7 | B / C / A |
| 4 | chatgpt | 75.0% | 5 / 2 / 7 | B / C / D |
| 5 | sonnet | 69.2% | 5 / 2 / 7 | B / D / C |
| 6 | opus | 51.2% | 5 / 2 / 7 | B / C / D |

**Observations** : Champion B dominant (signature Cross, absente chez Jin/Jio). WR opus 51.2% = le plus bas des 3, cohérent avec le mur opus. Symétrie parfaite confirmée v1 vs v1.5 : l'ordre est la variable dominante, pas l'identité de l'agent.

---

### Jaeha — Challenger généraliste
**Seed** : variable (random à chaque run de phase 2)

**Rôle** : 4e agent, design volontairement opposé aux 3 premiers. Généraliste explorateur vs spécialiste curriculum. Challenger final destiné à affronter Jin/Jio/Cross dans le bracket.

**Curriculum en 3 phases** :

**Phase 1 — Greedy only** : 500k steps, adversaire greedy uniquement
- Objectif : maîtrise meta des factions/champions (8 factions à explorer)
- WR final v1.5 : **67.0%** vs greedy

**Phase 2 — Curriculum aléatoire** : 7 profils LLM, ordre re-tiré aléatoirement à chaque run
- 150k steps/profil, 1,050k steps total
- Jamais le même ordre — mesure la généralisation, pas l'adaptation à une progression fixe
- Exemple run v1.5 (ordre : grok → opus → mistral → sonnet → claude → chatgpt → gemini) :

| Stage | Adversaire | WR final |
|---|---|---|
| 0 | grok | 75.0% |
| 1 | opus | 60.0% |
| 2 | mistral | 75.5% |
| 3 | sonnet | 65.5% |
| 4 | claude | 74.0% |
| 5 | chatgpt | 68.5% |
| 6 | gemini | 72.5% |

**Phase 3 — Bracket final** : affronte Jin, Jio, Cross (ordre selon WR vs greedy)

**Script empirique** (`build_jaeha_empirical.py`) : accumulateur de matrice 7×7 (position × adversaire → WR moyen), auto-déclenché après chaque phase 2. Permet de construire progressivement un tableau de performance empirique sur toutes les ordres testés.

**Observations** : WR moyen ~70% sur LLM, robuste aux ordres aléatoires. Faction 5 dominante, champion diversifié selon l'ordre rencontré.

---

### Neosia — Méta-agent anti-Claude (design)
> Pas de script. Design validé, implémentation dépend de la fin des 4 autres.

**Rôle** : 5e agent RL, conçu spécifiquement pour battre Claude API en direct. Question de recherche : *un RL spécialisé contre un LLM peut-il le battre de façon consistante ?*

**Concept** : Les 4 agents ont absorbé les profils LLM dans leurs poids via leur curriculum. S'entraîner contre eux = s'entraîner indirectement contre tout le savoir distillé des LLM.

**Curriculum en 2 phases** :

**Phase 1 — Les 4 agents RL** :
- Adversaires : Jin, Jio, Cross, Jaeha (ordre et rotation à définir selon résultats)
- Objectif : absorber les stratégies émergentes des 4 curricula différents
- Steps : à calibrer selon les résultats finaux des 4 agents

**Phase 2 — Claude API direct** :
- Adversaire : vrai modèle Claude via API Anthropic
- Objectif : spécialisation anti-Claude, battre le LLM de façon consistante
- Steps : à définir

**Contraintes techniques à implémenter** :
- Wrapper DDMEnv pour appel API Claude en temps réel comme adversaire
- `SubprocVecEnv` incompatible avec API synchrone → probablement `DummyVecEnv` ou appel async
- Ajouter `neosia` dans les choix `--agent` de `train_ppo.py`
- Gérer la latence API dans la boucle de training

**Dépendances** : fin du training Jin + Jio + Cross + Jaeha, implémentation wrapper Claude API dans `ddm_env.py`.

---

## 3. Plan de training — versions

### Versioning
| Version | Description | Statut |
|---|---|---|
| v0 | Baseline RL, tests initiaux | Terminé (checkpoints supprimés) |
| v1 | Curriculum standard, 7 stages 150k | Terminé — logs CSV/MD |
| v1.5 | Test inversion curriculum (Cross easy→hard, Jin/Jio hard→easy) | Terminé — symétrie confirmée |
| v2 | Interleaved avec ancres (4 variantes × 3 agents) | Terminé — évalué multiseed 2026-05-08 |
| v3+ | À définir selon résultats v2 | Non planifié |

### Résultats éval multiseed v1 vs v2 (2026-05-08)
**Setup** : 4 agents × 2 versions × 3 seeds (42, 137, 999) × 500 games vs opus = 12 000 games totaux.
Agrégation par version (1500 games/cellule), checkpoints v2 = `v2d/cross`, `v2b/jin`, `v2b/jio`, `v1.5/jaeha`.

| Agent | V1 WR | V2 WR | Δ | Verdict |
|---|--:|--:|--:|---|
| jaeha | 43.7% | **62.1%** | **+18.4 pts** | Gain majeur (jaeha v1.5 = 1.55M steps mistral curriculum) |
| cross | 57.3% | **70.5%** | **+13.2 pts** | Gain net |
| jio | 69.5% | **73.1%** | +3.7 pts | Léger gain |
| jin | 72.1% | 72.1% | 0.0 pts | Stagnation — v2b déstabilise sans remplacer |

**Observation jin** : le curriculum v2b (anchor sonnet) provoque -26.7 pts sur ses combos historiquement forts (f8_B passe de 90% → 63%, f4_D de 76% → 50%) compensés par d'autres hausses → 0 net. À retester sur v2c/v2d (anchor opus) avant de conclure que v1 reste optimal pour jin.

**Préférences combos best v2** :
| Agent | Best v1 | Best v2 |
|---|---|---|
| cross | f8_A 70.0% | **f5_A 86.7%** |
| jaeha | f1_A 56.7% | **f8_A 73.3%** |
| jin | f8_B 90.0% (regression) | f5_B 86.7% |
| jio | f2_D 83.3% | f3_E 83.3% (équivalent) |

**Détails** : `reports/Report/eval_multiseed_v1_vs_v2.csv`, scripts `tools/scripts/compare_eval_multiseed.py` et `compare_jin_variants.py`.

**Workflow eval** : `launch_eval_multiseed.bat` (24 evals × 4 // = 6 batches, ~1h sur laptop). À refaire pour chaque nouvelle release pour comparer aux baselines précédentes.

### Bracket RL vs RL — 2026-05-09

**Setup** : 4 agents en bracket complet — matrix 6 pairs × 3 seeds × 2 mirrors × 50 games + playoff (2 demis + finale + boss greedy). Total 2600 games.

#### Pre-migration (run_quick)

**Champion : jio** 🏆 (bat greedy 159-32)

| Rang | Agent | WR moy | Elo | Bilan |
|---|---|--:|--:|---|
| 1 | jio | 66.85% | 1661 | bat tous les RL + greedy |
| 2 | cross | 53.62% | 1598 | bat jin et jaeha |
| 3 | jin | 46.82% | 1410 | bat jaeha seul |
| 4 | jaeha | 29.00% | 1417 | perd contre tous |

Faits saillants : jio dominante sans appel, jaeha s'effondre à 29% (sous greedy en Elo), jin perd son edge sans son exploit f8+B (random faction draft).

#### Post-migration BLIND (post_migr_blind)

Mêmes agents, nouveau moteur (4 fichiers migrés laptop→desktop : surcharge ATK, attack redirection, dice_bag fix, nouveaux ability types). Aucun retraining — test de généralisation forcée.

**Champion : jio** 🏆 (identique au pre-migration, bat greedy 155-41)

| Agent | Pre WR | Post WR | Δ |
|---|--:|--:|--:|
| jaeha | 29.00% | 34.00% | **+5.00 pts** (gain max) |
| cross | 53.62% | 53.77% | +0.15 pts |
| jin | 46.82% | 46.00% | -0.82 pts |
| jio | 66.85% | 63.15% | -3.69 pts (perte max) |

**Δ moyen absolu : 2.42 pts → IMPACT FAIBLE**

H2H notable : jaeha vs jio passe de 19.6% à 30.2% (+10.6 pts) — l'engine fix favorise particulièrement Jaeha. Hypothèse : dice_bag fix (dés ressource retournés au sac) avantage les builds plus défensifs/longs.

**Verdict** : retraining non nécessaire à court terme. Les 4 agents tiennent face aux nouvelles mécaniques malgré qu'ils ne les aient jamais vues en training.

**Détails** : `reports/Report/bracket_pre_vs_post_migr.md`, scripts `tools/scripts/render_bracket.py`, `tools/scripts/compare_brackets.py`. Fichiers JSONL : `reports/bracket/run_quick/` et `reports/bracket/post_migr_blind/`.



### V2 — Interleaved curriculum (en cours)
**Problème résolu** : catastrophic forgetting. Les MLP policies subissent un drift progressif des poids entre stages. Aucun curriculum linéaire ne peut optimiser simultanément contre opus et claude.

**Solution** : ancres répétées toutes les 2–3 étapes pour limiter le drift à max 300k steps entre deux rappels.

**Structure** :
```
v2a — Circuit Sonnet : sonnet → claude → mistral → sonnet → chatgpt → gemini → grok → sonnet
v2b — Circuit Opus   : opus   → claude → mistral → opus   → chatgpt → gemini → grok → opus
v2c — [variante WR croissant]
v2d — [variante WR décroissant]
```

**Budget** : 3×150k (ancres) + 5×100k (middles) = **950k steps/run**
**Total v2** : 4 variantes × 3 agents (Jin/Jio/Cross) = **12 runs**, batché 2 à la fois via `launch_v2_full.bat`

**Paramètres train_ppo.py** :
```
--curriculum-custom sonnet,claude,mistral,sonnet,chatgpt,gemini,grok,sonnet
--anchor-steps 150000
--middle-steps 100000
```

---

## 4. Systèmes transverses

### Avancement curriculum
- **Mode fixe** (actuel) : X steps par stage, avance automatiquement
- **Mode conditionnel** (disponible) : avance quand WR ≥ seuil sur N parties (`--advance-mode conditional --advance-wr 0.55`)

### Logging
- `{agent}_{opponent}_training.csv` — WR par stage, steps, avg_len, avg_reward, total_ep
- `{agent}_{opponent}_training.md` — tableau lisible
- `{agent}_{opponent}_distrib.csv` — picks + wins + WR par faction/champion par stage
- Nommage opponent-scoped pour éviter l'écrasement entre phases (ex: `jaeha_greedy_training.csv` vs `jaeha_grok_training.csv`)

### Checkpoints
- Sauvegarde zip tous les 50k steps + `_final.zip` en fin de run
- Fichier sentinel `.done` à la fin de chaque agent pour séquencer les bats

### Matrice empirique Jaeha
- `build_jaeha_empirical.py` — scan récursif des CSV Jaeha, construit matrice 7×7 position × adversaire
- Auto-déclenché à la fin de chaque phase 2
- Output : `jaeha_empirical.md` avec tableau, meilleure position par adversaire, ordre optimal suggéré
- 5040 ordres possibles, ~2 ans pour saturation complète → outil de tendance progressive

---

## 5. Bracket final prévu

### Étape 1 — Évaluation croisée
40 combos faction/champion × 10 parties = **400 parties exploration**
+ 50 parties confirmation (préférences 1 + 2 par agent)
Matrice 8 factions × 5 champions = 40 choix uniques × 4 agents = 160 matchups totaux

### Étape 2 — Play-in Jin / Jio / Cross / Jaeha
Bracket entre les 4 agents RL

### Étape 3 — Vainqueur vs Greedy
Test de généralisation en aveugle — mesure que le meilleur agent ne s'est pas sur-adapté aux profils LLM

### Étape 4 — Neosia (post-bracket)
Phase 1 contre les 4 agents, phase 2 contre Claude API direct

---

## 6. Signaux de balance à surveiller

| Signal | Risque | Action |
|---|---|---|
| Champion B dominant chez Cross | Sur-apprentissage exploit B (62.6% WR agrégé, 2e toutes factions) | Monitorer distrib.csv Cross |
| Faction 3 (Conclave Abyssal) absente | Jamais choisie par aucun profil LLM — angle mort | Vérifier exposition en eval |
| Faction 5 dominante | Systématique chez tous les agents | Normal si WR élevé, surveiller si WR bas |
| Opus wall (~60%) | Plafond structurel de tous les curricula linéaires | Motif principal du v2 interleaved |

---

## 7. Fichiers clés

| Fichier | Rôle |
|---|---|
| `rl/train_ppo.py` | Script principal d'entraînement |
| `rl/ddm_env.py` | Wrapper gym.Env autour du moteur DDM |
| `rl/ddm_reward_v2.py` | Calcul du reward multi-signal |
| `rl/build_jaeha_empirical.py` | Accumulation matrice empirique Jaeha |
| `rl/jaeha_design.md` | Design détaillé Jaeha |
| `rl/neosia_design.md` | Design détaillé Neosia |
| `rl/docs/agents_Jin_Jio_Cross.md` | Architecture Jin/Jio/Cross + bracket |
| `rl/glossaire_rl_ddm.md` | Glossaire complet signaux reward + dashboard |
| `launch_v2_full.bat` | Lancement automatisé 12 runs v2 |
| `launch_jaeha_repeat.bat` | Jaeha en boucle pour matrice empirique |
| `launch_eval_v2_logged.bat` | Eval v2 vs opus (4 agents, seed unique, logs fichier) |
| `launch_eval_multiseed.bat` | Eval comparative v1 vs v2 (24 evals, 3 seeds, 6 batches) |
| `launch_eval_jin_v2cd.bat` | Eval Jin v2c/v2d vs v2b actuel |
| `tools/scripts/compare_eval_multiseed.py` | Agrégation 3 seeds, table v1 vs v2 |
| `tools/scripts/compare_jin_variants.py` | Comparaison côte-à-côte v1/v2/v2c/v2d pour Jin |
| `tools/scripts/watch_eval.bat` | Dashboard temps réel eval (process, sentinelles, tail logs) |
| `rl/bracket.py` | Bracket RL vs RL + boss greedy (matrix / bracket / pair / boss) |
| `launch_bracket.bat` | Orchestrateur bracket complet (matrix + playoff + boss) |
| `tools/scripts/render_bracket.py` | Rendu arbre playoff / matrice / Elo / draft / killers |
| `tools/scripts/compare_brackets.py` | Diff pre vs post bracket (engine fix impact) |
| `tools/scripts/watch_bracket.bat` | Dashboard live bracket (matrix progress + arbre live) |
| `engine/_pre_migration_backup/` | Backup 4 fichiers engine avant migration 2026-05-09 |
| `rl/checkpoints/v*/` | Checkpoints + logs par version |
| `rl/checkpoints/eval_multiseed/{ver}/seed{N}/{agent}/` | Résultats eval multiseed |
| `rl/checkpoints/eval_monoseed/_v1_baseline_2026-04-22/` | Backup eval v1 mono-seed (déprécié) |
