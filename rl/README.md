# DDM — Reinforcement Learning

Pipeline d'entraînement et d'évaluation des agents RL pour le moteur DDM.

## Structure

```
rl/
├── ddm_env.py              # Gym wrapper autour du moteur (obs/action/reward)
├── ddm_reward_v2.py        # Calcul reward multi-signal
├── train_ppo.py            # Entraînement PPO (curriculum, custom, random)
├── eval_agent.py           # Eval matricielle faction×champion vs LLM/greedy
├── bracket.py              # Bracket RL vs RL + boss greedy
├── analyze_jsonl_v2.py     # Analyse logs reward JSONL
├── build_jaeha_empirical.py# Matrice empirique Jaeha (curriculum random)
├── _bench_vec.py           # Bench SubprocVecEnv

├── docs/                   # Documentation
│   ├── agents_RL_overview.md  # Vue d'ensemble Jin/Jio/Cross/Jaeha + résultats
│   ├── glossaire_rl_ddm.md    # Glossaire signaux reward / metrics
│   ├── jaeha_design.md        # Design Jaeha (greedy + random curriculum)
│   ├── neosia_design.md       # Design Neosia (anti-Claude API, 5e agent)
│   └── jaeha_empirical.md     # Output build_jaeha_empirical.py

├── checkpoints/
│   ├── v1/{agent}/         # Curriculum standard 7×150k (claude→opus)
│   ├── v1.5/{agent}/       # Test inversion ordre (hard→easy ou easy→hard)
│   ├── v1.5/jaeha_repeat/  # Run jaeha en boucle (matrice empirique)
│   ├── v2/v2{a,b,c,d}/     # Interleaved curriculum (4 variantes × 3 agents)
│   ├── eval_multiseed/     # Eval reproductible 3 seeds (référence)
│   └── eval_monoseed/      # Eval mono-seed (déprécié, env déterministe)

└── _archive/               # Anciens fichiers / logs pré-v1
    ├── DDM — TABLE BONUS MALUS (Draft v0).txt
    ├── Training/Baseline RL v0.txt
    └── rl_logs/            # Beta_Agent, v0.0.x, v0.1.0
```

## Checkpoints de production (post-eval 2026-05-08)

| Agent | Checkpoint | WR opus | Source |
|---|---|--:|---|
| jaeha | `v1.5/jaeha/jaeha_final.zip` | 62.1% | curriculum mistral 1.55M |
| cross | `v2/v2d/cross/cross_final.zip` | 70.5% | opus + grok/gemini |
| jio | `v2/v2b/jio/jio_final.zip` | 73.1% | sonnet + grok/gemini |
| jin | `v1/jin/jin_claude_final.zip` | 72.1% | curriculum standard |

Les paths utilisés par `bracket.py` sont définis dans `AGENT_CKPT` (rl/bracket.py).

## Workflows

### Entraîner un agent
```
python -m rl.train_ppo --agent jin --curriculum --timesteps-per-stage 150000
```

### Evaluer vs LLM
```
python -m rl.eval_agent --agent jin --checkpoint rl/checkpoints/v1/jin/jin_claude_final.zip --opponent opus
```

### Eval multiseed reproductible (recommandé)
```
launch_eval_multiseed.bat                        # 24 evals, 6 batches
python tools/scripts/compare_eval_multiseed.py
```

### Bracket RL vs RL
```
launch_bracket.bat <run_name> both 50            # ~40 min, complet
launch_bracket.bat <run_name> matrix 50          # ~30 min, matrice seule
tools/scripts/watch_bracket.bat <run_name>       # dashboard live
```

### Analyse rewards JSONL
```
python rl/analyze_jsonl_v2.py path/to/log.jsonl
```

## Adversaires

| Type | Tag | Source |
|---|---|---|
| Greedy | `greedy` | `engine/ddm_p4_ai.py` |
| LLM heuristics | `claude`, `mistral`, `grok`, `gemini`, `chatgpt`, `sonnet`, `opus` | `engine/ddm_p4_<llm>.py` |
| RL agent | `rl:<agent>` (uniquement via `bracket.py`) | checkpoints |
