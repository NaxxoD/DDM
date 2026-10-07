# Neosia — Agent RL Méta

> ⚡ Status (2026-05-10) : **Phase 1 TERMINÉE. Neosia est devenu champion absolu**
> dans le tournament 2026-05-10, détrônant jaeha 222-178 (55.5%) sur 400 games.
> Phase 2 (Claude API direct) reste optionnelle.

## Rôle
5e agent RL, méta-agent conçu spécifiquement pour battre Claude API en direct.
Entraîné contre les 4 agents RL (Jin, Jio, Cross, Jaeha) puis spécialisé contre Claude API.

## Concept
Les 4 agents ont absorbé les profils LLM dans leurs poids via leur curriculum.
S'entraîner contre eux = s'entraîner indirectement contre tout le savoir distillé des LLM.
Puis affronter Claude API directement pour la spécialisation finale.

## Curriculum en 2 phases

### Phase 1 — Les 4 agents RL (✅ TERMINÉE 2026-05-10)

**Résultats** :

WR par stage (training, mode exploration) :
- Stage 0 vs rl:jin : 47.0% final
- Stage 1 vs rl:jio : 54.0%
- Stage 2 vs rl:cross : 50.5%
- Stage 3 vs rl:jaeha : 50.0%

Eval déterministe post-Phase 1 (100 games par opponent) :
- vs jin : **64.0%**
- vs jio : 56.0%
- vs cross : **63.0%**
- vs jaeha : 55.0%
- **MEAN : 59.5%**

Tournament confirmation (400 games par boss) :
- vs greedy : **83.5%** (vs jaeha 79.3%)
- vs jaeha : **55.5%** → **Neosia détrône jaeha** 🏆



**Setup** :
- Agent : `neosia`
- Curriculum : `rl:jin → rl:jio → rl:cross → rl:jaeha` (4 stages)
- Steps/stage : 200k (default, 4×200k = 800k total)
- Balance sides : OUI (recommandé après leçons jaeha v1.7)
- Estimation : ~4h sur desktop (56 steps/s en RL-vs-RL)

**Lancement** :
```cmd
launch_neosia_phase1.bat
```

Ou en CLI :
```cmd
python -m rl.train_ppo --agent neosia --curriculum --balance-sides --timesteps-per-stage 200000
```

**Implémentation** : `RL_AGENT_CKPT` dans `rl/ddm_env.py` mappe `rl:<agent>` → checkpoint PPO.
Lazy load + cache par worker. Le mécanisme `_make_rl_opponent_fn` swap temporairement
`rl_side` pendant que l'opponent RL agit, puis restore.

### Phase 2 — Claude API direct (✅ wrapper prêt, en attente API key)

**Setup** :
- Agent : `neosia`
- Opponent : `claude_api`
- Load : `rl/checkpoints/neosia/neosia_final.zip` (depuis phase 1)
- Steps : 50-200k selon budget API
- Modèle Claude par défaut : `claude-haiku-4-5-20251001` (le moins cher)
- Estimation budget API : ~$50-200 selon timesteps et modèle

**Pré-requis** :
1. Compte console.anthropic.com créé
2. ANTHROPIC_API_KEY définie en env var (`setx ANTHROPIC_API_KEY sk-ant-xxx`)
3. `pip install anthropic`
4. Crédits prépayés (recommandé : 20-50€ pour démarrer)

**Lancement** (à coder, launch_neosia_phase2.bat) :
```cmd
python -m rl.train_ppo ^
    --agent neosia ^
    --opponent claude_api ^
    --load rl/checkpoints/neosia/neosia_final.zip ^
    --balance-sides ^
    --timesteps 100000 ^
    --save-dir rl/checkpoints/neosia_phase2
```

**Implémentation** : `engine/ddm_p4_claude_api.py` sérialise le state engine en JSON,
envoie à Claude API, parse la réponse en liste d'actions (0-4 par unité, format
identique au DDMEnv action space), applique via les helpers du moteur.

Fallback greedy si l'API échoue (`DDM_CLAUDE_API_FALLBACK=1` par défaut).

## Question de recherche

Est-ce qu'un RL entraîné spécifiquement contre un LLM peut le battre de façon consistante ?

Sous-questions :
- Phase 1 seule suffit-elle (les RL sont des "distillations" des LLM heuristiques) ?
- Phase 2 ajoute-t-elle vraiment de la valeur ?
- Comparaison Jio v2b vs Claude API (sans entraînement spécifique) = baseline à mesurer
  AVANT phase 2 pour calibrer le ROI.

## Test gating Jio vs Claude API (à faire avant Neosia phase 2)

```cmd
python -m rl.bracket pair --side-a jio --side-b claude_api ^
    --games 100 --seed 42 ^
    --out reports/bracket/jio_vs_claude_api_haiku.jsonl
```

Coût estimé : ~$10-15 (Haiku, 100 games, ~50 API calls par game).

Décisions selon résultat :

| Jio vs Claude | Décision Neosia |
|---|---|
| Jio gagne 55%+ | Pipeline marche → Neosia faible ROI, à faire seulement pour l'élégance |
| Jio gagne 30-45% | Marge claire à exploiter → Neosia justifié |
| Jio gagne <25% | Claude domine → Neosia probablement insuffisant sans compute massif |

## Dépendances (état actuel)

- ✅ Jin, Jio, Cross, Jaeha disponibles en prod (v1.7 ou v2b)
- ✅ Wrapper Claude API codé (`engine/ddm_p4_claude_api.py`)
- ✅ Extension `train_ppo.py` (--agent neosia, --opponent rl:<agent>, --opponent claude_api)
- ✅ Extension `bracket.py` (side_b peut être "claude_api" pour test gating)
- ❌ API key Anthropic (à créer)
- ❌ Package anthropic Python (`pip install anthropic`)

## À implémenter (suite)

- [ ] launch_neosia_phase2.bat (après phase 1 + API key)
- [ ] Test gating Jio vs Claude API (~$10-15 Haiku)
- [ ] Mesure post-phase 1 : Neosia vs les 4 RL et vs Claude API
- [ ] Décision : continue phase 2 ou skip selon ROI

## Différences avec les autres agents

- Jin : curriculum easy → hard (claude → opus)
- Jio : même curriculum que Jin, mesure de variance
- Cross : curriculum hard → easy (opus → claude)
- Jaeha : greedy first + curriculum random
- **Neosia** : méta-agent, entraîné sur les 4 RL puis spécialisé Claude API

## Notes

- Phase 1 utilise `RL_AGENT_CKPT` (dans ddm_env.py) pour mapper `rl:<agent>` → checkpoint
  Donc si on change la prod (ex: jio v2b → v2c), il faut update `RL_AGENT_CKPT`.
- Les 4 RL en sparring sont mix balanced (v1.7) + non-balanced (jio v2b). C'est OK :
  diversity > homogénéité pour Neosia.
- Le `--balance-sides` est appliqué à Neosia pendant son training (équilibre A/B).
- Estimation totale (phase 1 + phase 2) : ~4h compute + budget API
- Si le test gating montre que Jio bat déjà Claude, on peut skip Neosia et juste
  publier "RL standard bat Claude" — encore plus impressionnant que "RL spécialisé".
