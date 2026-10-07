# DDM — Glossaire RL
> Termes du dashboard `analyze_jsonl_v2.py` et du système de reward
> Mis à jour : session 20260227 — mémoire inter-tours, new_infiltrator, intercept_kill, factions/champion

---

## Événements JSONL

| Terme | Traduction | Ce que c'est |
|---|---|---|
| `TURN_END` | Fin de tour | Une ligne par tour joué par un camp (A ou B) |
| `EPISODE_END` | Fin de partie | Dernière ligne d'une partie — contient le résultat final |
| `terminal` | Résultat final | `win`, `draw`, `max_rounds` (timeout technique) |
| `player` | Camp actif | `"A"` ou `"B"` — le camp qui vient de jouer |
| `opponent` | Camp adverse | L'autre camp |
| `turn_idx` | Index de tour | Compteur global de demi-tours depuis le début de la partie |
| `run_id` | Identifiant de run | Horodatage du lancement autorun (ex: `20260227_181235_00001`) |
| `game_id` | Identifiant de partie | Identique au run_id pour les parties individuelles |
| `faction_A` | Faction du camp A | Nom complet (ex: `Reptiliens – Légions Scailles-Feu`) |
| `faction_B` | Faction du camp B | Nom complet |
| `champion_A` | Champion du camp A | Nom du champion actif (ex: `Roi-Basilic Thar'Zul`) |
| `champion_B` | Champion du camp B | Nom du champion actif |

---

## Breakdown — signaux individuels

| Clé breakdown | Ce que ça mesure | Poids | Signe |
|---|---|---|---|
| `unused_pool` | Dés non utilisés en fin de tour | -0.001/dé | Proche de 0 |
| `void_action` | Tour sans action exécutée | -0.05 | Proche de 0 — ⚠️ si > 20% |
| `pass_avoidable` | Passe évitable (dés disponibles) | -0.02 | Proche de 0 — ⚠️ si > 15% |
| `my_hq_reachable` | QG allié accessible à l'ennemi | -0.40 | Négatif — défense poreuse |
| `mate_threat` | Unité adjacente au QG adverse | +0.30 | Positif — pression offensive |
| `qg_damage` | Dégâts infligés au QG adverse | +0.05/pt | Positif |
| `kill_enemy` | Unités ennemies éliminées | +0.10 | Positif |
| `lose_self` | Unités alliées perdues | -0.15 | Négatif |
| `hq_threat_delta` | Évolution menace sur notre QG | +0.03 | Positif si on repousse |
| `tempo` | Progression vers QG adverse | +0.02 | Signal de fond |
| `turn_tax` | Malus par tour (incite à finir) | -0.001 | Signal de fond |
| `new_infiltrator` | 1ère détection ennemi dans notre moitié + allié en position | +0.25 one-shot | Positif — alerte défensive |
| `intercept_kill` | Kill ce tour ET ally_intercept vrai au tour précédent | +0.35 | Positif — interception réussie |

---

## Features — état du jeu par tour

| Clé features | Ce que ça capture |
|---|---|
| `dmg_qg` | Dégâts au QG adverse ce tour |
| `kills_enemy` | Kills ce tour |
| `losses_self` | Pertes alliées ce tour |
| `mate_threat` | Bool — unité adjacente au QG adverse |
| `my_hq_reachable` | Bool — QG allié exposé |
| `hq_threats_start/end` | Nb d'ennemis menaçant le QG (début/fin de tour) |
| `min_dist_enemy_hq_start/end` | Distance min allié→QG adverse (début/fin) |
| `unused_pool_total` | Total dés non utilisés ce tour |
| `pass_avoidable` | Bool — la passe était évitable |
| `void_action` | Bool — aucune action ce tour |
| `units_count` | Nb d'unités alliées vivantes — distingue void réel du void RNG |
| `ally_intercept` | Bool — allié positionné entre un infiltrateur et le QG |
| `new_infiltrator` | Bool — nouvel ennemi détecté dans notre moitié + allié en position |
| `intercept_kill` | Bool — kill + ally_intercept était vrai au tour précédent |
| `aggro_seq` | Compteur de tours offensifs consécutifs adverses (mémoire inter-tours) |

---

## Mémoire inter-tours (`rl_memory_A` / `rl_memory_B`)

Structure persistante sur la durée d'une partie, réinitialisée si `game_id` change.

| Clé | Ce que ça stocke |
|---|---|
| `infiltrators_seen` | Set d'ids d'ennemis déjà détectés — évite re-trigger de `new_infiltrator` |
| `ally_intercept_prev` | État `ally_intercept` du tour N-1 — nécessaire pour `intercept_kill` |
| `aggro_seq` | Compteur de kills consécutifs subis — alimente `dynamic_aggro` Reptiliens |
| `kill_turns` | Historique tours de pertes — fenêtre glissante 10 tours |

---

## Dashboard — indicateurs synthèse

| Terme | Ce que ça dit |
|---|---|
| `── Par paire ──` | Résultat par groupe de 4 variants avec factions et champions |
| `P1/base`, `P2/mirror`... | Paire N + variant en cours |
| `void_réel %` | Void uniquement sur tours avec unités — isole l'IA du bruit RNG |
| `dominant ⚠️` | Signal absorbant le plus de reward négatif — priorité de patch |
| `dominant ✓` | Signal générant le plus de reward positif — l'IA joue bien ici |
| `ok ✓` | Contribution < 15% du total — pas prioritaire |
| `⚠️ biais` | Un camp gagne ≥ 75% — biais plateau ou déséquilibre IA |

---

## Variants (cycle de 4 par paire de factions)

| Variant | Description |
|---|---|
| `base` | A joue sa faction, B joue la sienne |
| `mirror` | Factions échangées |
| `sideflip` | Côtés du plateau inversés, mêmes factions |
| `mirror_sideflip` | Factions échangées + côtés inversés |

> Avec N paires (`total = N×4`), chaque paire = un matchup faction distinct.

---

## Profils faction — urgency dynamique

| Faction | Style | `state_w` | `tempo_w` | Spécial |
|---|---|---|---|---|
| Humains | balanced | 0.25 | 0.20 | — |
| Reptiliens | traps | **0.22** | 0.10 | `dynamic_aggro` : boost si `aggro_seq ≥ 2` |
| Égypte | bulwark | 0.10 | 0.05 | `egypt_trigger` : ×3 si QG adverse < 30% HP |
| Cyborgs | control | **0.25** | 0.15 | réactivité opportuniste améliorée |
| Orcs | aggressive | 0.40 | 0.25 | — |
| Lycans | mobile | 0.45 | 0.10 | — |
| Abominations | weird | variable | variable | `abom_champion_mod` selon lettre champion |

---

## Signaux à surveiller en priorité

```
CRITIQUE   unused_pool dominant          → l'IA gaspille ses dés
CRITIQUE   void_action > 20%             → l'IA passe sans jouer
CRITIQUE   void_réel ≈ void_action       → problème IA, pas RNG
IMPORTANT  pass_avoidable > 15%          → l'IA abandonne des dés
IMPORTANT  my_hq_reachable dominant      → QG exposé, défense poreuse
OK         mate_threat positif           → pression offensive ✓
OK         intercept_kill positif        → interceptions qui aboutissent ✓
OK         new_infiltrator positif       → détection défensive fonctionne ✓
```
