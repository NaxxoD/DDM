# Problèmes connus — DDM Frontend

## [LATENT] ability_targeted — détection incomplète

**Fichiers concernés :**
- `ddm_snapshot.py` ligne 26 — `_ability_needs_target()` (version snapshot)
- `ddm_p3_mechanics.py` ligne 1313 — `ability_needs_target()` (version mécanique)

**Description :**
La détection des abilities nécessitant un ciblage manuel repose sur du texte brut (`raw_text`) et non sur le type d'ability. Les deux fonctions ne sont pas synchronisées :
- `ddm_snapshot.py` couvre : `etype == "teleport"` + mots-clés brume/toxique/zone de brume
- `ddm_p3_mechanics.py` couvre : mots-clés brume/toxique/zone de brume seulement (teleport absent)

**Impact si raté :**
Si une nouvelle ability ciblée est ajoutée au JSON sans les mots-clés détectés et sans `etype == "teleport"` :
1. Appui sur C → ability envoyée immédiatement au moteur **sans cible**
2. Overlay de portée absent (pas d'entrée en mode `CAP_TARGET`)
3. Hover de ciblage (`cap_hov`) inactif

C'est un bug comportemental et visuel, pas uniquement cosmétique.

**Statut :** Pas de bug aujourd'hui (31 types couverts, cas ciblés = brume/toxique/teleport). Fragilité à surveiller si le JSON évolue.

**Correction à faire si nécessaire :**
Ajouter le nouvel `etype` dans les deux fonctions + dans le tableau `supported` de `ddm_p3_mechanics.py` (`use_unit_ability`).
