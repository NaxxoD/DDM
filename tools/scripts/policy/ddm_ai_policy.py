import json
from pathlib import Path

# Chargé une fois au démarrage
POLICY_PATH = Path("ddm_invocation_policy.json")
with POLICY_PATH.open("r", encoding="utf-8") as f:
    INVOC_POLICY = json.load(f)


def choose_invocation_action(stars, available_levels, policy=INVOC_POLICY):
    """
    stars : nb d'étoiles ce tour-ci
    available_levels : liste des niveaux (1..5) que l'IA PEUT invoquer
    policy : dict chargé depuis ddm_invocation_policy.json
    """
    candidates = []

    # Option "ne rien invoquer"
    key_none = f"{stars}::none"
    if key_none in policy:
        candidates.append(("none", policy[key_none]))

    # Options "invoquer Lx"
    for lvl in available_levels:
        key = f"{stars}::invoke_L{lvl}"
        if key in policy:
            candidates.append((f"invoke_L{lvl}", policy[key]))

    if not candidates:
        # Pas de data -> fallback safe
        return "none"

    # Optionnel : virer les actions avec trop peu de samples (ex < 10)
    filtered = [c for c in candidates if c[1]["count"] >= 10]
    if filtered:
        candidates = filtered

    # Choix : meilleure winrate
    best_action, best_stats = max(candidates, key=lambda c: c[1]["winrate"])
    return best_action
