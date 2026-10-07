# Features Frontend — DDM PyGame

## Menu Principal

### CHARGER PARTIE
**Statut :** Placeholder (`_placeholder()` dans `main()`)
**Complexité :** Élevée — nécessite du travail moteur

Pour fonctionner il faudrait :
- Côté moteur : un mode `--resume <fichier>` qui recharge un `GameState` complet sérialisé (pas juste le snapshot renderer, qui est partiel)
- Côté menu : écran de liste des sauvegardes + relance moteur avec bon état

À ne pas commencer sans décision côté moteur sur le format de sauvegarde.

---

### OPTIONS
**Statut :** Placeholder (`_placeholder()` dans `main()`)
**Complexité :** Faible à moyenne selon le scope

Réglages faisables sans toucher au moteur :
- Vitesse animation dés (`DiceAnim` — durées hardcodées)
- Replay IA B on/off (`IAReplay`)
- Overlay d'aide au démarrage on/off (actuellement `show_help=True` fixe)

Réglages nécessitant le moteur :
- Comportement greedy, niveau de log, etc.

---

## Post-Game (ddm_post_game.py)

### DA / Thème visuel
**Statut :** V1 minimaliste — fonctionnel, pas dans le thème du jeu
**Complexité :** Moyenne

Pistes pour aligner avec le reste du jeu :
- Reprendre palette + éléments visuels du menu (bricks, banners, lava drip)
- Couleurs de factions depuis le JSON plutôt que bleu/rouge générique
- Icônes de faces (ATK/DEF/MOVE) dans les barres stats à la place du texte brut
- Effet glow / particules sur la bannière du camp gagnant
