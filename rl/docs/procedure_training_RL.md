# Procédure — Mise en place training RL (Jin, Jio, Cross)

> Lire dans l'ordre :
> 1. `benchmark_beta_script_claude.md` — résultats complets des 7 profils
> 2. `agents_Jin_Jio_Cross.md` — architecture des 3 agents et curriculum
> 3. Ce fichier — procédure d'implémentation

---

## Étape 1 — Wrapper gym.Env autour du moteur

Encapsuler le moteur DDM dans une interface compatible Stable Baselines 3.

- Créer `rl/ddm_env.py` héritant de `gym.Env`
- Méthodes à implémenter : `reset()`, `step()`, `render()` (optionnel)
- `step()` doit retourner `(observation, reward, done, info)`
- Utiliser `ddm_reward_v2.py` déjà présent pour le calcul du reward
- L'observation doit encoder l'état du jeu en vecteur numérique (plateau, pool ressources, HP QG, positions unités)

**Ne pas modifier `ddm_p1_core.py` à cette étape.**

---

## Étape 2 — SubprocVecEnv (4 workers)

Les globals dans `ddm_p1_core.py` (`UNITS`, `HQ_POS`, `_UID_SEQ`, `_RL_QG_DMG_PENDING`) empêchent la vectorisation in-process.

- Utiliser `SubprocVecEnv` de SB3 (déjà installé) — chaque worker est un process séparé, les globals sont isolés automatiquement
- **Ne pas utiliser `DummyVecEnv`** — incompatible avec les globals actuels
- Lancer 4 workers (= 4 cœurs physiques disponibles)

```python
from stable_baselines3.common.vec_env import SubprocVecEnv

def make_env():
    def _init():
        return DDMEnv()
    return _init

env = SubprocVecEnv([make_env() for _ in range(4)])
```

---

## Étape 3 — Valider le training sur quelques milliers de parties

Avant de lancer le curriculum complet, valider que la boucle fonctionne :

- Lancer PPO contre le profil Haiku (le plus simple) sur ~5 000 parties
- Vérifier que le WR progresse et que le reward converge
- Vérifier l'absence de corruption entre workers

**Si la validation passe → passer à l'étape 4.**  
**Si problème → déboguer le wrapper avant tout.**

---

## Étape 4 — Curriculum Jin, Jio, Cross

Une fois le training validé, lancer les 3 agents selon leur curriculum :

**Jin & Jio** (ordre standard) :
Haiku → Mistral → Grok → Gemini → ChatGPT → Sonnet → Opus

**Cross** (ordre inversé) :
Opus → Sonnet → ChatGPT → Gemini → Grok → Mistral → Haiku

Critère d'avancement entre profils : à définir (fixe ou conditionnel — voir `agents_Jin_Jio_Cross.md`).

---

## Étape 5 — Refactor globals → GameState (long terme)

**À faire uniquement après validation complète du training.**

Migrer les 4 globals de `ddm_p1_core.py` dans `GameState` :
- `UNITS`
- `HQ_POS`
- `_UID_SEQ`
- `_RL_QG_DMG_PENDING`

Tous les modules qui font `from .ddm_p1_core import *` devront être mis à jour.  
Durée estimée : 2-3 jours.

**Bénéfice** : débloque `DummyVecEnv` — workers légers dans le même process, meilleure performance globale.

---

## Fix bandit (avant ou pendant le training)

Le seuil `+10% WR sur ≥ 20 games` est trop sensible — over-exploration systémique sur tous les profils (40+ combos explorés).

Options :
- Augmenter `min_games_before_switch` (50-100 games minimum)
- Ou remplacer par UCB (Upper Confidence Bound) — évite les switches sur bruit statistique

**À corriger sur tous les scripts profil avant de les utiliser comme adversaires du curriculum.**
