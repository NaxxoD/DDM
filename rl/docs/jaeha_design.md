# Jaeha — Agent RL Challenger

## Rôle
4e agent RL, challenger des 3 premiers (Jin, Jio, Cross).
Design volontairement différent : généraliste/explorateur vs spécialiste curriculum.

## Curriculum en 3 phases

### Phase 1 — Greedy only
- Adversaire : greedy bot uniquement
- Steps : 300 000-400 000 (plus long que les autres stages car 8 factions à explorer)
- Objectif principal : connaissance meta des factions/champions, pas juste le WR
- Objectif secondaire : WR solide contre le greedy

### Phase 2 — Curriculum aléatoire
- Les 7 profils LLM (claude, mistral, grok, gemini, chatgpt, sonnet, opus)
- Ordre re-tiré aléatoirement à chaque relance — jamais le même
- Steps : 150 000 par profil (comme Jin/Jio/Cross)
- Objectif : généralisation, pas d'adaptation à une difficulté progressive fixe

### Phase 3 — Bracket final
- Affronte Jin, Jio, Cross dans l'ordre du plus faible au plus fort
  (classement basé sur leur WR respectif contre le greedy)
- Objectif : battre le n°1 et devenir le meilleur agent

## Commandes à implémenter

```
# Phase 1
python -m rl.train_ppo --agent jaeha --opponent greedy --timesteps 350000

# Phase 2 (ordre random auto à implémenter dans train_ppo)
python -m rl.train_ppo --agent jaeha --curriculum-random --timesteps-per-stage 150000

# Reprendre depuis checkpoint
python -m rl.train_ppo --agent jaeha --load rl/checkpoints/v1/jaeha/jaeha_greedy_final.zip --curriculum-random --timesteps-per-stage 150000
```

## À implémenter dans train_ppo.py
- Ajouter `--curriculum-random` flag
- Ajouter `jaeha` dans les choix `--agent`
- Phase 1 : greedy déjà disponible comme opponent
- Phase 2 : shuffle aléatoire de CURRICULUM_STANDARD à chaque run

## Notes
- Jin/Jio : curriculum easy → hard, mesure variance
- Cross : curriculum hard → easy, mesure impact de l'ordre
- Jaeha : greedy first + random, mesure généralisation
- Bracket final : Cross → Jio → Jin (ordre à confirmer après éval greedy des 3)
