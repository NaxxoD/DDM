# DDM — Dungeon Dice Monsters

Jeu de stratégie tactique au tour par tour, basé sur les dés, avec un moteur de règles en Python,
une interface PyGame et un banc d'essai d'agents IA (profils scriptés et agents entraînés par
apprentissage par renforcement).

Projet personnel en cours de développement. Cette page est une **vitrine** : un instantané de la
version stable, sans l'historique de développement.

## Le jeu

- **8 factions**, chacune avec ses champions et ses unités. Tout le contenu (factions, champions,
  unités, capacités) est décrit dans `data/Data_8_Factions.json`.
- Les unités sont invoquées avec des **dés** puis placées sur la grille sous forme de **formes**
  (shapes). Un sac de dés alimente quatre réserves : déplacement, attaque, défense et capacité.
- Trois modes de sac : **Standard**, **Étendu** et **Perso**, avec un draft d'armée pour les deux
  derniers.
- Modes de jeu : Humain contre IA, IA contre IA, et un **mode Tournoi**
  (bracket entre profils scriptés et agents RL, avec un boss final).

## Architecture

Le moteur est découpé en couches, chacune n'important que celles du dessous :

| Module | Rôle |
|--------|------|
| `engine/ddm_p1_core.py` | Modèles d'état, chargement des données, journalisation |
| `engine/ddm_p2_board_dice.py` | Plateau, placement des formes, économie de dés |
| `engine/ddm_p3_mechanics.py` | Règles : invocation, combat, capacités, statuts, pièges |
| `engine/ddm_p4_loop.py` | Boucle de jeu, arguments CLI, conditions de victoire, dispatch des modes |

Le frontend PyGame (`pygame/`) tourne dans un processus séparé du moteur. Les deux communiquent
uniquement par fichiers (`engine/snapshots/`), sans sockets.

## Agents IA

- **11 profils scriptés** (greedy, haiku, gemini, chatgpt, mistral, grok, sonnet, opus, deepseek,
  qwen3, glm) : des heuristiques écrites en Python, dont la « philosophie » a été conçue avec
  chaque modèle. Aucun modèle ne tourne pendant la partie.
- **`claude_api`** : seul profil qui appelle un modèle de langage en direct (clé API requise).
- **6 agents RL** (Jin, Jio, Cross, Jaeha, Néosia, Zenom) : agents PPO entraînés avec
  Stable-Baselines3 sur un environnement Gymnasium (`rl/`).

## Lancer le moteur

Dépendances Python : `numpy`, `gymnasium`, `stable_baselines3` (agents RL), `pygame` (interface),
`anthropic` (profil `claude_api`, optionnel).

Partie IA contre IA en ligne de commande :

```bash
python -m engine.ddm_p4_loop --mode iaia --seed 123 --bag 11 --max-rounds 120
```

Partie interactive en console : `python -m engine.cli_main`.

## Ce qui n'est pas dans ce dépôt

- Les **sprites** et autres assets graphiques (`assets/`) : l'interface PyGame ne peut donc pas
  démarrer à partir de ce dépôt seul.
- Les **checkpoints RL** (`rl/checkpoints/`) : les agents entraînés ne sont pas fournis.
- Les journaux de parties et les rapports de tournois.

## Documents

- [US.md](US.md) : user stories et état d'avancement.
