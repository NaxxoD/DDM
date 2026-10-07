

from .ddm_p1_core import *

#  BOARD HELPERS + UX
# ----------------------------------------------------------------------

def in_bounds(board, r, c):
    """Return True if (r,c) is inside the board."""
    return 0 <= r < len(board) and 0 <= c < len(board[0])

def _is_free_for_shape(ch):
    """Cells a shape may occupy during invocation placement."""
    return ch == EMPTY or (isinstance(ch, str) and ch.isdigit())


def create_board(flip_sides: bool = False):
    board = [[EMPTY for _ in range(WIDTH)] for _ in range(HEIGHT)]

    # HQ positions (canon, with optional sideflip)
    if not flip_sides:
        rB, cB = 0, WIDTH // 2
        rA, cA = HEIGHT - 1, WIDTH // 2
    else:
        # swap spawns: B at bottom, A at top
        rB, cB = HEIGHT - 1, WIDTH // 2
        rA, cA = 0, WIDTH // 2

    board[rB][cB] = P2_QG
    HQ_POS['B'] = (rB, cB)

    board[rA][cA] = P1_QG
    HQ_POS['A'] = (rA, cA)

    # Plateau vide : QG seuls, pas de tuiles initiales
    # Les territoires se construisent depuis zéro via les invocations
    # La zone protégée autour du QG est créée uniquement au trigger despair

    return board


def unit_label(owner: str, idx: int) -> str:
    """Id visuel par unité : A = 0..9, B = k..t (évite conflit avec a/b chemins)."""
    if owner == 'A':
        return str(idx % 10)
    base = ord('k')
    return chr(base + (idx % 10))


def build_board_with_units(state: GameState, focus_unit: Unit | None = None):
    temp = [row[:] for row in state.board]

    for idx, u in enumerate(UNITS['A']):
        ch = unit_label('A', idx)
        temp[u.row][u.col] = ch

    for idx, u in enumerate(UNITS['B']):
        ch = unit_label('B', idx)
        temp[u.row][u.col] = ch

    if focus_unit is not None:
        temp[focus_unit.row][focus_unit.col] = '@'

    return temp


def lines_with_coords(temp_board):
    col_labels = "0123456789ABCDEF"[:WIDTH]
    lines = []
    lines.append("   " + col_labels)
    for r in range(HEIGHT):
        lines.append(f"{r:2d} " + ''.join(temp_board[r]))
    return lines


def pool_to_str(pool):
    parts = [
        f"MOVE={pool.get('MOVE',0)}",
        f"ATK={pool.get('ATK',0)}",
        f"DEF={pool.get('DEF',0)}",
        f"CAP={pool.get('CAP',0)}",
    ]
    return " ".join(parts)


def render_ui(state: GameState):
    """
    Affiche :
      [ Panneau Joueur A ]   [ Plateau ]   [ Panneau IA B ]
    avec un seul écran lisible.
    """
    temp = build_board_with_units(state)
    board_lines = lines_with_coords(temp)

    # --- Panneau gauche : Joueur A ---
    left_panel_lines = []
    left_panel_lines.append(f"[Tour {state.turn} - Joueur "
                            f"{'A' if state.current_player == 1 else 'B'}]")
    left_panel_lines.append("")

    # QG A
    hqA_def_eff = state.get_hq_effective_def('A')
    left_panel_lines.append(f"=== Joueur A (Faction: {state.hero_A['faction']}) ===")
    left_panel_lines.append(
        f"QG : HP {state.hq_A_hp:2d}/{state.hq_A_hp_max:2d}   DEF : {hqA_def_eff:2d}"
    )
    left_panel_lines.append(
        f"Champion : {state.hero_A['name']} "
        f"(HP={state.hero_A['hp']}, ATK={state.hero_A['atk']}, DEF={state.hero_A['def']})"
    )
    left_panel_lines.append(f"Pool: {pool_to_str(state.pool_A)}")
    left_panel_lines.append("")
    left_panel_lines.append("Unités Joueur A :")
    for idx, u in enumerate(UNITS['A']):
        lab = unit_label('A', idx)
        left_panel_lines.append(
            f"[{idx}] {lab} {u.name} ({'Champ' if getattr(u,'is_champion',False) else 'Lv'+str(getattr(u,'level',getattr(u,'lvl','?')))}) [HP={u.hp}, ATK={u.atk}, DEF={u.defense}+{u.temp_def}]"
        )
        left_panel_lines.append(
            f"    -> pos (r={u.row}, c={u.col})  moved={u.has_moved} atk={u.has_attacked}"
        )

    # --- Panneau droit : Joueur B (IA) ---
    right_panel_lines = []
    right_panel_lines.append("")
    right_panel_lines.append("")
    hqB_def_eff = state.get_hq_effective_def('B')
    right_panel_lines.append(f"=== Joueur B (Faction: {state.hero_B['faction']}) ===")
    right_panel_lines.append(
        f"QG : HP {state.hq_B_hp:2d}/{state.hq_B_hp_max:2d}   DEF : {hqB_def_eff:2d}"
    )
    right_panel_lines.append(
        f"Champion : {state.hero_B['name']} "
        f"(HP={state.hero_B['hp']}, ATK={state.hero_B['atk']}, DEF={state.hero_B['def']})"
    )
    right_panel_lines.append(f"Pool: {pool_to_str(state.pool_B)}")
    right_panel_lines.append("")
    right_panel_lines.append("Unités IA B :")
    for idx, u in enumerate(UNITS['B']):
        lab = unit_label('B', idx)
        right_panel_lines.append(
            f"[{idx}] {lab} {u.name} ({'Champ' if getattr(u,'is_champion',False) else 'Lv'+str(getattr(u,'level',getattr(u,'lvl','?')))}) [HP={u.hp}, ATK={u.atk}, DEF={u.defense}+{u.temp_def}]"
        )
        right_panel_lines.append(
            f"    -> pos (r={u.row}, c={u.col})"
        )

    # -------------------------------------------------
    #  Affichage 3 colonnes : Joueur A / Plateau / Joueur B
    # -------------------------------------------------

    left_width = 59   # largeur panneau Joueur A
    board_width = 19  # largeur zone plateau (0123456789ABC + lignes 0..18)
    right_width = 59  # largeur panneau Joueur B

    offset = 3  # 0 = aligné ; 1 ou 2 = plateau plus bas
    board_lines_aligned = [""] * offset + board_lines

    max_len = max(
        len(left_panel_lines),
        len(board_lines_aligned),
        len(right_panel_lines)
    )

    def _clip_line(s, w):
        s = "" if s is None else str(s)
        if len(s) > w:
            return s[:w]  # keep columns stable
        return s.ljust(w)

    print("\n")
    for i in range(max_len):
        l = left_panel_lines[i] if i < len(left_panel_lines) else ""
        b = board_lines_aligned[i] if i < len(board_lines_aligned) else ""
        r = right_panel_lines[i] if i < len(right_panel_lines) else ""
        l = _clip_line(l, left_width)
        b = _clip_line(b, board_width)
        r = _clip_line(r, right_width)
        print(f"{l}  {b}  {r}")
    print()


def print_board_with_focus(state: GameState, focus_unit: Unit):
    temp = build_board_with_units(state, focus_unit=focus_unit)
    lines = lines_with_coords(temp)
    for line in lines:
        print(line)
    print()


def print_board_simple(board):
    for row in board:
        print(''.join(row))
    print()


def print_board_with_anchors(board, anchors):
    temp = [row[:] for row in board]
    for idx, (r, c) in enumerate(anchors):
        temp[r][c] = str(idx % 10)
    print("Plateau (ancres = chiffres) :")
    for r in range(HEIGHT):
        print(''.join(temp[r]))
    print()


def print_board_with_ghost(board, ghost_cells, ghost_char='#'):
    temp = [row[:] for row in board]
    for r, c in ghost_cells:
        if 0 <= r < HEIGHT and 0 <= c < WIDTH:
            if temp[r][c] == EMPTY:
                temp[r][c] = ghost_char
    for r in range(HEIGHT):
        print(''.join(temp[r]))
    print()


# ----------------------------------------------------------------------
#  SHAPES (6 cases) + NORMALISATION
# ----------------------------------------------------------------------

SHAPES_BY_LEVEL = {
    1: [
        # 1) croix classique — net de cube compact
        [(0, 1),
         (1, 0), (1, 1), (1, 2),
         (2, 1),
         (3, 1)],

        # 2) T droit
        [(0, 1),
         (1, 0), (1, 1), (1, 2),
         (2, 1), (2, 2)],

        # 3) T gauche
        [(0, 1),
         (1, 0), (1, 1), (1, 2),
         (2, 0), (2, 1)],
    ],
    2: [
        # 1) L colonne
        [(0, 0),
         (1, 0),
         (2, 0),
         (3, 0), (3, 1), (2, 1)],

        # 2) L colonne inversée
        [(0, 1),
         (1, 1),
         (2, 0), (2, 1),
         (3, 0),
         (4, 0)],

        # 3) U ouvert
        [(0, 0), (0, 2),
         (1, 0), (1, 1), (1, 2),
         (2, 1)],
    ],
    3: [
        # 1) S étendu
        [(0, 0), (0, 1),
         (1, 1), (1, 2),
         (2, 2), (2, 3)],

        # 2) Z étendu
        [(0, 1), (0, 2),
         (1, 0), (1, 1),
         (2, 0),
         (3, 0)],
    ],
    4: [
        # 1) pont 2×2
        [(0, 0), (0, 1),
         (1, 1), (1, 2),
         (2, 1), (2, 2)],

        # 2) marche
        [(0, 0),
         (1, 0), (1, 1),
         (2, 1), (2, 2),
         (3, 2)],

        # 3) barre + angle
        [(0, 0),
         (1, 0), (1, 1),
         (2, 0), (2, 1),
         (3, 0)],
    ],
    5: [
        # 1) S long
        [(0, 0),
         (1, 0), (1, 1),
         (2, 1), (2, 2),
         (3, 2)],

        # 2) Z long
        [(0, 2),
         (1, 1), (1, 2),
         (2, 0), (2, 1),
         (3, 0)],
    ],
}


def normalize_shapes():
    """
    Normalise chaque shape autour d'une ANCRE :
      - rangée la plus haute (min_r)
      - parmi ces cases, on prend la colonne "centrale"
      - cette case devient (0,0), c'est l'ancre
    """
    global SHAPES_BY_LEVEL

    for lvl, shape_list in SHAPES_BY_LEVEL.items():
        new_list = []
        for cells in shape_list:
            if not cells:
                new_list.append(cells)
                continue

            rows = [r for (r, c) in cells]
            min_r = min(rows)

            top_cells = [(r, c) for (r, c) in cells if r == min_r]
            top_cells.sort(key=lambda rc: rc[1])
            anchor_r, anchor_c = top_cells[len(top_cells) // 2]

            recentered = [(r - anchor_r, c - anchor_c) for (r, c) in cells]
            new_list.append(recentered)

        SHAPES_BY_LEVEL[lvl] = new_list


normalize_shapes()


def rotate_pattern(cells, quarter_turns=0):
    pts = cells
    for _ in range(quarter_turns % 4):
        pts = [(c, -r) for (r, c) in pts]
    return pts


def translate_pattern(cells, base_r, base_c):
    return [(base_r + r, base_c + c) for (r, c) in cells]


def can_place_shape(board, cells, player_tiles):
    """Validate that a shape can be placed.

    Rules (MAJ9):
      - A shape may ONLY occupy empty cells ('.') or temporary anchor digits ('0'..'9').
      - It must not overlap any existing territory/units/HQ.
      - It must touch the player's territory (4-neighborhood) at least once.
    """
    # 1) strict occupancy check
    for r, c in cells:
        if not in_bounds(board, r, c):
            return False
        if board[r][c] in (P1_QG, P2_QG):
            return False
        if not _is_free_for_shape(board[r][c]):
            return False

    # 2) must connect to existing territory
    for r, c in cells:
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if in_bounds(board, nr, nc) and board[nr][nc] in player_tiles:
                return True

    return False


def place_shape(board, cells, tile_char):
    for r, c in cells:
        board[r][c] = tile_char
    return cells


def find_anchors(board, player_tiles):
    anchors = []
    for r in range(HEIGHT):
        for c in range(WIDTH):
            if board[r][c] in player_tiles:
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < HEIGHT and 0 <= nc < WIDTH:
                        if board[nr][nc] == EMPTY:
                            anchors.append((nr, nc))
    anchors = list(dict.fromkeys(anchors))
    return anchors


def preview_shape(shape):
    rows = [r for (r, c) in shape]
    cols = [c for (r, c) in shape]
    min_r, max_r = min(rows), max(rows)
    min_c, max_c = min(cols), max(cols)
    h = max_r - min_r + 1
    w = max_c - min_c + 1
    grid = [['.' for _ in range(w)] for _ in range(h)]
    for r, c in shape:
        grid[r - min_r][c - min_c] = '#'
    for line in grid:
        print(''.join(line))
    print()

# ----------------------------------------------------------------------
#  DÉS & POOL
# ----------------------------------------------------------------------

SYMBOLS = ('ATK','DEF','MOVE','CAP','STAR')

# --- MAJ9: pool cap (stacks) ---
POOL_CAP = {"ATK": 12, "DEF": 12, "MOVE": 12, "CAP": 12}

class Die:
    def __init__(self, name, level, faces):
        self.name = name
        self.level = level
        self.faces = faces

    def roll(self):
        return random.choice(self.faces)

def create_starter_dice():
    dice = []

    # L1 : dés blancs de base
    faces_L1 = ["MOVE", "MOVE", "DEF", "STAR", "ATK", "STAR"]
    for i in range(3):
        dice.append(Die(f"L1-Blanc-{i+1}", 1, faces_L1))

    # L2 : dés verts (stables et agressifs)
    # CAP accessible dès L2 : abilities viables en early game (choix design)
    faces_L2_stable = ["MOVE", "DEF", "CAP", "ATK", "ATK", "STAR"]   # DEF×2→1, +CAP
    faces_L2_agro   = ["MOVE", "ATK", "ATK", "CAP", "DEF", "STAR"]   # ATK×3→2, +CAP
    dice.append(Die("L2-Vert-Stable-1", 2, faces_L2_stable))
    dice.append(Die("L2-Vert-Stable-2", 2, faces_L2_stable))
    dice.append(Die("L2-Vert-Agro-1",   2, faces_L2_agro))

    # L3 : bleus (traps + premiers CAP)
    faces_L3 = ["MOVE", "ATK", "CAP", "CAP", "DEF", "STAR"]
    dice.append(Die("L3-Bleu-1", 3, faces_L3))
    dice.append(Die("L3-Bleu-2", 3, faces_L3))

    # L4 : rouges (agressifs + CAP plus fréquent)
    faces_L4 = ["ATK", "ATK", "MOVE", "CAP", "CAP", "STAR"]  # patch: ATK→MOVE pour mobilité late game
    dice.append(Die("L4-Rouge-1", 4, faces_L4))
    dice.append(Die("L4-Rouge-2", 4, faces_L4))

    # L5 : noir (élite)
    faces_L5 = ["ATK", "MOVE", "CAP", "DEF", "STAR", "STAR"]  # patch: ATK→MOVE + DEF→STAR pour mobilité + accès L5
    dice.append(Die("L5-Noir-1", 5, faces_L5))

    return dice

def describe_die(d: Die) -> str:
    """
    Retourne un petit résumé des faces du dé, ex : 'ATKx3, DEFx2, STARx1'.
    """
    counts: dict[str, int] = {}
    for f in d.faces:
        counts[f] = counts.get(f, 0) + 1
    parts = []
    for sym in SYMBOLS:
        if counts.get(sym, 0):
            parts.append(f"{sym}x{counts[sym]}")
    return ", ".join(parts)


def print_units_for_build(faction_info: dict, label: str) -> None:
    """Affiche un aperçu des unités disponibles par niveau pour une faction (core only)."""
    base_units = faction_info.get("units_by_level") or {}

    if not base_units:
        print(f"\nAucune unité définie pour {label}.")
        return

    print(f"\nAperçu des unités de {label} par niveau :")
    for lvl in sorted(base_units.keys()):
        print(f"  Niveau {lvl} :")
        for m in base_units.get(lvl, []):
            stats = m.get("stats", {})
            atk = stats.get("ATK", "?")
            df = stats.get("DEF", "?")
            hp = stats.get("HP", "?")
            print(f"    - {m.get('nom', '?')} ATK={atk}, DEF={df}, HP={hp}")

    print()



def build_standard_dice_bag(catalog: list[Die], bag_size: int) -> list[Die]:
    """
    Sac standard :
      - si bag_size <= len(catalog) : on prend les premiers dés,
      - sinon : on duplique dans l'ordre jusqu'à atteindre la taille.
    """
    if bag_size <= len(catalog):
        return list(catalog[:bag_size])

    bag: list[Die] = []
    while len(bag) < bag_size:
        for d in catalog:
            bag.append(d)
            if len(bag) >= bag_size:
                break
    return bag


def build_custom_dice_bag(
    catalog: list[Die],
    bag_size: int,
    label: str,
    faction_info: dict | None = None,
) -> list[Die]:
    """
    Permet au joueur de choisir quels dés utiliser pour constituer son sac.
    On peut en plus afficher les unités disponibles pour aider le choix.
    """
    print(f"\nConstruction du sac pour {label} ({bag_size} dés).")

    if faction_info is not None:
        print_units_for_build(faction_info, label)

    print("Dés disponibles :")
    for idx, d in enumerate(catalog):
        print(f"  [{idx}] {d.name} (Lv{d.level}) : {describe_die(d)}")

    print("\nEntrez les indices séparés par des espaces (Enter = sac standard).")
    raw = input("Choix : ").strip()
    if not raw:
        print("  -> Sac standard utilisé.")
        return build_standard_dice_bag(catalog, bag_size)

    indices: list[int] = []
    for tok in raw.split():
        if tok.isdigit():
            i = int(tok)
            if 0 <= i < len(catalog):
                indices.append(i)

    if not indices:
        print("  -> Entrée invalide, sac standard utilisé.")
        return build_standard_dice_bag(catalog, bag_size)

    bag: list[Die] = []
    i = 0
    while len(bag) < bag_size:
        bag.append(catalog[indices[i % len(indices)]])
        i += 1

    print(f"  -> Sac de {label} : {[d.name for d in bag]}")
    return bag


def build_random_dice_bag(catalog: list[Die], bag_size: int, label: str) -> list[Die]:
    """
    Génère un sac aléatoire pour l'IA à partir du même catalogue.
    """
    bag = [random.choice(catalog) for _ in range(bag_size)]
    print(f"  -> Sac généré pour {label} : {[d.name for d in bag]}")
    return bag


_EXTENDED_BASE = {1: 6, 2: 6, 3: 5, 4: 3, 5: 2}  # composition 22 dés de référence
_EXTENDED_TOTAL = 22


def extended_level_counts(bag_size: int) -> dict[int, int]:
    """
    Retourne la composition par niveau pour un sac étendu de taille bag_size.
    Proportionnel à la base 22, arrondi par la méthode du plus grand reste.
    """
    raw = {lv: n * bag_size / _EXTENDED_TOTAL for lv, n in _EXTENDED_BASE.items()}
    floored = {lv: int(v) for lv, v in raw.items()}
    remainder = bag_size - sum(floored.values())
    # Distribuer le reste aux niveaux avec la plus grande partie décimale
    by_frac = sorted(raw.keys(), key=lambda lv: -(raw[lv] - floored[lv]))
    for lv in by_frac[:remainder]:
        floored[lv] += 1
    return floored


def build_extended_dice_bag(catalog: list[Die], bag_size: int = 22) -> list[Die]:
    """
    Sac étendu : composition proportionnelle à 6L1+6L2+5L3+3L4+2L5, scalée à bag_size.
    """
    counts = extended_level_counts(bag_size)
    bag: list[Die] = []
    for level, n in sorted(counts.items()):
        pool = [d for d in catalog if d.level == level]
        if not pool:
            pool = catalog
        for i in range(n):
            bag.append(pool[i % len(pool)])
    return bag


def build_from_indices_bag(catalog: list[Die], indices: list[int]) -> list[Die]:
    """Construit un sac à partir d'une liste d'indices dans le catalogue."""
    return [catalog[i] for i in indices if 0 <= i < len(catalog)]


def init_pool():
    return {'ATK': 0, 'MOVE': 0, 'DEF': 0, 'CAP': 0}

def add_to_pool(pool: dict, symbol: str, amount: int = 1) -> int:
    """Ajoute jusqu'au cap. Retourne le gain réel (0..amount)."""
    # compat: anciennes faces/clefs CAP -> TRAP
    if symbol == 'CAP':
        symbol = 'CAP'
    if not isinstance(pool, dict):
        return 0
    if symbol not in pool:
        # allow symbol creation only if cap known
        if symbol not in POOL_CAP:
            return 0
        pool[symbol] = 0

    cap = int(POOL_CAP.get(symbol, 0) or 0)
    if cap <= 0:
        return 0

    before = int(pool.get(symbol, 0) or 0)
    after = min(cap, before + int(amount))
    pool[symbol] = after
    return after - before

def spend_from_pool(pool, symbol, amount=1):
    # compat: anciennes faces/clefs CAP -> TRAP
    if symbol == 'CAP':
        symbol = 'CAP'
    if pool.get(symbol, 0) < amount:
        return False
    pool[symbol] -= amount
    return True

# ----------------------------------------------------------------------
