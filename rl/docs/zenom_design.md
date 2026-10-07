# Zenom — Agent RL Méta-final

## Rôle
6e agent RL, sommet de la pyramide. Conçu pour être **robuste max contre toute la roster**
(greedy + 7 LLM heuristiques + 4 RL Jin/Jio/Cross/Jaeha + Neosia).
Doit battre tous les autres agents en moyenne, ou au minimum n'avoir aucun matchup
exploitable.

## Concept
Là où :
- Les 4 RL distillent les **profils LLM**
- Neosia distille **Claude API** spécifiquement
- Zenom distille **toute la pile** simultanément

Pas un specialist anti-X. Un généraliste robuste qui exploite la diversité de la roster
pour ne laisser aucune faille.

## Deux versions à explorer

### Version A — Ensemble exploiter (pragmatique, recommandée en premier)

Agent entraîné contre la roster complète en random :
- greedy bot
- 7 profils LLM scriptés (claude, sonnet, opus, mistral, grok, gemini, chatgpt)
- Jin / Jio / Cross / Jaeha (RL)
- Neosia (RL spécialisé)
- = jusqu'à 13 adversaires

Chaque épisode tire un opponent aléatoire (uniforme ou pondéré par difficulté).
Apprend **une seule policy robuste à tous**.

**Architecture** : PPO standard, MlpPolicy. Pas de changement structurel.

**Coût** : ~1M-1.5M steps de training (~12-20h sur desktop).

**Implémentation** :
- Étendre `train_ppo.py` pour accepter pool d'opponents (mix LLM + RL)
- Mécanisme de hot-swap d'opponent par épisode (méthode déjà partiellement en place
  via `_set_opponent`)
- Pour les RL opponents : load checkpoints en mémoire, predict pendant training
- Latence : ~1ms par tour pour predict d'un PPO opponent
- Pour 13 opponents : RAM ~5-6 GB (chaque PPO en mémoire), pas un problème sur desktop

### Version B — Meta-game adaptive (ambitieuse, optionnelle)

Architecture neural plus complexe avec mémoire récurrente. L'agent **détecte le type
d'adversaire** en début de partie et **adapte sa stratégie** au cours des tours.

**Approches possibles** :

1. **LSTM/Transformer policy** : la policy a une mémoire récurrente. Au cours des
   premiers tours, elle observe les patterns adverses (timing d'invocation, choix
   d'attaques, mouvement) et infère implicitement le type d'opponent.

2. **Hierarchical RL** : Zenom a N sub-policies (une par "type" d'opponent prédéfini).
   Une meta-policy choisit la sub-policy active au tour 5-10 selon les observations
   accumulées.

3. **Population-based training** : Zenom est en fait un ensemble de policies, et un
   selector apprend à choisir la bonne au runtime.

**Architecture** : sortir de stable_baselines3 PPO standard, peut-être passer à RLlib
ou implémentation custom.

**Coût** : ~2-3M steps (~30-40h) + ~1-2 semaines de dev architecture.

**Risques** :
- LSTM RL est notoirement difficile à converger
- Évaluation plus complexe (faut tester contre opponents jamais vus en training)
- Maintenance lourde si architecture custom

## Question de recherche

Est-ce qu'un seul agent peut battre **toute** une roster diversifiée d'agents
(heuristiques + RL spécialisés) sans avoir de point faible exploitable ?

Hypothèse forte : oui, parce que la diversité de la roster en training comble
naturellement les angles morts.

## Dépendances

- Requiert que **tous les autres agents soient finalisés et stables** :
  - Jin, Jio, Cross, Jaeha (RL généralistes) : ✅ disponibles, en cours d'amélioration v1.7
  - Neosia (specialist anti-Claude) : à entraîner avant
  - 7 profils LLM scriptés : ✅ stables
- Requiert l'implémentation de RL-vs-RL training dans `train_ppo.py` (extension du
  mécanisme actuel qui ne supporte que les heuristiques + greedy)
- Pas d'API call (différence avec Neosia) → 100% offline et reproductible
- Engine stable (sinon retraining à chaque migration moteur, comme on l'a vu)

## À implémenter

### Pour Version A
- Extension `train_ppo.py` : flag `--opponents-pool` qui accepte une liste mixte
  (`greedy,claude,jin,jio,...`)
- Mécanisme de chargement multiple PPO en mémoire au démarrage
- Hot-swap d'opponent par épisode (déjà existe pour LLM heuristiques, à étendre RL)
- Ajouter `zenom` dans les choix `--agent` de `train_ppo.py`
- Save dir convention : `rl/checkpoints/zenom/`

### Pour Version B (additionnel)
- Architecture neural avec LSTM/Transformer (custom policy class SB3 ou switch RLlib)
- Logique de détection opponent (analyse statistique des premiers tours)
- Eval framework spécifique pour mesurer la capacité d'adaptation

## Mode de validation (à la fin)

1. **Bracket Zenom contre tous** : matrix complète Zenom vs chaque agent + greedy
2. **WR moyen attendu** : >= 70% sur tous les opponents (si <= 60% sur certains, c'est
   une faille à creuser)
3. **Test contre opponents jamais vus** (si Version B) : tenir un opponent en réserve
   pendant le training, l'utiliser uniquement en eval pour mesurer la généralisation
   pure

## Hiérarchie de la roster (vision long-terme)

```
greedy bot                    (baseline)
   ↓
7 profils LLM scriptés        (curriculum + référence)
   ↓
RL Jin/Jio/Cross/Jaeha        (challengers généralistes)
   ↓
Neosia                        (specialist anti-LLM Claude)
   ↓
Zenom                         (meta-agent ensemble / adaptive)
   ↓
[futur agent vs Zenom ?]      (anti-meta, si jamais nécessaire)
```

Zenom = sommet de la pyramide actuelle. Tout ce qui vient après devra le battre.

## Recommandation pratique

**Faire Version A en premier**. Elle donne 80% du bénéfice pour 30% du coût.
Si Zenom Version A plafonne à un niveau insatisfaisant ou si tu veux pousser la
recherche, alors Version B (adaptive).

Décision finale conditionnelle aux résultats de Neosia : si Neosia bat Claude API
nettement, Zenom est moins urgent (la pile est déjà solide). Si Neosia est mitigé,
Zenom devient utile pour avoir un agent de référence robuste.

## Notes

- Nom initial proposé "Sephira", renommé "Zenom" (le N de Neosia + sens "demon"/sommet)
- Chronologie : à entraîner après Neosia, idéalement quand le moteur est stable depuis
  longtemps (sinon retraining à chaque migration)
- Différence clé vs Neosia : Zenom est offline (pas d'API), Neosia est en partie online
- Différence clé vs Jin/Jio/Cross/Jaeha : Zenom voit aussi des RL en training,
  pas juste des heuristiques
