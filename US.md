# DDM — User Stories

## Statuts : ✅ Fait | 🟡 Partiel | ❌ A faire

*Dernière mise à jour : 2026-10-06 (vérifié contre le code ; statuts non testés en jeu marqués ⚠️).*

---

## Bloc 1 — Jouer une partie

| ID | User Story | Statut |
|----|-----------|--------|
| US-1 | En tant que joueur, je peux lancer une partie HvIA contre un profil scripté (greedy, haiku, gemini, chatgpt, mistral, grok, sonnet, opus, deepseek, qwen3, glm) ou `claude_api` (seul profil qui appelle un modèle) | ✅ |
| US-2 | En tant que spectateur, je peux observer un match IAvIA entre deux profils | ✅ |
| US-3 | En tant que joueur, je peux configurer mon sac de dés (Standard / Étendu / Perso) et drafter mon armée | ✅ |
| US-4 | En tant que joueur, je peux lire le bilan post-partie (factions, tours, unités, QG HP, répartition dés) | ✅ |
| US-5 | En tant que joueur, je peux mettre en pause et quitter proprement pendant une partie | ✅ |
| US-6 | En tant que joueur, je peux choisir un agent RL comme adversaire (Jin / Jio / Cross / Jaeha / Neosia / Zenom) | ✅ 7 checkpoints câblés dans `_AI_REGISTRY` (jin, jio, cross, jaeha, neosia, zenom, zenom_frozen). Checkpoints locaux, non versionnés. Zenom : curriculum Phase 1 + self-play Phase 2 faits, champion du tournoi Phase 7 (72 %, 22 mai). ⚠️ Un compact de juin mentionne un repli sur greedy quand le module/checkpoint est indisponible (`ddm_p4_turn.py:349`) : à vérifier en jeu |

---

## Bloc 2 — Progression et profondeur

| ID | User Story | Statut |
|----|-----------|--------|
| US-7 | En tant que joueur, je peux consulter mon historique de parties (win/loss, adversaires joués) | ❌ (les logs de parties existent, sans écran de consultation) |
| US-8 | En tant que joueur, les agents RL se débloquent progressivement par ordre de difficulté | ❌ (le mode Tournoi les enchaîne en bracket, sans déblocage persistant) |
| US-9 | En tant que joueur, je vois les stats de l'adversaire choisi avant de confirmer (WR, style, points forts) | ❌ (données prêtes : `data/faction_stats.json`, WR des profils dans `AGENTS_RECAP.md` ; pas d'affichage) |

---

## Bloc 3 — Compréhension du jeu

| ID | User Story | Statut |
|----|-----------|--------|
| US-10 | En tant que joueur, je peux consulter le WikiDDM in-game (fiches factions, unités, abilities) | 🟡 Entrée « ENCYCLOPEDIE » dans le menu (`pygame/ddm_encyclopedia.py`). ⚠️ Complétude non vérifiée |
| US-11 | En tant que spectateur, je peux suivre le replay détaillé de chaque tour IA | 🟡 IAReplay partiel |
| US-12 | En tant que joueur, je comprends pourquoi j'ai perdu — analyse post-partie (placement, pool, erreurs) | ❌ |

---

## Bloc 4 — Accessibilité

| ID | User Story | Statut |
|----|-----------|--------|
| US-13 | En tant que nouveau joueur, un tutoriel guidé s'affiche au premier lancement | ❌ |
| US-14 | En tant que joueur, je peux sauvegarder une partie en cours et la reprendre plus tard | ❌ (« CHARGER PARTIE » = placeholder dans le menu) |

---

## Bloc 5 — Fin de jeu et meta

| ID | User Story | Statut |
|----|-----------|--------|
| US-15 | En tant que joueur, je peux battre tous les agents RL par ordre de difficulté (progression "campagne") | 🟡 Mode Tournoi dans le menu : bracket LLM + RL, boss final Zenom. Pas de progression persistante |
| US-16 | En tant que spectateur, je peux lancer le bracket visuel tournoi | ✅ standalone (`ddm_bracket.py`) et intégré au menu (Tournoi) |

---

## Bugs connus

- Données d'unités incohérentes : Miroir Glitché / Inverseur Mineur (`swap_positions` ≠ texte). Trois règles de déplacement différentes (IA, GUI, stat `move` inutilisée).
- Build 3 exe (menu/engine/renderer, juin) jamais testé en profondeur.
- Touche **F** (fin de phase) sans effet dans le renderer — signalé 2026-10-06, cause non identifiée (voir `pygame/Probleme.md`).

---

## Priorités suggérées (court terme)

1. **Bug touche F** — diagnostiquer (phase d'invocation vs actions, animation, état WAITING)
2. **US-9** — Infos adversaire dans l'écran de sélection (impact immédiat, dev léger)
3. **US-12** — Enrichir l'écran post-partie avec analyse (pool utilisé, erreurs clés)
4. **US-14** — Sauvegarde / reprise de partie
5. **US-10** — Vérifier et compléter l'encyclopédie
