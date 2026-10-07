# Contexte — Agents RL : Jin, Jio, Cross

> Lire le benchmark complet avant ce fichier : `benchmark_beta_script_claude.md`

---

## Architecture générale

Le système compte 11 entités :

- **1 greedy** — bot brut, optimisation locale pure, sélection faction aléatoire
- **7 profils LLM** — scripts distillés depuis les réponses de modèles réels (voir benchmark)
- **3 agents RL** — Jin, Jio, Cross — la cible finale du système

---

## Les 3 agents

### Jin & Jio — curriculum standard
Entraînement séquentiel dans l'ordre de création des profils :

**Haiku → Mistral → Grok → Gemini → ChatGPT → Sonnet → Opus**

Progression globalement du plus faible au plus fort (42%–67% WR vs greedy).  
Jin et Jio partagent le même curriculum — l'objectif est de mesurer la variance naturelle entre deux agents identiquement entraînés.

### Cross — curriculum inversé
Entraînement dans l'ordre inverse :

**Opus → Sonnet → ChatGPT → Gemini → Grok → Mistral → Haiku**

Commence par l'adversaire le plus fort. L'objectif est de mesurer l'impact de l'ordre d'exposition sur le style émergent de l'agent.

---

## Critère d'avancement dans le curriculum

À définir — deux options :
- **Fixe** : X parties par profil, peu importe les résultats (simple, reproductible)
- **Conditionnel** : avance quand WR dépasse un seuil sur N parties (vrai curriculum learning, mais risque over-exploration — cf. bug bandit Grok)

---

## Bracket final

Une fois les 3 agents entraînés :

1. **Play-in** : Jin vs Jio vs Cross — bracket entre les 3
2. **Perdant** → retour entraînement vs les 7 profils
3. **Vainqueur** → confrontation vs greedy en aveugle (test de généralisation)
4. Après la finale, faire passer les 3 agents contre le greedy pour avoir les 3 mesures comparatives

---

## Signaux de balance à surveiller pendant le training

### 1. Champion B dominant
4/5 bandits ont convergé indépendamment sur champion B (62.6% WR agrégé, 2e meilleur toutes factions).  
**Risque** : les agents vont potentiellement sur-apprendre à exploiter B.  
**Action** : monitorer la distribution faction/champion des agents en cours d'entraînement.

### 2. Faction 3 (Conclave Abyssal) — angle mort du pool
Faction la plus forte mécaniquement (69% WR agrégé) mais jamais choisie par aucun profil LLM.  
Le greedy peut la jouer aléatoirement mais aucun profil ne l'exploite activement.  
**Risque** : les agents n'y sont jamais confrontés de façon répétée — généralisation potentiellement faible contre ce style.

### 3. Over-exploration bandit (systémique)
Tous les profils ont exploré ~40 combos sur 500 parties — le seuil `+10% WR sur ≥ 20 games` est trop sensible.  
**À corriger avant le training RL** : augmenter `min_games_before_switch` ou passer à UCB.

---

## Mécanique de référence par niveau

| Niveau       | Modèles              | WR    | Mécanique clé                          |
|--------------|----------------------|-------|----------------------------------------|
| Baseline     | Haiku, Gemini        | 47–54% | force_hq + kill shot simple           |
| Intermédiaire| ChatGPT, Mistral     | 57%   | CAP threshold + scoring offensif       |
| Avancé       | Sonnet, Opus         | 62–67% | Threat-weighted (Sonnet) / Advance-first (Opus) |

**Meilleure mécanique identifiée** : advance-first ordering (Opus) — candidat à intégrer dans la baseline greedy pour la phase finale.

---

## Note méthodologique

Haiku, Grok, Gemini, Mistral, ChatGPT → context lite  
Sonnet, Opus → context complet

La différence de contexte peut partiellement expliquer la qualité supérieure des profils Sonnet/Opus, sans qu'on puisse isoler cet effet de la capacité intrinsèque du modèle.
