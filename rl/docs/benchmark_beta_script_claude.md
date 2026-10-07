# Benchmark — beta_script_claude

Suivi de performance du script stratégique `ddm_p4_claude.py` selon le modèle LLM source.
L'objectif est d'observer si la qualité de raisonnement du modèle (Haiku → Sonnet → Opus)
se reflète dans les indicateurs de jeu issus du bot Python qui en est inspiré.

> **beta_script_claude** = `ddm_p4_claude.py` v1  
> Script traduit en Python depuis la réflexion stratégique du modèle Haiku 4.5 (choix faction/champion + style de jeu).  
> Interface identique à `phase_mobs_ai`. Mode `--mode cvia` dans le loop.

---

## Paramètres fixes (référence)

| Paramètre           | Valeur                        |
|---------------------|-------------------------------|
| Adversaire          | IA greedy (`phase_mobs_ai`)   |
| Bag size            | 11 dés (standard)             |
| Max rounds          | 150 *(runs actuels)*          |
| Mode bandit         | 85% exploit / 15% explore     |
| Switch threshold    | +10% WR sur ≥ 20 parties      |
| Prefs persistance   | `data/claude_prefs.json`      |
| Prompt LLM          | Identique pour tous les modèles (`prompt_standard.md`) |
| Contexte Haiku / Grok / Gemini / Mistral / ChatGPT | Context lite |
| Contexte Sonnet / Opus | Context complet |

---

## Historique par modèle source

### Haiku 4.5 — beta_script_claude v1

**Date :** 2026-04-16  
**Modèle :** `claude-haiku-4-5-20251001`  
**Script :** `ddm_p4_claude.py` v1  
**Faction de départ :** 3 — Légions Scailles-Feu / Champion D (Venina)  
*(inspiré indirectement — Haiku a choisi 7/D Serapia, mais la faction 3/D partage la philosophie attrition/late-game)*

**Choix Haiku brut :**
- Faction : 7 — Dynasties Solaires
- Champion : D — Serapia la Vengeresse
- Style : défense early → spike offensif quand QG adverse < 30% HP
- Matchup voulu : Orcs (rush brut s'use seul)
- Matchup évité : Lycans (mobilité casse le plan)

**Mécaniques traduites dans le script :**
- `score_enemy()` : kill_potential (200) + hp_low bonus (60) + QG_proximity (25) → focus fire sur blessés
- `_try_ability_smart()` : heal seulement si allié < 80% HP, offensif seulement si cible valide
- `_astar_step()` : A* vers l'ennemi le plus valorisé (portée 5 en priorité)
- Attaque : kill shot sur unité > focus QG (sauf si QG only adjacent)

---

### Historique des patches v1.x

| Version | Date       | Fix appliqué                                               | Run de validation |
|---------|------------|------------------------------------------------------------|-------------------|
| v1.0    | 2026-04-16 | Baseline post-INCOMPLETE fix (mouvement → 40% threshold)  | 80 games          |
| v1.1    | 2026-04-16 | Attack priority : QG kill shot > unit kill shot > QG focus | 20 games          |
| v1.2    | 2026-04-16 | force_hq=True (rush QG permanent) + combo Égypte Disque Solaire | pending      |

---

### v1.0 — Baseline (80 parties)

> Mouvement cible unité ennemie par défaut, QG seulement si ≤ 40% HP.  
> Attaque : priorité kill shot unité avant QG.

| Métrique              | Valeur                      |
|-----------------------|-----------------------------|
| Parties jouées        | 80 (20 paires × 4 variants) |
| WR vs IA greedy (A)   | **5%** (4/80)               |
| WR vs IA greedy (B)   | 55% (44/80)                 |
| Draw                  | 40% (32/80)                 |
| dmg_QG moy. A / B     | 1.9 / 20.4                  |
| void_mid/late A / B   | 30.9% / 42.7%               |
| unused_pool           | -483.0 (dominant)           |
| my_hq_reachable       | -253.6                      |
| Faction finale bandit | non convergé (run supprimé) |

---

### v1.1 — Attack priority fix (20 parties)

> QG kill shot devient priorité #1. Mouvement inchangé (threshold 40%).

| Métrique              | Valeur                      |
|-----------------------|-----------------------------|
| Parties jouées        | 20 (5 paires × 4 variants)  |
| WR vs IA greedy (A)   | **10%** (2/20)  +5pp vs v1.0 |
| WR vs IA greedy (B)   | 50% (10/20)                 |
| Draw                  | 40% (8/20)                  |
| dmg_QG moy. A / B     | 3.0 / 26.1                  |
| void_mid/late A / B   | 29.2% / 43.2%               |
| unused_pool           | -111.4 (dominant)           |
| my_hq_reachable       | -96.0                       |
| Notes                 | dmg_QG A ×1.6 mais écart B reste énorme |

---

### v1.2 — force_hq + combo Égypte

> Mouvement cible toujours QG ennemi (rush constant).  
> Statue du Disque Solaire : reste immobile si ennemis vivants et QG > 25% HP (Ancrage passif).  
> Champion du Disque Solaire : rejoint la Statue si dist > 1 avant de rusher QG (Aura active).

**Run de validation — 60 parties (15 paires × 4 variants)**

| Métrique              | Valeur                                    |
|-----------------------|-------------------------------------------|
| Parties jouées        | 60                                        |
| WR vs IA greedy (A)   | **57%** (34/60)  +47pp vs v1.1            |
| WR vs IA greedy (B)   | 40% (24/60)                               |
| Draw                  | **3%** (2/60)  ↓ depuis 40%              |
| dmg_QG moy. A / B     | **19.2 / 15.7**  A dépasse B pour la 1ère fois |
| void_mid/late A / B   | 29.9% / 43.3%                             |
| unused_pool           | -260.8                                    |
| my_hq_reachable       | **-292.0 (dominant)** — nouveau signal ⚠️ |

**Run benchmark — 500 parties (125 paires × 4 variants)**

| Métrique              | Valeur                                    |
|-----------------------|-------------------------------------------|
| Parties jouées        | 500                                       |
| WR vs IA greedy (A)   | **54%** (272/500)  IC ±4.4pp              |
| WR vs IA greedy (B)   | 40% (198/500)                             |
| Draw                  | 6% (30/500)                               |
| dmg_QG moy. A / B     | **20.5 / 15.8**                           |
| void_mid/late A / B   | 27.9% / 44.0%                             |
| unused_pool           | -2279.3                                   |
| my_hq_reachable       | **-2565.6 (dominant)** ⚠️                |
| Notes                 | 57% → 54% : léger repli sur grand échantillon. Signal dominant = QG allié exposé par rush |

---

---

## Mistral Équilibre — beta_script_mistral v1.0

**Date :** 2026-04-16  
**Modèle :** Mistral Équilibre (lite)  
**Script :** `ddm_p4_mistral.py` v1.0  
**Faction de départ :** 4 — Cyborgs — Système Oméga / Champion B (Analyste du Code)

**Choix Mistral brut :**
- Faction : 4 — Système Oméga
- Champion : B — Analyste du Code
- Style : calculé/technique, optimisation ressources, précision, gestion des risques
- Matchup voulu : Orcs (counter rush brut par calcul)
- Matchup évité : Fractaux Oniriques (chaos perturbe la précision)
- Second choix : Citadelles du Nexus / Archonte du Bastion (défensif/positionnel)

**Mécaniques traduites dans le script :**
- `force_hq=True` pour toutes les unités non-défenseur (convergence avec Claude v1.2)
- Defender redirect : 1 unité redirigée vers QG allié si ennemi adjacent (dist ≤ 1)
- Abilities : utilise tout le pool CAP disponible (vs cap à 1 pour Claude)
- `score_position()` : implémentée mais non utilisée en v1.0 (flanking trop dominant)

**Progression des runs**

| Run  | Parties | WR A | WR B | Draw | dmg_QG A/B |
|------|---------|------|------|------|------------|
| 20g  | 20      | 70%  | 10%  | 20%  | 26.0 / 5.2 |
| 60g  | 60      | 57%  | 27%  | 17%  | 21.3 / 11.9 |
| 80g  | 80      | **62%** | 35% | 2.5% | 22.1 / 12.0 |
| **500g** | **500** | **57%** | **32%** | **11%** | **20.7 / 14.1** |

IC 500g : ±4.4pp → **[52.6%, 61.4%]** — confirme l'avantage vs Claude 54% ([49.6%, 58.4%])

**Run benchmark — 500 parties (125 paires × 4 variants)**

| Métrique              | Valeur (500g)                              |
|-----------------------|--------------------------------------------|
| Parties jouées        | 500                                        |
| WR vs IA greedy (A)   | **57%** (284/500)  IC ±4.4pp               |
| WR vs IA greedy (B)   | 32% (160/500)                              |
| Draw                  | 11% (56/500)                               |
| dmg_QG moy. A / B     | **20.7 / 14.1**  B plus supprimé que Claude (15.8) |
| void_mid/late A / B   | 28.6% / 44.2%                              |
| unused_pool           | -2263.0 (dominant ⚠️)                      |
| my_hq_reachable       | **-2387.2** — meilleur que Claude -2566    |
| Notes                 | +3pp vs Claude — defender réduit exposure QG |

---

### Sonnet 4.6 — beta_script_sonnet v1

**Date :** 2026-04-18  
**Modèle :** `claude-sonnet-4-6`  
**Script :** `ddm_p4_sonnet.py`  
**Faction de départ :** 4/B — Cyborgs · Système Oméga / Analyste du Code

**Choix Sonnet brut :**
- Faction : 4 — Cyborgs · Système Oméga
- Champion : B — Analyste du Code
- Style : arbre de décision par tour — prioriser l'efficacité des ressources, construire le sentier chirurgicalement pour restreindre les options adverses, déclencher les abilities au moment de leur impact maximal
- Abilities choisies : Protocole d'Invalidation (3 ATK, silence ennemi à portée 2 / 1 tour) + Analyse Stérile (passif, +1 au coût de la prochaine ability ennemie à portée de garde)
- Matchup voulu : Orcs (rush prévisible à lire et contrer) / évité : Abominations (chaos casse l'optimisation)
- Choix final confirmé sans révision après clarifications mécaniques

**Mécaniques implémentées dans ddm_p4_sonnet.py :**
- `score_enemy()` : threat-weighted targeting — `def_threat × 80` (proximité QG allié) + `off_prox × 20` (proximité QG ennemi) + kill shot 250 + low HP 30
- `_should_use_cap()` : CAP conservatrice — utilise uniquement si kill shot possible OU cible à ≤ 2 cases du QG allié
- Bandit RL interne (85% exploit / 15% explore, seuil +10% WR sur ≥ 20 games)

**Progression WR (vs IA greedy) :**

| Volume | WR A (Sonnet) | WR B (greedy) | Draws |
|--------|--------------|---------------|-------|
| 20g    | 60%          | 30%           | 10%   |
| 60g    | 57%          | 30%           | 13%   |
| 80g    | 57%          | 32%           | 10%   |
| **500g** | **62.4%** (312/500) | **32.8%** (164/500) | **4.8%** (24/500) |

**Bandit final :** 5/B (Clans Fer & Fureur) — 20W/2L/22g = **90.9% WR**  
**Combos explorés :** 40 — même over-exploration systémique  
**Divergence profile/bandit :** oui — parti sur 4/B, convergé vers 5/B  
**dmg_QG A :** 21.8 — meilleur de tous les modèles  
**Draws :** 4.8% — très bas (threat-weighted targeting résout les parties plus vite)

---

### Opus 4.7 — beta_script_opus v1

**Date :** 2026-04-18  
**Modèle :** `claude-opus-4-7`  
**Script :** `ddm_p4_opus.py`  
**Faction de départ :** 4/A — Cyborgs · Système Oméga / Programme Alpha

**Choix Opus brut :**
- Faction : 4 — Cyborgs (initial 4/D Architecte Zero, révisé vers 4/A après clarifications mécaniques)
- Champion : A — Programme Alpha
- Abilities : Reconfiguration Tactique (3 MOVE, téléporte un allié vers case libre à portée 3) + Optimisation du Flux (passif, 1 MOVE gratuit à une unité adjacente au QG au début du tour adverse)
- Style révisé : QG comme catapulte — maintenir 1-2 unités adjacentes au QG, les projeter via Reconfiguration ; invocations L1/L2/L3 pour étendre le sentier et la portée utile de Reconfiguration ; pas de Rituel Noir (tempo > pari L5) ; 1 Reconfiguration/tour en croisière, burst ×2 possible en late si pool MOVE le permet
- Matchup voulu : Orcs / évité : Abominations
- Révision motivée : Architecte Zero = fortification statique (≠ style adaptatif voulu) ; Programme Alpha = contrôle de position dynamique

**Mécaniques implémentées dans ddm_p4_opus.py :**
- `phase_mobs_opus()` : advance-first ordering — unités les plus proches du QG adverse agissent en premier (mouvement ET attaque)
- `_has_valid_target()` : CAP libérale — utilise dès qu'une cible ennemie est à portée d'ability
- `score_enemy()` : kill shot 230 + `hq_prox × 40` (proximité QG ennemi) + low HP 25
- Bandit RL interne (85% exploit / 15% explore, seuil +10% WR sur ≥ 20 games)

**Progression WR (vs IA greedy) :**

| Volume | WR A (Opus) | WR B (greedy) | Draws |
|--------|------------|---------------|-------|
| 20g    | 60%        | 30%           | 10%   |
| 60g    | 67%        | 23%           | 10%   |
| 80g    | 48%        | 40%           | 12%   |
| **500g** | **67%** (334/500) | **26%** (130/500) | **7.2%** (36/500) |

**Bandit final :** 1/B (Meutes Lunaires) — 18W/6L/24g = **75% WR**  
**Combos explorés :** 40 — même over-exploration systémique  
**Divergence profile/bandit :** oui — parti sur 4/A, convergé vers 1/B  
**dmg_QG A :** 23.5 — record absolu tous modèles confondus  
**Creux 80g :** variance uniquement — 500g confirme le niveau 60g

---

## Grok Auto — beta_script_grok

**Date :** 2026-04-18  
**Modèle :** Grok (xAI) — lite  
**Script :** `ddm_p4_grok.py`  
**Faction de départ :** 5 — Orcs — Clans Fer & Fureur / Champion A (Chef de Guerre Grok)

**Choix Grok brut :**
- Faction : 5 — Clans Fer & Fureur
- Champion : A — Chef de Guerre Grok
- Style : rush agressif dès T1, trades mêlée, assaut final QG avant que les factions techniques prennent le dessus
- Matchup voulu : Démons — Conclave Abyssal (miroir brutalité)
- Matchup évité : Cyborgs — Système Oméga (précision contre-rush)
- **Seul modèle à diverger** : tous les autres ont choisi Faction 4 (Cyborgs)

**Mécaniques traduites dans le script :**
- `force_hq=True` (convergence avec Claude/Mistral)
- **v1.0** : trade-targeting si ennemi à dist ≤ 2 → détours, draws (17%)
- **v1.1** : trade seulement si ennemi `in_path` (dist ennemi→QG ennemi ≤ dist nous→QG ennemi)
- `score_enemy()` : kill_shot=250 (vs Claude 200), hq_proximity×30
- `_CAP` : utilise tout le pool disponible

**Progression des runs**

| Run      | Parties | WR A (Grok) | WR B (greedy) | Draw | Notes |
|----------|---------|-------------|---------------|------|-------|
| v1.0 20g | 20      | 50%         | 33%           | 17%  | baseline |
| v1.0 60g | 60      | 50%         | 33%           | 17%  | signal détours |
| v1.0 80g | 80      | 60%         | 32%           | 7.5% | 80g cumulé avec 500g |
| **v1.0 500g** | **500** | **49%** | **40%** | **11%** | IC ±4.4pp |
| v1.1 20g | 20      | 57%         | 40%           | 3%   | fix in_path validé |
| v1.1 60g | 60      | 57%         | 40%           | 3%   | draws ↓↓ |
| v1.1 80g | 80      | 57%         | 40%           | 3%   | stable |
| **v1.1 500g** | **500** | **42.4%** (212) | **39.6%** (198) | **18%** (90) | IC excl. draws [46.9–56.5%] |

**Run benchmark v1.1 — 500 parties**

| Métrique              | Valeur                                      |
|-----------------------|---------------------------------------------|
| Parties jouées        | 500                                         |
| WR Grok (A) incl. draws | **42.4%** (212/500)                       |
| WR excl. draws        | **51.7%** (212/410)  IC [46.9% – 56.5%]    |
| Draws (timeouts)      | 18% (90/500)                                |
| dmg_QG moy. A / B     | 19.4 / 16.3                                 |
| void_mid/late A / B   | 29.3% / 43.1%                               |
| Faction finale bandit | **7/B — Lycans · Meutes Lunaires** (WR 77.8% sur 36g) |
| Notes                 | Bandit sur-exploré (40+ combos). Seul bot à changer de faction vs profil annoncé. |

**Observation notable :** Grok est le seul modèle à avoir divergé du consensus Faction 4 lors du profil, **et** le seul dont le bandit a changé de préférence en cours de run (Orcs → Lycans). Cohérence profil/comportement : instinct de pivot, pas d'ancrage sur le choix initial.

---

## Gemini Rapide — beta_script_gemini

**Date :** 2026-04-18  
**Script :** `ddm_p4_gemini.py`  
**Faction de départ :** 4/D — Cyborgs · Système Oméga / Architecte Zero

**Choix Gemini brut :**
- Faction : 4 — Système Oméga (approche méthodique, précision technique)
- Champion : D — Architecte Zero (siège + zone de sécurité autour du QG)
- Style : fortification des goulots d'étranglement, Architecte Zero comme ancre défensive près du QG
- Matchup voulu : Orcs / évité : Abominations (chaos perturbe les calculs)
- Choix maintenu sans révision après clarifications mécaniques (malgré la découverte que Architecte Zero = statique, pas bâtisseur de plateau)

**Progression WR (vs IA greedy) :**

| Volume | WR A (Gemini) | WR B (greedy) | Draws |
|--------|--------------|---------------|-------|
| 20g    | 80%          | —             | ~7%   |
| 60g    | 60%          | —             | ~13%  |
| 80g    | 52%          | —             | ~20%  |
| **500g** | **47.2%** (236/500) | **32.4%** (162/500) | **20.4%** (102/500) |

**Bandit final :** 7/D (Citadelles du Nexus) — 26W/6L sur 32g = **81.25% WR**  
**Combos explorés :** 40 — même over-exploration que Grok  
**Divergence profile/bandit :** oui — parti sur 4/D, convergé vers 7/D

**Observations :**
- Tendance descendante régulière sur toute la séquence (80% → 47%)
- Draws stables à ~20% dès 80g — mécanisme de timeout (Anchor/défenseur permanent) confirmé
- WR positif global (47% > 32% greedy) malgré la descente
- Bandit sur-explore (40 combos) sans converger sur le choix profile — même pattern que Grok
- Gemini et Grok convergent tous deux vers faction 7 (Citadelles) via le bandit, divergeant du profil initial Cyborgs

---

## ChatGPT — beta_script_chatgpt

**Date :** 2026-04-18  
**Script :** `ddm_p4_chatgpt.py`  
**Faction de départ :** 4/B — Cyborgs · Système Oméga / Analyste du Code

**Progression WR (vs IA greedy) :**

| Volume | WR A (ChatGPT) | WR B (greedy) | Draws |
|--------|---------------|---------------|-------|
| 20g    | 50%           | 20%           | 30%   |
| 60g    | 53%           | 33%           | 13%   |
| 80g    | 60%           | 25%           | 15%   |
| **500g** | **57.2%** (286/500) | **31.2%** (156/500) | **11.6%** (58/500) |

**Choix ChatGPT brut :**
- Faction : 4 — Système Oméga, style calculé/tempo, contrôle des ouvertures adverses
- Champion : B — Analyste du Code
- Initial : matchup voulu Abominations / évité Orcs
- Après clarifications abilities + limite unités → **style révisé** : zone de contrôle active, "bulles mortes" (Analyse Stérile taxe en continu, Protocole d'Invalidation casse les pics adverses)
- Matchup voulu révisé → **Égyptiens** (timing abilities vulnérable à la taxation)
- Matchup évité révisé → **Lycans** (mobilité échappe à la zone de garde)
- Choix 4/B confirmé, style nettement plus tranché post-clarification

**Bandit final :** 4/B (Cyborgs, Analyste du Code) — 22W/4L sur 26g = **84.6% WR**  
**Combos explorés :** 40 — même over-exploration que Grok/Gemini  
**Divergence profile/bandit :** non — convergé sur le choix initial (seul modèle sans divergence parmi les non-Claude)

---

## Tableau comparatif global

| Modèle source | Version script | Faction départ | WR vs greedy (A)    | dmg_QG A | Notes |
|---------------|---------------|----------------|---------------------|----------|-------|
| Haiku 4.5     | v1.0          | aléatoire      | 5%                  | 1.9      | baseline, unit-focus |
| Haiku 4.5     | v1.1          | aléatoire      | 10%                 | 3.0      | attack priority fix |
| Haiku 4.5     | v1.2          | aléatoire      | **54%** (500g)      | 20.5     | force_hq + Égypte combo |
| Mistral Éq.   | v1.0          | 4/B Cyborgs    | **57%** (500g)      | 20.7     | IC [52.6–61.4%] — defender |
| Grok Auto     | v1.0          | 5/A Orcs       | **49%** (500g)      | 19.4     | trade-targeting → détours |
| Grok Auto     | v1.1          | 5/A Orcs       | **42.4%** / 51.7% excl. draws (500g) | 19.4 | in_path fix — bandit pivot Lycans |
| Gemini Rapide | v1.0          | 4/D Cyborgs    | **47.2%** (500g)    | 19.2     | descente 80→47%, draws 20%, bandit pivot 7/D |
| ChatGPT       | v1.0          | 4/B Cyborgs    | **57.2%** (500g)    | 21.2     | stable 50→57%, draws bas 12%, bandit = profil |
| Sonnet 4.6    | v1            | 4/B Cyborgs    | **62.4%** (500g)    | 21.8     | stable 57→62%, draws 5%, bandit pivot 5/B |
| Opus 4.7      | v1            | 4/A Cyborgs    | **67%** (500g)      | 23.5     | advance-first, creux 80g variance, bandit pivot 1/B |

---

## Classement final — Beta Script v1 (500g chacun)

> Classement par WR vs IA greedy sur 500 parties, modèles ayant complété la séquence complète.

| Rang | Modèle        | WR vs greedy | dmg_QG A | Draws | Mécanique clé |
|------|--------------|-------------|----------|-------|---------------|
| 🥇 1 | Opus 4.7      | **67.0%**   | 23.5     | 7.2%  | Advance-first ordering |
| 🥈 2 | Sonnet 4.6    | **62.4%**   | 21.8     | 4.8%  | Threat-weighted targeting |
| 🥉 3 | ChatGPT       | **57.2%**   | 21.2     | 11.6% | Zone contrôle / disruption |
|    4 | Mistral       | **57.0%**   | 20.7     | —     | Defender positioning |
|    5 | Haiku v1.2    | **54.0%**   | 20.5     | —     | force_hq baseline |
|    6 | Gemini        | **47.2%**   | 19.2     | 20.4% | Descente progressive |
|    7 | Grok v1.1     | **42.4%**   | 19.4     | 18.1% | in_path fix — sur-exploration |

**Observations générales :**
- Corrélation forte entre dmg_QG et WR — les modèles qui attaquent le QG adverse tôt gagnent plus
- Draws : Opus/Sonnet résolvent les parties rapidement (5–7%) ; Gemini/Grok laissent traîner (18–20%)
- Over-exploration bandit (40 combos) systémique à tous les modèles — n'a pas empêché la convergence mais dilue le WR global
- Divergence profile/bandit : 5 modèles sur 6 ont divergé — seul ChatGPT a convergé sur son choix initial

---

## Hypothèses à valider

---

### H1 — Un modèle plus capable choisit-il une faction mécaniquement plus forte ?

**Verdict : ❌ FAUSSE**

Force mécanique réelle des factions (WR agrégé sur ~500g de bandit, tous modèles) :

| Rang | Faction                  | WR moyen |
|------|--------------------------|----------|
| 1    | Conclave Abyssal (3)     | 69.0%    |
| 2    | Clans Fer & Fureur (5)   | 67.5%    |
| 3    | Citadelles du Nexus (7)  | 66.5%    |
| 4    | Meutes Lunaires (1)      | 59.6%    |
| 5    | Dynasties Solaires (2)   | 59.3%    |
| 6    | Fractaux Oniriques (8)   | 53.6%    |
| 7    | Légions Scailles-Feu (6) | 50.2%    |
| 8    | **Système Oméga (4)**    | **48.1%**|

Choix de profil initial vs bandit final :

| Modèle  | Profil initial        | Rang faction | Bandit final          | Rang faction |
|---------|-----------------------|--------------|-----------------------|--------------|
| Grok    | Clans Fer & Fureur/A  | **2/8**      | Citadelles du Nexus/B | 3/8          |
| Gemini  | Système Oméga/D       | 8/8          | Citadelles du Nexus/D | 3/8          |
| ChatGPT | Système Oméga/B       | 8/8          | Système Oméga/B       | 8/8          |
| Sonnet  | Système Oméga/B       | 8/8          | Clans Fer & Fureur/B  | 2/8          |
| Opus    | Système Oméga/A       | 8/8          | Meutes Lunaires/B     | 4/8          |

**Analyse :**
- Grok (modèle moins sophistiqué) est le seul à avoir choisi une faction forte d'emblée (rang 2/8)
- Les 4 modèles plus capables (Gemini, ChatGPT, Sonnet, Opus) ont tous convergé vers Faction 4 = la plus faible mécaniquement
- La raison est thématique : "analytique, calculé, technique" = Cyborgs — signal d'identité, pas d'évaluation mécanique
- Le bandit a partiellement corrigé pour Gemini, Sonnet, Opus — mais pas pour ChatGPT (resté sur 4/B)

**Corollaire :** Le WR de Sonnet (62%) et Opus (67%) est obtenu *malgré* le pire choix de faction — c'est la qualité des mécaniques du script qui compense. Grok a fait le meilleur choix de faction mais ses mécaniques plombent l'avantage : 42% malgré rang 2/8.

---

### H2 — Les mécaniques issues d'un raisonnement plus riche produisent-elles un WR supérieur ?

**Verdict : ✅ VRAIE — avec nuances**

Richesse du raisonnement (questions posées + révision de profil) vs WR :

| Modèle  | Questions | Révision profil           | Mécanique clé                          | WR    |
|---------|-----------|---------------------------|----------------------------------------|-------|
| Haiku   | aucune    | aucune                    | force_hq (simple)                      | 54%   |
| Grok    | aucune    | aucune                    | trade-targeting (bug détours)          | 42%   |
| Gemini  | 2         | style mineur              | force_hq hérité                        | 47%   |
| ChatGPT | 2         | matchup + style (majeure) | zone disruption / taxation abilities   | 57%   |
| Sonnet  | 3         | aucune                    | threat-weighted dual-score (def×80+off×20) | 62% |
| Opus    | 2         | champion + style (majeure)| advance-first + liberal CAP            | 67%   |

**Analyse :**
- **Famille Claude** : progression stricte capacité → mécanique → WR (Haiku 54% < Sonnet 62% < Opus 67%) — hypothèse validée sans ambiguïté dans ce sous-ensemble
- **ChatGPT et Opus** : révision majeure du profil après clarifications → mécaniques les plus nuancées de leur groupe → WR au-dessus de la moyenne
- **Grok** : principal contre-exemple apparent — modèle capable, bon choix de faction, mais mécanique buggée (trade-targeting générait des détours) → 42% malgré les atouts. Ce n'est pas un contre-exemple de H2 : c'est une illustration que la qualité d'implémentation compte autant que la richesse du raisonnement
- **Gemini** : révision de style sans changement de mécanique fondamentale (force_hq hérité) → WR moyen — confirme que la révision de profil doit se traduire en mécanique réelle pour avoir de l'impact

**Nuance principale :** la richesse du raisonnement se mesure ici par la profondeur du calibrage — pas uniquement par la taille du modèle. Sonnet n'a pas révisé son profil mais a produit des mécaniques complexes ; Gemini a révisé sans impact mécanique.

### H3 — Le bandit RL converge-t-il vers la même faction quelle que soit l'origine du script ?

**Verdict : ❌ FAUSSE sur la faction — ⚠️ convergence cachée sur le champion**

Bandit finals comparés :

| Modèle  | Bandit final | Faction (rang/8) | Champion |
|---------|-------------|-----------------|----------|
| Grok    | 7/B         | Citadelles (3/8) | B        |
| Gemini  | 7/D         | Citadelles (3/8) | D        |
| ChatGPT | 4/B         | Cyborgs (8/8)    | B        |
| Sonnet  | 5/B         | Orcs (2/8)       | B        |
| Opus    | 1/B         | Meutes Lunaires (4/8) | B   |

**Sur la faction :** pas de convergence — 4 factions différentes. Seul Grok et Gemini partagent la même faction finale (7), probablement un signal de force réelle de cette faction dans leurs contextes d'exploration respectifs. Aucun modèle n'a convergé vers Faction 3 (Conclave Abyssal, la plus forte agrégée) — l'over-exploration à 40 combos n'a pas permis une couverture suffisante pour l'identifier.

**Sur le champion : convergence émergente.** 4 modèles sur 5 ont convergé sur champion B — et B est objectivement le 2e champion le plus fort toutes factions confondues :

| Champion | WR moyen (agrégé) | Games |
|----------|-------------------|-------|
| C        | 62.8%             | 672g  |
| **B**    | **62.6%**         | 840g  |
| A        | 58.8%             | 796g  |
| E        | 57.3%             | 824g  |
| D        | 56.1%             | 848g  |

Le bandit a découvert indépendamment dans chaque script que B est systématiquement performant, quelle que soit la faction. C'est un signal de balance : champion B est probablement surpuissant relativement aux autres dans le kit actuel du jeu.

### H4 — La cohérence style annoncé / comportement réel est-elle corrélée à la taille du modèle ?

**Verdict : ✅ VRAIE**

Cohérence entre style annoncé et mécaniques réellement implémentées :

| Modèle  | Style annoncé                                  | Script réel                                      | Cohérence      |
|---------|------------------------------------------------|--------------------------------------------------|----------------|
| Grok    | Rush T1, trades mêlée, assaut QG               | trade-targeting + force_hq (bug détours)         | **partielle**  |
| Gemini  | Fortification, siège, zone de sécurité         | force_hq + hq_proximity×35 (purement offensif)  | **faible**     |
| ChatGPT | Zone contrôle, bulles mortes, tempo précis     | force_hq + hq_proximity×20 + CAP threshold=2    | **partielle**  |
| Sonnet  | Prioriser menaces sur notre QG, abilities au bon timing | def_threat×80 + off_prox×20 + CAP seulement kill/≤2 cases QG allié | **excellente** |
| Opus    | QG catapulte, advance-first, 1 Reconfiguration sélective | advance-first ordering + liberal CAP     | **bonne** (divergence CAP) |

**Analyse :**
- Corrélation claire avec la capacité du modèle : Gemini/ChatGPT (faible→partielle) → Grok (partielle) → Opus (bonne) → Sonnet (excellente)
- **Insight clé :** les modèles plus capables décrivent des styles **opérationnels** directement traduisibles en code. Sonnet dit "def_threat prioritaire" = c'est déjà une fonction de scoring. Opus dit "advance-first" = c'est déjà un algorithme de tri. Gemini dit "zone de sécurité autour du QG" = image abstraite, aucune règle extractable.
- **Gemini** : la révision de style ("siège, fortification") n'a produit aucune différenciation mécanique — le script est identique dans sa structure à la baseline force_hq
- **ChatGPT** : révision majeure du style mais "bulles mortes" et "zone de contrôle" ne se traduisent pas en logique de mouvement/scoring — seul le CAP threshold conservateur (=2) reflète l'intention "tempo précis"
- **Opus** : seule divergence notable — style annonce "1 Reconfiguration sélective/tour" mais le script implémente une CAP libérale (use whenever valid target). La révision du profil a bien guidé l'advance-first mais pas la gestion CAP.

**Conclusion générale :** la capacité du modèle détermine si son raisonnement produit des abstractions implémentables ou des métaphores. Les modèles les plus capables "pensent en algorithmes" sans le formuler explicitement.

---

## Bilan global

### Performance

Le benchmark couvre 7 modèles sources sur 500 parties chacun (4 variants × 125 paires), tous contre la même IA greedy. La progression WR suit globalement la capacité des modèles, avec des exceptions instructives :

- **Opus 4.7 (67%)** et **Sonnet 4.6 (62%)** dominent — leurs mécaniques sont les plus nuancées et les plus directement issues de leur raisonnement
- **ChatGPT (57%)** et **Mistral (57%)** sont à parité, avec des approches différentes (zone contrôle vs défense positionnelle)
- **Haiku v1.2 (54%)** est la baseline — le plancher minimal pour un bot "correct" avec force_hq
- **Gemini (47%)** et **Grok v1.1 (42%)** sous-performent — pour des raisons différentes (descente progressive vs mécanique buggée)

La corrélation la plus forte avec le WR est le **dmg_QG moyen** (dégâts infligés au QG adverse par partie) — les bots qui attaquent le QG tôt et régulièrement gagnent plus, indépendamment de la faction.

### Mécaniques

Trois niveaux de sophistication se dégagent :

1. **Baseline** — force_hq + score kill shot : Haiku v1.2, Gemini (47–54% WR)
2. **Intermédiaire** — conservative CAP threshold + scoring offensif : ChatGPT, Mistral (57% WR)
3. **Avancé** — scoring dual-axis ou ordering dynamique : Sonnet (threat-weighted), Opus (advance-first) (62–67% WR)

Le saut entre niveau 2 et 3 est de ~5–10% WR. La différence entre Sonnet et Opus (5 points) s'explique par l'advance-first : faire agir en premier les unités déjà proches du QG adverse crée une pression cumulée que le greedy ne sait pas contrer.

### Bandit RL

L'over-exploration est le problème systémique majeur — tous les modèles ont exploré ~40 combos sur 500g, laissant peu de jeux sur le combo optimal. Le bandit converge mais trop tard et trop lentement. La bonne nouvelle : champion B est émergé comme dominant dans 4/5 modèles indépendamment — c'est un signal de déséquilibre à investiguer.

Divergence profile/bandit : 4 modèles sur 5 ont changé de faction via le bandit. Seul ChatGPT est resté sur son choix initial (4/B). La faction 4 (Cyborgs), choisie par tous les modèles Claude/Gemini/ChatGPT, est objectivement la plus faible (48% WR agrégé) — les bots Claude s'en sortent malgré ce handicap grâce à la qualité de leurs mécaniques.

### Enseignements pour la suite

| Observation | Action recommandée |
|-------------|-------------------|
| Over-exploration bandit (40 combos / 500g) | Augmenter `min_games_before_switch` ou passer à UCB |
| Champion B dominant (4/5 modèles) | Vérifier le kit champion B — possible déséquilibre de balance |
| Faction 4 la plus faible (48%) malgré adoption massive | Signal de thème > force mécanique dans les choix LLM |
| Draws à 20% pour Gemini/Grok | Investiguer le mécanisme Anchor — timeout structurel |
| Opus advance-first = meilleure mécanique testée | Candidat à intégrer dans la baseline IA greedy |

### Note méthodologique

Tous les modèles ont reçu le même prompt standardisé (`prompt_standard.md`). Cependant, le contexte de calibrage n'est pas uniforme : Haiku, Grok, Gemini, Mistral et ChatGPT ont été interrogés en **context lite**, tandis que Sonnet et Opus ont bénéficié d'un **context complet**. Cela peut partiellement expliquer la qualité supérieure des profils Sonnet/Opus (descriptions plus opérationnelles, révisions plus précises) sans qu'on puisse isoler l'effet contexte de l'effet capacité intrinsèque du modèle.

### Conclusion

L'hypothèse centrale du benchmark est confirmée : **la qualité de raisonnement du modèle source se reflète dans le WR du bot généré**, mais pas via le canal attendu (choix de faction) — via la qualité des mécaniques extraites. Les modèles les plus capables pensent en algorithmes plutôt qu'en métaphores, ce qui rend leur style directement traduisible en code efficace.

Le résultat le plus contre-intuitif est que les modèles qui ont fait le moins bon choix de faction (Sonnet, Opus — tous sur faction 4/8, la pire) ont les meilleurs WR. La mécanique compense largement le handicap faction.

---

## Fichiers liés

**Scripts bots :**
- `engine/ddm_p4_claude.py` — Haiku 4.5
- `engine/ddm_p4_mistral.py` — Mistral Équilibre
- `engine/ddm_p4_grok.py` — Grok Auto
- `engine/ddm_p4_gemini.py` — Gemini Rapide
- `engine/ddm_p4_chatgpt.py` — ChatGPT
- `engine/ddm_p4_sonnet.py` — Sonnet 4.6
- `engine/ddm_p4_opus.py` — Opus 4.7

**Préférences bandit :**
- `data/claude_prefs.json`
- `data/mistral_prefs.json`
- `data/grok_prefs.json`
- `data/gemini_prefs.json`
- `data/chatgpt_prefs.json`
- `data/sonnet_prefs.json`
- `data/opus_prefs.json`

**Profils LLM (choix faction + calibrage) :**
- `rl/rl_logs/Beta_Agent/Claude_Haiku/Haiku4.5_v1.md`
- `rl/rl_logs/Beta_Agent/Grok_Auto/Grok_Auto.md`
- `rl/rl_logs/Beta_Agent/Gemini_Rapide/Gemini_Rapide.md`
- `rl/rl_logs/Beta_Agent/ChatGPT/ChatGPT.md`
- `rl/rl_logs/Beta_Agent/Claude_Sonnet/Sonnet_4.6.md`
- `rl/rl_logs/Beta_Agent/Claude_Opus/Opus_4.7.md`

**Prompt standard LLM :** `<dossier-theorie>\prompt_standard.md`  
**Résultats bruts LLM :** `<dossier-theorie>\results\`
