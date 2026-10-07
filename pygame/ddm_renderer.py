# =============================================================================
# DDM — Renderer principal
#
# Layout complet : HUD dés/logs + liste unités + barre bas 9 zones
#                  Mini map interactive + invocation + QG pixel art
#
# Usage :
#   Spectateur (autorun) : python ddm_renderer.py
#   Joueur humain GUI    : lancer en parallèle de :
#                          python -m engine.ddm_p4_loop --mode gui --faction-a X --faction-b Y
# =============================================================================

# On importe tout depuis phase2e et on étend
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import pygame, json, time, unicodedata, re, pathlib, random, subprocess

# =============================================================================
# CHEMINS
# =============================================================================
_DDM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPRITES_ROOT   = os.path.join(_DDM_ROOT, "assets", "sprites")
MISSING_PNG    = os.path.join(SPRITES_ROOT, "_ui", "missing.png")
QG_ROOT        = os.path.join(_DDM_ROOT, "assets", "sprites", "QG")
SNAPSHOT_PATH  = pathlib.Path(os.path.join(_DDM_ROOT, "engine", "snapshots", "latest.json"))
COMMAND_PATH   = pathlib.Path(os.path.join(_DDM_ROOT, "engine", "snapshots", "_command"))
FONT_PATH      = os.path.join(_DDM_ROOT, "assets", "PressStart2P-Regular.ttf")
_QUIT_PATH     = SNAPSHOT_PATH.parent / "renderer_quit.json"
_PAUSE_PATH    = SNAPSHOT_PATH.parent / "pause.json"


def _write_quit_signal():
    try:
        import json as _j
        _QUIT_PATH.write_text(_j.dumps({"quit": True}), encoding="utf-8")
    except Exception:
        pass


def _set_pause_signal(active: bool):
    """Crée/supprime pause.json pour synchroniser avec le moteur."""
    try:
        if active:
            _PAUSE_PATH.write_text("{}", encoding="utf-8")
        elif _PAUSE_PATH.exists():
            _PAUSE_PATH.unlink()
    except Exception as e:
        print(f"[RENDERER] Erreur signal pause : {e}")


def _draw_pause_menu(screen, fonts, items, sel, msg=""):
    """Overlay menu pause en cours de partie. ESC pour fermer."""
    f_title, f_menu, f_small, f_tiny = fonts
    sw, sh = screen.get_size()
    # Overlay sombre transparent
    veil = pygame.Surface((sw, sh), pygame.SRCALPHA)
    veil.fill((0, 0, 0, 180))
    screen.blit(veil, (0, 0))
    # Boîte centrale
    bw, bh = 560, 60 + 60 * len(items) + 80
    bx = (sw - bw) // 2
    by = (sh - bh) // 2
    pygame.draw.rect(screen, (24, 20, 36), (bx, by, bw, bh))
    pygame.draw.rect(screen, (200, 160, 50), (bx, by, bw, bh), 2)
    pygame.draw.rect(screen, (200, 160, 50), (bx + 5, by + 5, bw - 10, bh - 10), 1)
    # Titre
    title = f_menu.render("MENU PAUSE", True, (220, 200, 100))
    screen.blit(title, (bx + (bw - title.get_width()) // 2, by + 16))
    # Items
    for i, (key, label) in enumerate(items):
        ey = by + 70 + i * 60
        is_sel = (i == sel)
        if is_sel:
            hl = pygame.Surface((bw - 40, 50), pygame.SRCALPHA)
            hl.fill((200, 160, 50, 50))
            screen.blit(hl, (bx + 20, ey))
            screen.blit(f_menu.render(label, True, (255, 220, 100)), (bx + 50, ey + 12))
        else:
            color = (140, 130, 150) if "venir" not in label else (90, 85, 100)
            screen.blit(f_menu.render(label, True, color), (bx + 50, ey + 12))
    # Message d'erreur / placeholder
    if msg:
        m = f_tiny.render(msg, True, (220, 120, 120))
        screen.blit(m, (bx + (bw - m.get_width()) // 2, by + bh - 50))
    # Hint
    hint = f_tiny.render("HAUT/BAS naviguer    ENTREE selectionner    ESC fermer", True, (140, 130, 158))
    screen.blit(hint, (bx + (bw - hint.get_width()) // 2, by + bh - 28))


# =============================================================================
# LAYOUT (identique Phase 2-E)
# =============================================================================
SCREEN_W, SCREEN_H = 1920, 1080
FPS = 60

def pct(p): return int(SCREEN_W * p / 100)

HUD_W     = pct(15)
LOG_H     = 190
DIE_LOG_H = 180
BOARD_W   = SCREEN_W - HUD_W * 2
BOARD_H   = SCREEN_H - LOG_H
LOG_Y     = SCREEN_H - LOG_H
UNIT_Y    = DIE_LOG_H
DIE_W     = HUD_W // 2
LOGD_W    = HUD_W - DIE_W

_LOG = pct(15); _GAP = pct(2.5); _JOU = pct(15)
_CHP = pct(7.5); _MAP = pct(20)

_LA=0; _JA=_LOG+_GAP; _CA=_JA+_JOU
_MM=_CA+_CHP; _CB=_MM+_MAP; _JB=_CB+_CHP; _LB=_JB+_JOU+_GAP

BOT_LOG_W=_LOG; BOT_JOU_W=_JOU; BOT_CHP_W=_CHP; BOT_MAP_W=_MAP

GRID_COLS=13; GRID_ROWS=19
MINI_CELL=13
MINI_W=GRID_ROWS*MINI_CELL; MINI_H=GRID_COLS*MINI_CELL

# =============================================================================
# SHAPES (depuis ddm_p2_board_dice)
# =============================================================================
SHAPES_BY_LEVEL = {
    1: [
        # 1) croix classique
        [(0,1),(1,0),(1,1),(1,2),(2,1),(3,1)],
        # 2) T droit
        [(0,1),(1,0),(1,1),(1,2),(2,1),(2,2)],
        # 3) T gauche
        [(0,1),(1,0),(1,1),(1,2),(2,0),(2,1)],
    ],
    2: [
        # 1) L colonne
        [(0,0),(1,0),(2,0),(3,0),(3,1),(2,1)],
        # 2) L colonne inversée
        [(0,1),(1,1),(2,0),(2,1),(3,0),(4,0)],
        # 3) U ouvert
        [(0,0),(0,2),(1,0),(1,1),(1,2),(2,1)],
    ],
    3: [
        # 1) S étendu
        [(0,0),(0,1),(1,1),(1,2),(2,2),(2,3)],
        # 2) Z étendu
        [(0,1),(0,2),(1,0),(1,1),(2,0),(3,0)],
    ],
    4: [
        # 1) pont 2×2
        [(0,0),(0,1),(1,1),(1,2),(2,1),(2,2)],
        # 2) marche
        [(0,0),(1,0),(1,1),(2,1),(2,2),(3,2)],
        # 3) barre + angle
        [(0,0),(1,0),(1,1),(2,0),(3,0),(4,0)],
    ],
    5: [
        # 1) S long
        [(0,0),(1,0),(1,1),(2,1),(2,2),(3,2)],
        # 2) Z long
        [(0,2),(1,1),(1,2),(2,0),(2,1),(3,0)],
    ],
}

# Normalisation identique à ddm_p2_board_dice.normalize_shapes()
def _normalize_shapes():
    for lvl, shape_list in SHAPES_BY_LEVEL.items():
        new_list = []
        for cells in shape_list:
            if not cells:
                new_list.append(cells); continue
            rows = [r for (r, c) in cells]
            min_r = min(rows)
            top_cells = sorted([(r, c) for (r, c) in cells if r == min_r], key=lambda rc: rc[1])
            anchor_r, anchor_c = top_cells[len(top_cells) // 2]
            new_list.append([(r - anchor_r, c - anchor_c) for (r, c) in cells])
        SHAPES_BY_LEVEL[lvl] = new_list

_normalize_shapes()

# =============================================================================
# PALETTE
# =============================================================================
C_BG=(10,8,16); C_HUD_BG=(14,11,22); C_HUD_TOP=(18,15,26)
C_ROW_A=(20,17,28); C_ROW_B=(24,20,32); C_LOG_BG=(12,10,18)
C_JOU_BG=(16,13,26); C_JOU_A_ACC=(20,36,85); C_JOU_B_ACC=(88,18,18)
C_CHP_BG=(12,10,20); C_BOT_BG=(8,6,12); C_BOARD_BG=(22,20,24)
C_BORDER=(20,18,22); C_BLIGHT=(28,26,30)
C_NEUTRAL=(34,31,36); C_NEUTRAL_B=(29,26,31)
C_P1_TILE=(25,45,92); C_P1_TILE_B=(28,50,104)
C_P2_TILE=(92,24,24); C_P2_TILE_B=(104,28,28)
C_P1_QG=(38,68,155); C_P2_QG=(155,38,38)
C_ACCENT=(200,160,50); C_TEXT=(220,215,230); C_DIM=(100,94,112)
C_P1_OUT=(78,138,252); C_P2_OUT=(252,78,78)
C_HP_OK=(78,198,78); C_HP_MID=(218,178,38); C_HP_LOW=(218,58,58)
C_MOVED=(38,98,38); C_ATK_DONE=(98,38,38)

# Couleurs mode invocation
C_ANCHOR_VALID  = (200,200,50,160)   # cases d'ancrage valides
C_ANCHOR_HOV    = (255,255,100,200)  # ancrage survolé
C_ANCHOR_SEL    = (255,220,0,255)    # ancrage sélectionné
C_SHAPE_PREVIEW = (100,200,100,140)  # preview shape
C_SHAPE_INVALID = (200,50,50,120)    # shape invalide

DIE_COLORS={1:(210,210,222),2:(78,178,78),3:(58,118,208),4:(198,48,48),5:(28,22,42)}
DIE_SYM_COL={1:(28,24,38),2:(18,48,18),3:(14,30,60),4:(58,12,12),5:(180,140,255)}
FACE_SYM={"MOVE":"↑","ATK":"⚔","DEF":"⛨","CAP":"✦","STAR":"★"}
FACE_COL={"MOVE":(100,180,255),"ATK":(255,100,100),"DEF":(100,220,100),
          "CAP":(220,180,50),"STAR":(255,220,80)}

EMPTY='.'; P1_QG='A'; P2_QG='B'; P1_TILE='a'; P2_TILE='b'

# =============================================================================
# MACHINE D'ÉTAT — Invocation
# =============================================================================
class InvocState:
    NORMAL         = "normal"
    ANCHOR_SELECT  = "anchor_select"
    SHAPE_SELECT   = "shape_select"
    CONFIRM        = "confirm"

    def __init__(self):
        self.mode            = self.NORMAL
        self.niveau          = None
        self.anchors         = []
        self.selected_anchor = None
        self.shapes          = []
        self.shape_idx       = 0
        self.rotation        = 0
        self.hovered_anchor  = None
        self.test_niveau     = 3    # override pour les tests [ et ]

    def reset(self):
        tn = self.test_niveau   # préserve le niveau de test
        self.__init__()
        self.test_niveau = tn

    def start_invoc(self, niveau, snap):
        """Démarre le mode invocation depuis un lancer avec étoiles."""
        self.mode   = self.ANCHOR_SELECT
        self.niveau = niveau
        self.shapes = SHAPES_BY_LEVEL.get(niveau, [])
        self.anchors = find_valid_anchors(snap, "A")  # joueur A = humain

    def select_anchor(self, col, row):
        self.selected_anchor = (col, row)
        self.mode = self.SHAPE_SELECT
        self.shape_idx = 0
        self.rotation  = 0

    def cancel(self):
        self.reset()


def _purge_stale_command():
    try:
        if COMMAND_PATH.exists():
            COMMAND_PATH.unlink()
    except Exception:
        pass

# =============================================================================
# MACHINE D'ÉTAT — Phase Mobs (MOVE / ATK / CAP)
# =============================================================================
class MobsState:
    NORMAL     = "normal"
    SELECTED   = "selected"    # unité sélectionnée, en attente d'action
    CAP_TARGET = "cap_target"  # ciblage manuel d'une capacité (brume…)
    WAITING    = "waiting"     # commande envoyée, attend snapshot moteur

    def __init__(self):
        self.mode         = self.NORMAL
        self.selected_idx = None
        self.move_cells   = set()
        self.atk_targets  = []
        self.qg_atk_cell  = None   # (col,row) du QG B si attaquable
        self.cap_range    = 0       # portée de la capacité ciblée
        self.cap_hov      = None    # cellule survolée en mode CAP_TARGET
        self._wait_fp     = None
        self._wait_t      = 0.0
        self._cmd_consumed = False   # command.json supprimé par moteur

    def reset(self):
        self.__init__()

    def select(self, idx, snap):
        u = _get_unit_A(snap, idx)
        if not u: return
        # Ne sélectionne que si l'unité a encore des actions disponibles
        pool = get_player(snap, "A").get("pool", {})
        can_move = pool.get("MOVE", 0) > 0 and not u.get("moved", False)
        can_atk  = pool.get("ATK", 0) > 0 and not u.get("attacked", False)
        can_cap  = pool.get("CAP", 0) > 0
        if not (can_move or can_atk or can_cap): return
        self.selected_idx = idx
        self.mode = self.SELECTED
        self.move_cells  = _compute_move_cells(idx, snap) if can_move else set()
        self.atk_targets = _compute_atk_targets(idx, snap) if can_atk else []
        self.qg_atk_cell = _can_atk_qg(idx, snap) if can_atk else None

    def send_and_wait(self, snap):
        """Après envoi d'une commande, passe en WAITING."""
        self._wait_fp = snap_fingerprint(snap)
        self._wait_t  = time.time()
        self._cmd_consumed = False
        self.mode = self.WAITING

    def on_snapshot_update(self, snap):
        """Sort du WAITING quand le moteur a traité la commande."""
        global _snap_time
        if self.mode != self.WAITING:
            return
        elapsed = time.time() - self._wait_t
        # Signal primaire : command.json supprimé = moteur a lu la commande
        if not self._cmd_consumed and not COMMAND_PATH.exists():
            self._cmd_consumed = True
        # Une fois la commande consommée, on attend que le snapshot se mette à jour
        if self._cmd_consumed and elapsed > 0.8:
            _snap_time = 0   # force relecture immédiate du snapshot
            self.reset()
            return
        # Signal secondaire : fingerprint changé (état modifié par le moteur)
        fp = snap_fingerprint(snap)
        if fp != self._wait_fp:
            _snap_time = 0
            _purge_stale_command()
            self.reset()
            return
        # Timeout sécurité : 6 secondes max
        if elapsed > 6.0:
            print("[GUI] WAITING timeout — force reset")
            _snap_time = 0
            _purge_stale_command()
            self.reset()

    def deselect(self):
        self.reset()


def _get_unit_A(snap, idx):
    units = get_player(snap, "A").get("unites", []) if snap else []
    return units[idx] if 0 <= idx < len(units) else None


def _compute_move_cells(idx, snap):
    """Cases accessibles en MOVE — territoire A + territoire B (invasion)."""
    u = _get_unit_A(snap, idx)
    if not u: return set()
    if u.get("moved", False): return set()
    pool = get_player(snap, "A").get("pool", {})
    move_pts = pool.get("MOVE", 0)
    if move_pts <= 0: return set()
    grid = sg(snap, "grille") or []
    ur, uc = u["row"], u["col"]
    # Walkable : territoire A + territoire B (cases non occupées par ennemi)
    walkable = {P1_TILE, P2_TILE}  # QG non traversables — attaque QG via action dédiée
    units_a = {(v["row"], v["col"]) for v in get_player(snap,"A").get("unites",[])}
    units_b = {(v["row"], v["col"]) for v in get_player(snap,"B").get("unites",[])}
    from collections import deque
    visited = {(ur, uc): 0}
    cells = set()
    q = deque([(ur, uc, 0)])
    while q:
        r, c, dist = q.popleft()
        if dist >= move_pts: continue
        for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
            nr, nc = r+dr, c+dc
            if not (0 <= nr < GRID_ROWS and 0 <= nc < GRID_COLS): continue
            ch = grid[nr][nc] if nr < len(grid) and nc < len(grid[nr]) else '.'
            if ch not in walkable: continue
            if (nr, nc) in units_a: continue   # bloqué par allié
            if (nr, nc) in units_b: continue   # bloqué par ennemi
            if (nr, nc) not in visited or visited[(nr,nc)] > dist+1:
                visited[(nr, nc)] = dist+1
                cells.add((nc, nr))  # (col, row)
                q.append((nr, nc, dist+1))
    return cells


def _compute_atk_targets(idx, snap):
    """Indices des unités B adjacentes attaquables."""
    u = _get_unit_A(snap, idx)
    if not u: return []
    if u.get("attacked", False): return []
    pool = get_player(snap, "A").get("pool", {})
    if pool.get("ATK", 0) <= 0: return []
    ur, uc = u["row"], u["col"]
    enemies = get_player(snap, "B").get("unites", [])
    return [i for i, e in enumerate(enemies)
            if abs(e["row"]-ur) + abs(e["col"]-uc) == 1]


def _can_atk_qg(idx, snap):
    """Retourne (col, row) du QG B si l'unité A[idx] est adjacente, sinon None."""
    u = _get_unit_A(snap, idx)
    if not u: return None
    if u.get("attacked", False): return None
    pool = get_player(snap, "A").get("pool", {})
    if pool.get("ATK", 0) <= 0: return None
    ur, uc = u["row"], u["col"]
    # QG B position depuis le snapshot
    qg_b = get_player(snap, "B").get("qg", {})
    pos = qg_b.get("pos")
    if not pos: return None
    qg_r, qg_c = pos[0], pos[1]
    if abs(ur - qg_r) + abs(uc - qg_c) == 1:
        return (qg_c, qg_r)   # (col, row) pour cohérence
    return None


def write_attack_qg_command(attacker):
    """Écrit une commande d'attaque sur le QG ennemi."""
    cmd = {"action":"attack","player":"A",
           "unit_letter":   attacker.get("lettre",""),
           "unit_name":     attacker.get("nom",""),
           "target_letter": "",
           "target_name":   "",    # vide = engine fallback vers QG
           "timestamp":     int(time.time())}
    try:
        with open(COMMAND_PATH,"w",encoding="utf-8") as f:
            json.dump(cmd,f)
        print(f"[CMD] attack QG écrit : {attacker.get('nom','')} → QG B")
    except Exception as e:
        print(f"[CMD] Erreur écriture attack QG : {e}")


def write_move_command(unit, to_col, to_row):
    cmd = {"action":"move","player":"A",
           "unit_letter": unit.get("lettre",""),
           "unit_name":   unit.get("nom",""),
           "from":        [unit["col"], unit["row"]],
           "to":          [to_col, to_row],
           "timestamp":   int(time.time())}
    try:
        with open(COMMAND_PATH,"w",encoding="utf-8") as f:
            json.dump(cmd,f)
        print(f"[CMD] move écrit : {unit.get('nom','')} → ({to_col},{to_row})")
    except Exception as e:
        print(f"[CMD] Erreur écriture move : {e}")


def write_attack_command(attacker, target):
    cmd = {"action":"attack","player":"A",
           "unit_letter":   attacker.get("lettre",""),
           "unit_name":     attacker.get("nom",""),
           "target_letter": target.get("lettre",""),
           "target_name":   target.get("nom",""),
           "timestamp":     int(time.time())}
    try:
        with open(COMMAND_PATH,"w",encoding="utf-8") as f:
            json.dump(cmd,f)
        print(f"[CMD] attack écrit : {attacker.get('nom','')} → {target.get('nom','')}")
    except Exception as e:
        print(f"[CMD] Erreur écriture attack : {e}")


def write_cap_command(unit, target_row=None, target_col=None):
    cmd = {"action":"cap","player":"A",
           "unit_letter": unit.get("lettre",""),
           "unit_name":   unit.get("nom",""),
           "timestamp":   int(time.time())}
    if target_row is not None and target_col is not None:
        cmd["target_row"] = target_row
        cmd["target_col"] = target_col
    try:
        with open(COMMAND_PATH,"w",encoding="utf-8") as f:
            json.dump(cmd,f)
        print(f"[CMD] cap écrit : {unit.get('nom','')} → ({target_col},{target_row})")
    except Exception as e:
        print(f"[CMD] Erreur écriture cap : {e}")


def write_end_phase_command():
    cmd = {"action":"end_phase","player":"A","timestamp":int(time.time())}
    try:
        with open(COMMAND_PATH,"w",encoding="utf-8") as f:
            json.dump(cmd,f)
        print("[CMD] end_phase écrit")
    except Exception as e:
        print(f"[CMD] Erreur end_phase : {e}")


# =============================================================================
# HELPERS INVOCATION
# =============================================================================

def find_valid_anchors(snap, side):
    """
    Cases vides adjacentes au territoire du joueur — identique à find_anchors() du moteur.
    """
    grid  = sg(snap, "grille") or []
    tile  = P1_TILE if side == "A" else P2_TILE
    qg    = P1_QG   if side == "A" else P2_QG
    seen  = set()
    anchors = []
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            ch = grid[row][col] if row < len(grid) and col < len(grid[row]) else '.'
            if ch in (tile, qg):
                for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                    nr, nc = row+dr, col+dc
                    if 0 <= nr < GRID_ROWS and 0 <= nc < GRID_COLS:
                        nch = grid[nr][nc] if nr < len(grid) and nc < len(grid[nr]) else '.'
                        if nch == EMPTY and (nc, nr) not in seen:
                            seen.add((nc, nr))
                            anchors.append((nc, nr))
    return anchors


def rotate_shape(shape, rot):
    """Rotation sans normalisation — offsets négatifs autorisés."""
    pts = [(r, c) for r, c in shape]
    for _ in range(rot):
        pts = [(c, -r) for r, c in pts]
    return pts


def get_shape_cells(anchor_col, anchor_row, shape, rot):
    """
    Place (0,0) à (anchor_col, anchor_row) — cohérent avec le moteur.
    Retourne (anchor_cell, deploy_cells).
    """
    pts = rotate_shape(shape, rot)
    # (0,0) est toujours présent après normalize_shapes ; rotation (0,0)→(0,0)
    rest = [(anchor_col + c, anchor_row + r) for r, c in pts if (r, c) != (0, 0)]
    return (anchor_col, anchor_row), rest


def get_all_shape_cells(anchor_col, anchor_row, shape, rot):
    """Toutes les cases (ancrage + déploiement) en liste plate."""
    anc, dep = get_shape_cells(anchor_col, anchor_row, shape, rot)
    return [anc] + dep


def is_shape_valid(anchor_col, anchor_row, shape, rot, snap, side):
    """
    Validation :
    - ancrage : vide + adjacent au territoire
    - déploiement : vides uniquement, dans les limites
    """
    grid = sg(snap, "grille") or []
    tile = P1_TILE if side == "A" else P2_TILE
    qg   = P1_QG   if side == "A" else P2_QG

    def gch(col, row):
        if not (0 <= row < GRID_ROWS and 0 <= col < GRID_COLS): return None
        return grid[row][col] if row < len(grid) and col < len(grid[row]) else '.'

    anc_col, anc_row = anchor_col, anchor_row
    _, deploy = get_shape_cells(anchor_col, anchor_row, shape, rot)

    # Ancrage : vide
    if gch(anc_col, anc_row) != EMPTY:
        return False
    # Ancrage : adjacent au territoire
    if not any(gch(anc_col+dc, anc_row+dr) in (tile, qg)
               for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]):
        return False

    # Déploiement : vide et dans les limites
    for col2, row2 in deploy:
        if gch(col2, row2) != EMPTY:
            return False
    return True


def get_invoc_niveau(snap):
    """
    Lit le niveau d'invocation depuis le snapshot.
    En mode connecté, le moteur l'écrit dans 'invoc_niveau'.
    Fallback log : uniquement en mode déconnecté.
    """
    # Champ direct — écrit par le moteur avant d'attendre, effacé après
    n = sg(snap, "invoc_niveau")
    if n is not None:
        return int(n)
    # En mode connecté, le champ direct fait autorité — pas de fallback
    if os.environ.get("DDM_GUI_CONNECTED","0") == "1":
        return None
    # Fallback log — mode déconnecté uniquement
    log = sg(snap, "log") or []
    for line in reversed(log):
        if "[INVOC]" in line and "pas assez" not in line and "invoqué" not in line and "échec" not in line:
            m = re.search(r"Lv(\d)", line)
            if m: return int(m.group(1))
    return None


def write_command(invoc_state):
    """Écrit command.json pour le moteur."""
    if invoc_state.selected_anchor is None: return
    col, row = invoc_state.selected_anchor
    cmd = {
        "action":    "invoke",
        "player":    "A",
        "ancrage":   [col, row],
        "shape_idx": invoc_state.shape_idx,
        "rotation":  invoc_state.rotation,
        "niveau":    invoc_state.niveau,
        "timestamp": int(time.time()),
    }
    with open(COMMAND_PATH, "w", encoding="utf-8") as f:
        json.dump(cmd, f, indent=2)
    print(f"[CMD] command.json écrit : {cmd}")

# =============================================================================
# SNAPSHOT
# =============================================================================
_snap_cache=None; _snap_time=0.0

def load_snapshot(fast=False):
    global _snap_cache,_snap_time
    now=time.time()
    interval = 0.15 if fast else 0.5
    if now-_snap_time<interval: return _snap_cache
    _snap_time=now
    try:
        if SNAPSHOT_PATH.exists():
            with open(SNAPSHOT_PATH,"r",encoding="utf-8") as f:
                _snap_cache=json.load(f)
    except: pass
    return _snap_cache

def sg(snap,*keys,default=None):
    d=snap
    for k in keys:
        if not isinstance(d,dict): return default
        d=d.get(k,default)
    return d


def snap_fingerprint(snap):
    """Empreinte légère — change quand le moteur modifie l'état."""
    if not snap: return None
    pa = get_player(snap, "A")
    pb = get_player(snap, "B")
    pool = pa.get("pool", {})
    parts = [
        sg(snap, "tour"), sg(snap, "joueur_actif"),
        pool.get("MOVE", 0), pool.get("ATK", 0),
        pool.get("DEF", 0), pool.get("CAP", 0),
        pa.get("qg", {}).get("hp", 0),
        pb.get("qg", {}).get("hp", 0),
        sg(snap, "invoc_niveau"),
    ]
    for u in pa.get("unites", []):
        parts.extend([u.get("col"), u.get("row"), u.get("hp"),
                       u.get("moved"), u.get("attacked")])
    for u in pb.get("unites", []):
        parts.extend([u.get("col"), u.get("row"), u.get("hp")])
    return tuple(parts)

def get_player(snap,side):
    if not snap: return {}
    return (snap.get(f"joueur_{side.lower()}") or
            snap.get(f"joueur_{side.upper()}") or {})

# =============================================================================
# SPRITES (identique Phase 2-E)
# =============================================================================
_spr={}

def slugify(t):
    t=t.lower().strip()
    t=unicodedata.normalize("NFD",t)
    t="".join(c for c in t if unicodedata.category(c)!="Mn")
    return re.sub(r"[^a-z0-9]+","_",t).strip("_")

def fac_slug(s):
    if not s: return ""
    part=s.split("–")[0].split("-")[0].strip().lower()
    part=unicodedata.normalize("NFD",part)
    part="".join(c for c in part if unicodedata.category(c)!="Mn")
    return re.sub(r"[^a-z0-9]+","_",part).strip("_")

def _placeholder(tw,th):
    s=pygame.Surface((tw,th)); s.fill((40,20,40)); return s

def load_spr(faction,niveau,nom,lettre,tw,th):
    if not faction or not nom: return _placeholder(tw,th)
    slug=slugify(nom)
    fn=(f"{faction}_champion_{lettre.lower()}_{slug}.png"
        if lettre else f"{faction}_lv{niveau}_{slug}.png")
    key=f"{fn}_{tw}_{th}"
    if key in _spr: return _spr[key]
    path=os.path.join(SPRITES_ROOT,faction,fn)
    if not os.path.isfile(path): path=MISSING_PNG
    try:
        src=pygame.image.load(path).convert()
        sw,sh=src.get_size(); r=min((tw*.88)/sw,(th*.88)/sh)
        s=pygame.transform.scale(src,(max(1,int(sw*r)),max(1,int(sh*r))))
    except: s=_placeholder(tw,th)
    _spr[key]=s; return s

def find_champion_sprite(faction_str,nom):
    slug=slugify(nom); fac=fac_slug(faction_str)
    fac_dir=os.path.join(SPRITES_ROOT,fac)
    if not os.path.isdir(fac_dir): return MISSING_PNG
    for fname in os.listdir(fac_dir):
        if "champion" in fname and slug in fname:
            return os.path.join(fac_dir,fname)
    return MISSING_PNG

def load_champ_spr(faction_str,nom,tw,th):
    key=f"champ_{slugify(nom)}_{tw}_{th}"
    if key in _spr: return _spr[key]
    path=find_champion_sprite(faction_str,nom)
    try:
        src=pygame.image.load(path).convert()
        sw,sh=src.get_size(); r=min((tw*.88)/sw,(th*.88)/sh)
        s=pygame.transform.scale(src,(max(1,int(sw*r)),max(1,int(sh*r))))
    except: s=_placeholder(tw,th)
    _spr[key]=s; return s

def load_qg_spr(faction_str,tw,th):
    fac=fac_slug(faction_str)
    key=f"qg_{fac}_{tw}_{th}"
    if key in _spr: return _spr[key]
    path=os.path.join(QG_ROOT,f"QG_{fac}.png")
    if not os.path.isfile(path): _spr[key]=None; return None
    try:
        src=pygame.image.load(path).convert_alpha()
        s=pygame.transform.scale(src,(max(1,tw),max(1,th)))
    except: s=None
    _spr[key]=s; return s

# =============================================================================
# PERSPECTIVE C
# =============================================================================
BOARD_CX=HUD_W+BOARD_W//2; BOARD_CY=BOARD_H//2-10
GRID_H_PX=740; NEAR_W=int(BOARD_W*.88); VP_Y=-900

def compute_perspective():
    fy=BOARD_CY-GRID_H_PX//2; ny=BOARD_CY+GRID_H_PX//2
    dist=ny-VP_Y; rows=[]
    for r in range(GRID_ROWS):
        t=r/(GRID_ROWS-1)
        yt=fy+t*(ny-fy); step=(ny-fy)/(GRID_ROWS-1); yb=yt+step
        rt=(yt-VP_Y)/dist; rb=(yb-VP_Y)/dist
        wt,wb=NEAR_W*rt,NEAR_W*rb
        rows.append({"y_top":yt,"y_bot":yb,
                     "xlt":BOARD_CX-wt/2,"xrt":BOARD_CX+wt/2,
                     "xlb":BOARD_CX-wb/2,"xrb":BOARD_CX+wb/2,
                     "cw":(wt+wb)/2/GRID_COLS,"ch":yb-yt})
    return rows

def cpoly(rd,col,row):
    r=rd[row]; t0,t1=col/GRID_COLS,(col+1)/GRID_COLS
    def ix(r,t,s):
        return r["xlt"]+t*(r["xrt"]-r["xlt"]) if s=="top" else r["xlb"]+t*(r["xrb"]-r["xlb"])
    return [(int(ix(r,t0,"top")),int(r["y_top"])),(int(ix(r,t1,"top")),int(r["y_top"])),
            (int(ix(r,t1,"bot")),int(r["y_bot"])),(int(ix(r,t0,"bot")),int(r["y_bot"]))]

def ccc(rd,col,row):
    p=cpoly(rd,col,row)
    return int(sum(x for x,y in p)/4),int(sum(y for x,y in p)/4)

def pip(px,py,poly):
    n,inside,j=len(poly),False,len(poly)-1
    for i in range(n):
        xi,yi=poly[i]; xj,yj=poly[j]
        if ((yi>py)!=(yj>py)) and (px<(xj-xi)*(py-yi)/(yj-yi)+xi): inside=not inside
        j=i
    return inside

def get_hov(mpos,rd):
    mx,my=mpos
    if not(HUD_W<mx<HUD_W+BOARD_W): return None
    for row in range(GRID_ROWS-1,-1,-1):
        for col in range(GRID_COLS):
            if pip(mx,my,cpoly(rd,col,row)): return(col,row)
    return None

def hp_c(hp,hm):
    if hm<=0: return C_HP_LOW
    r=hp/hm; return C_HP_OK if r>.6 else(C_HP_MID if r>.3 else C_HP_LOW)

def cfill(ch,col,row):
    ck=(col+row)%2==0
    if ch in(P1_QG,P2_QG): return C_BOARD_BG
    if ch==P1_TILE: return C_P1_TILE if ck else C_P1_TILE_B
    if ch==P2_TILE: return C_P2_TILE if ck else C_P2_TILE_B
    return C_NEUTRAL if ck else C_NEUTRAL_B

# =============================================================================
# SYMBOLES DÉS PIXEL ART
# =============================================================================
import math

def sym_star(surf,cx,cy,s,col):
    pts=[]
    for i in range(5):
        ao=math.pi/2+i*2*math.pi/5; ai=ao+math.pi/5
        r_out=s//2; r_in=s//5
        pts.append((cx+int(r_out*math.cos(ao)),cy-int(r_out*math.sin(ao))))
        pts.append((cx+int(r_in*math.cos(ai)),cy-int(r_in*math.sin(ai))))
    pygame.draw.polygon(surf,col,pts)

def sym_atk(surf,cx,cy,s,col):
    t=max(2,s//8)
    pygame.draw.rect(surf,col,(cx-t,cy-s//2,t*2,s*3//4))
    pygame.draw.rect(surf,col,(cx-s//3,cy+s//8,s*2//3,t*2))
    pygame.draw.rect(surf,col,(cx-t,cy+s//4,t*2,s//4))
    pygame.draw.polygon(surf,col,[(cx-t,cy-s//2),(cx+t,cy-s//2),(cx,cy-s//2-s//6)])

def sym_def(surf,cx,cy,s,col):
    hw=s//2; hh=s*2//3
    pts=[(cx-hw,cy-hh+s//5),(cx+hw,cy-hh+s//5),(cx+hw,cy),(cx,cy+hh-s//5),(cx-hw,cy)]
    pygame.draw.polygon(surf,col,pts)

def sym_move(surf,cx,cy,s,col):
    hw=s//2; t=max(2,s//8)
    pygame.draw.rect(surf,col,(cx-t,cy,t*2,s//2))
    pygame.draw.polygon(surf,col,[(cx-hw,cy),(cx+hw,cy),(cx,cy-s//2)])

def sym_cap(surf,cx,cy,s,col):
    hw=s//2; t=max(2,s//8)
    for dx,dy in [(0,-1),(0,1),(-1,0),(1,0)]:
        nx,ny=cx+dx*hw//2,cy+dy*hw//2
        pygame.draw.polygon(surf,col,[(cx,cy),(nx-dx*t,ny-dy*t+dy*t),(nx,ny),(nx+dx*t,ny+dy*t-dy*t)])
    pygame.draw.polygon(surf,col,[(cx,cy-t*2),(cx+t*2,cy),(cx,cy+t*2),(cx-t*2,cy)])

FACE_DRAW={"STAR":sym_star,"ATK":sym_atk,"DEF":sym_def,"MOVE":sym_move,"CAP":sym_cap}

def draw_face_sym(surf,face,cx,cy,s,col):
    fn=FACE_DRAW.get(face)
    if fn: fn(surf,cx,cy,s,col)


# =============================================================================
# ANIMATION LANCER DE DÉS
# =============================================================================
ALL_FACES = ["MOVE", "ATK", "DEF", "CAP", "STAR"]

class DiceAnim:
    """Animation de lancer de 3 dés — overlay central sur le plateau."""
    IDLE     = "idle"
    ROLLING  = "rolling"
    LANDING  = "landing"    # dés atterrissent un par un
    DONE     = "done"       # résultat affiché, pause avant fermeture

    ROLL_DURATION  = 1.2    # secondes de tumble
    LAND_STAGGER   = 0.25   # délai entre chaque dé qui atterrit
    DONE_PAUSE     = 0.8    # pause après tous posés

    def __init__(self):
        self.state = self.IDLE
        self.t_start = 0
        self.dice = []         # [{"niveau":N, ...}, ...]
        self.faces = []        # ["ATK", "MOVE", "STAR"]
        self.side = "A"
        self._rng = random.Random()

    def start(self, dice, faces, side="A"):
        if not dice or not faces:
            return
        self.dice = dice[:3]
        self.faces = faces[:3]
        self.side = side
        self.state = self.ROLLING
        self.t_start = time.time()
        self._rng = random.Random(int(time.time() * 1000))

    def update(self):
        if self.state == self.IDLE:
            return
        elapsed = time.time() - self.t_start
        if self.state == self.ROLLING:
            if elapsed >= self.ROLL_DURATION:
                self.state = self.LANDING
        elif self.state == self.LANDING:
            land_end = self.ROLL_DURATION + len(self.dice) * self.LAND_STAGGER
            if elapsed >= land_end:
                self.state = self.DONE
                self.t_start = time.time()  # reset pour DONE_PAUSE
        elif self.state == self.DONE:
            if time.time() - self.t_start >= self.DONE_PAUSE:
                self.state = self.IDLE

    def is_active(self):
        return self.state != self.IDLE

    def draw(self, surf, fonts):
        if self.state == self.IDLE:
            return
        self.update()

        f_t, f_b, f_s = fonts
        elapsed = time.time() - (self.t_start if self.state != self.DONE else self.t_start - 0.1)
        n = len(self.dice)
        if n == 0:
            return

        # Overlay semi-transparent sur le plateau
        ov = pygame.Surface((BOARD_W, BOARD_H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 140))
        surf.blit(ov, (HUD_W, 0))

        # Titre "LANCER DE DES"
        side_col = C_P1_OUT if self.side == "A" else C_P2_OUT
        title = f_t.render(f"LANCER DE DES — J{self.side}", True, side_col)
        surf.blit(title, (HUD_W + (BOARD_W - title.get_width()) // 2, BOARD_H // 2 - 160))

        # Position des 3 dés
        die_sz = 100
        gap = 40
        total_w = n * die_sz + (n - 1) * gap
        base_x = HUD_W + (BOARD_W - total_w) // 2
        base_y = BOARD_H // 2 - die_sz // 2

        for i in range(n):
            dx = base_x + i * (die_sz + gap)
            dy = base_y
            die = self.dice[i] if i < len(self.dice) else {}
            lv = die.get("niveau", 1) if isinstance(die, dict) else 1
            final_face = self.faces[i] if i < len(self.faces) else "?"

            # Déterminer si ce dé a atterri
            land_time = self.ROLL_DURATION + i * self.LAND_STAGGER
            total_elapsed = time.time() - (self.t_start if self.state != self.DONE
                                            else self.t_start - self.DONE_PAUSE)
            if self.state == self.DONE:
                total_elapsed = self.ROLL_DURATION + n * self.LAND_STAGGER + 1
            else:
                total_elapsed = time.time() - self.t_start

            landed = total_elapsed >= land_time

            if landed:
                # Dé posé — face finale
                self._draw_die_big(surf, dx, dy, die_sz, lv, final_face, fonts, landed=True)
                # Label face
                face_label = f_b.render(final_face, True, FACE_COL.get(final_face, C_TEXT))
                surf.blit(face_label, (dx + (die_sz - face_label.get_width()) // 2,
                                        dy + die_sz + 12))
            else:
                # Dé en rotation — face aléatoire qui change vite
                tumble_face = self._rng.choice(ALL_FACES)
                # Offset vertical oscillant
                bob = int(12 * math.sin(total_elapsed * 14 + i * 2.5))
                # Légère rotation visuelle
                wobble = int(4 * math.sin(total_elapsed * 18 + i * 3))
                self._draw_die_big(surf, dx + wobble, dy + bob, die_sz, lv,
                                    tumble_face, fonts, landed=False)

        # Nom des dés sous les résultats
        if self.state in (self.LANDING, self.DONE):
            for i in range(n):
                die = self.dice[i] if i < len(self.dice) else {}
                name = die.get("nom", "?") if isinstance(die, dict) else "?"
                dx = base_x + i * (die_sz + gap)
                ns = f_s.render(name[:16], True, C_DIM)
                surf.blit(ns, (dx + (die_sz - ns.get_width()) // 2, base_y + die_sz + 32))

    def _draw_die_big(self, surf, x, y, sz, level, face, fonts, landed):
        """Dessine un gros dé avec face."""
        f_t, f_b, f_s = fonts
        bg = DIE_COLORS.get(level, (100, 100, 100))
        sym_col = DIE_SYM_COL.get(level, (20, 16, 30))

        if not landed:
            # Teinte plus claire pendant le tumble
            bg = tuple(min(255, c + 30) for c in bg)

        # Ombre
        shadow = pygame.Surface((sz + 6, sz + 6), pygame.SRCALPHA)
        pygame.draw.rect(shadow, (0, 0, 0, 80), (3, 3, sz, sz), border_radius=10)
        surf.blit(shadow, (x, y))

        # Corps du dé
        pygame.draw.rect(surf, bg, (x, y, sz, sz), border_radius=10)
        pygame.draw.rect(surf, (0, 0, 0), (x, y, sz, sz), 3, border_radius=10)

        # Reflet haut
        highlight = pygame.Surface((sz - 10, sz // 4), pygame.SRCALPHA)
        highlight.fill((255, 255, 255, 25))
        surf.blit(highlight, (x + 5, y + 3))

        # Niveau en bas-droite
        lv_s = f_b.render(f"L{level}", True, sym_col)
        surf.blit(lv_s, (x + sz - lv_s.get_width() - 6, y + sz - lv_s.get_height() - 4))

        # Symbole de face au centre
        face_sz = sz * 2 // 3
        draw_face_sym(surf, face, x + sz // 2, y + sz // 2 - 4, face_sz, sym_col)

        # Flash d'atterrissage
        if landed:
            flash_col = FACE_COL.get(face, C_ACCENT)
            glow = pygame.Surface((sz + 20, sz + 20), pygame.SRCALPHA)
            pygame.draw.rect(glow, (*flash_col, 30), (0, 0, sz + 20, sz + 20), border_radius=14)
            surf.blit(glow, (x - 10, y - 10))


# =============================================================================
# REPLAY TOUR IA — rejoue visuellement les actions de B
# =============================================================================
class IAReplay:
    IDLE    = "idle"
    DICE    = "dice"      # animation des dés B
    ACTION  = "action"    # replay action par action
    PAUSE   = "pause"     # courte pause entre actions

    def __init__(self):
        self.state = self.IDLE
        self.actions = []
        self.action_idx = 0
        self.t_action = 0

    def start(self, snap, dice_anim_ref):
        """Démarre le replay du tour IA B."""
        log_b = sg(snap, "log_B") or []
        if not log_b:
            return
        self.actions = self._parse_log(log_b)
        # Dés B d'abord
        des_b = sg(snap, "des_B") or []
        faces_b = sg(snap, "faces_B") or []
        if des_b and faces_b:
            dice_anim_ref.start(des_b, faces_b, "B")
            self.state = self.DICE
        elif self.actions:
            self.state = self.ACTION
            self.action_idx = 0
            self.t_action = time.time()
        # Sinon rien à rejouer

    def _parse_log(self, lines):
        """Parse les lignes du log B en actions visuelles."""
        actions = []
        for line in lines:
            if "=== Tour" in line:
                continue
            # MOVE : [IA B] X se déplace de (row,col) vers (row, col)
            if "[IA B]" in line and "déplace" in line:
                m = re.search(r'\] (.+?) se déplace de \((\d+),\s*(\d+)\) vers \((\d+),\s*(\d+)\)', line)
                if m:
                    actions.append({
                        "type": "move", "name": m.group(1),
                        "from_rc": (int(m.group(2)), int(m.group(3))),  # (row, col)
                        "to_rc":   (int(m.group(4)), int(m.group(5))),
                        "text": f"{m.group(1)} se déplace",
                        "dur": 0.5,
                    })
                    continue
            # ATK : [IA B] X attaque Y
            if "[IA B]" in line and "attaque" in line:
                m = re.search(r'\] (.+?) attaque (.+?)[\.\(]', line)
                name_a = m.group(1) if m else "?"
                name_t = m.group(2).strip() if m else "?"
                actions.append({
                    "type": "attack", "name": name_a, "target": name_t,
                    "text": f"{name_a} attaque {name_t}",
                    "dur": 0.8,
                })
                continue
            # INVOC
            if "[INVOC]" in line and ("IA place" in line or "invoqué" in line):
                actions.append({
                    "type": "invoc",
                    "text": line.split("]")[-1].strip()[:50],
                    "dur": 1.2,
                })
                continue
            # Dégâts (subit X dégâts)
            if "subit" in line and "dégâts" in line:
                m = re.search(r'(.+?) subit (\d+) dégâts.*?HP=(\d+)', line)
                if m:
                    actions.append({
                        "type": "damage",
                        "text": f"{m.group(1).strip()} -{m.group(2)}HP → {m.group(3)}HP",
                        "dur": 0.6,
                    })
                    continue
            # Éliminé
            if "éliminé" in line.lower():
                actions.append({
                    "type": "kill",
                    "text": line.split("]")[-1].strip()[:40],
                    "dur": 0.8,
                })
        return actions

    def update(self, dice_anim_ref):
        if self.state == self.IDLE:
            return
        if self.state == self.DICE:
            if not dice_anim_ref.is_active():
                if self.actions:
                    self.state = self.ACTION
                    self.action_idx = 0
                    self.t_action = time.time()
                else:
                    self.state = self.IDLE
        elif self.state == self.ACTION:
            if self.action_idx >= len(self.actions):
                self.state = self.IDLE
                return
            act = self.actions[self.action_idx]
            if time.time() - self.t_action >= act.get("dur", 0.6):
                self.action_idx += 1
                self.t_action = time.time()
                if self.action_idx >= len(self.actions):
                    self.state = self.IDLE

    def skip(self):
        self.state = self.IDLE
        self.actions = []
        self.action_idx = 0

    def is_active(self):
        return self.state != self.IDLE

    def draw(self, surf, fonts, rd):
        if self.state in (self.IDLE, self.DICE):
            return  # DICE: DiceAnim se dessine tout seul

        f_t, f_b, f_s = fonts

        # Overlay sombre sur le plateau
        ov = pygame.Surface((BOARD_W, BOARD_H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 100))
        surf.blit(ov, (HUD_W, 0))

        # Bandeau "TOUR IA B"
        banner = pygame.Surface((BOARD_W, 36), pygame.SRCALPHA)
        banner.fill((150, 30, 30, 180))
        surf.blit(banner, (HUD_W, 6))
        title = f_t.render("TOUR  IA  B", True, C_P2_OUT)
        surf.blit(title, (HUD_W + (BOARD_W - title.get_width()) // 2, 10))

        if self.action_idx >= len(self.actions):
            return
        act = self.actions[self.action_idx]

        # Texte de l'action au centre bas
        act_text = act.get("text", "")
        # Couleur par type
        type_colors = {
            "move": (100, 200, 255),
            "attack": (255, 100, 100),
            "invoc": (200, 160, 50),
            "damage": (255, 180, 80),
            "kill": (255, 50, 50),
        }
        tc = type_colors.get(act["type"], C_TEXT)

        # Type badge
        type_labels = {"move": "MOVE", "attack": "ATK", "invoc": "INVOC",
                       "damage": "DMG", "kill": "ÉLIMINÉ"}
        badge = f_b.render(type_labels.get(act["type"], "?"), True, tc)
        badge_x = HUD_W + (BOARD_W - badge.get_width()) // 2
        badge_y = BOARD_H // 2 - 40
        # Fond badge
        bg = pygame.Surface((badge.get_width() + 20, badge.get_height() + 10), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 160))
        surf.blit(bg, (badge_x - 10, badge_y - 5))
        surf.blit(badge, (badge_x, badge_y))

        # Texte détail
        det = f_b.render(act_text, True, C_TEXT)
        surf.blit(det, (HUD_W + (BOARD_W - det.get_width()) // 2, BOARD_H // 2 + 10))

        # Highlight cells sur le plateau
        if act["type"] == "move" and "from_rc" in act and "to_rc" in act:
            fr, fc = act["from_rc"]
            tr, tc2 = act["to_rc"]
            # Case départ — bleu
            if 0 <= fr < GRID_ROWS and 0 <= fc < GRID_COLS:
                poly = cpoly(rd, fc, fr)
                ov2 = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                pygame.draw.polygon(ov2, (80, 120, 255, 100), poly)
                pygame.draw.polygon(ov2, (120, 160, 255, 180), poly, 2)
                surf.blit(ov2, (0, 0))
            # Case arrivée — vert
            if 0 <= tr < GRID_ROWS and 0 <= tc2 < GRID_COLS:
                poly = cpoly(rd, tc2, tr)
                ov2 = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                pygame.draw.polygon(ov2, (80, 255, 120, 120), poly)
                pygame.draw.polygon(ov2, (120, 255, 160, 200), poly, 2)
                surf.blit(ov2, (0, 0))
                # Flèche direction
                cx_f, cy_f = ccc(rd, fc, fr)
                cx_t, cy_t = ccc(rd, tc2, tr)
                pygame.draw.line(surf, (120, 200, 255), (cx_f, cy_f), (cx_t, cy_t), 3)

        elif act["type"] == "attack":
            # Flash rouge sur le plateau
            t = time.time()
            pulse = int(60 + 40 * math.sin(t * 10))
            flash = pygame.Surface((BOARD_W, BOARD_H), pygame.SRCALPHA)
            flash.fill((255, 40, 40, pulse))
            surf.blit(flash, (HUD_W, 0))

        elif act["type"] == "kill":
            # Flash blanc intense
            flash = pygame.Surface((BOARD_W, BOARD_H), pygame.SRCALPHA)
            flash.fill((255, 255, 255, 40))
            surf.blit(flash, (HUD_W, 0))

        # Compteur actions + hint skip
        total = len(self.actions)
        prog = f_s.render(f"[{self.action_idx+1}/{total}]  Clic/Touche pour skip",
                          True, C_DIM)
        surf.blit(prog, (HUD_W + (BOARD_W - prog.get_width()) // 2, BOARD_H - 24))


# =============================================================================
# MINI MAP — avec overlay invocation
# =============================================================================

def get_mini_map_origin():
    """Retourne (mx0, my0) — coin haut-gauche de la mini map."""
    mcx = _MM + (BOT_MAP_W - MINI_W) // 2
    mcy = LOG_Y + (LOG_H - MINI_H) // 2
    return mcx, mcy


def mini_map_cell_at(mx, my):
    """
    Retourne (grid_col, grid_row) de la case mini map sous (mx,my).
    La mini map est tournée 90° : axe X = rows DDM, axe Y = cols DDM.
    """
    mx0, my0 = get_mini_map_origin()
    if not (mx0 <= mx <= mx0+MINI_W and my0 <= my <= my0+MINI_H):
        return None
    row = (mx - mx0) // MINI_CELL   # rangée DDM
    col = (my - my0) // MINI_CELL   # colonne DDM
    if 0 <= row < GRID_ROWS and 0 <= col < GRID_COLS:
        return (col, row)
    return None


def draw_mini_map_interactive(surf, snap, invoc, fonts, f_ps2p):
    """
    Mini map avec overlay selon le mode d'invocation.
    """
    f_t,f_b,f_s = fonts
    grid = sg(snap,"grille") or []
    ua = get_player(snap,"A").get("unites",[])
    ub = get_player(snap,"B").get("unites",[])
    um = {}
    for u in ua: um[(u["col"],u["row"])]="a"
    for u in ub: um[(u["col"],u["row"])]="b"

    mx0, my0 = get_mini_map_origin()

    # Fond
    pygame.draw.rect(surf,(14,12,18),(mx0-2,my0-2,MINI_W+4,MINI_H+4))
    pygame.draw.rect(surf,C_BORDER,(mx0-2,my0-2,MINI_W+4,MINI_H+4),1)

    # Calculer les cellules de la shape preview si applicable
    anc_cell   = None
    deploy_cells = set()
    shape_valid  = False
    if invoc.mode == InvocState.SHAPE_SELECT and invoc.selected_anchor:
        shape = invoc.shapes[invoc.shape_idx]
        col_a, row_a = invoc.selected_anchor
        anc_cell, dep = get_shape_cells(col_a, row_a, shape, invoc.rotation)
        deploy_cells = set(dep)
        shape_valid  = is_shape_valid(col_a, row_a, shape, invoc.rotation, snap, "A")

    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            px = mx0 + row*MINI_CELL
            py = my0 + col*MINI_CELL
            ch = grid[row][col] if row<len(grid) and col<len(grid[row]) else '.'

            # Couleur de base
            if ch=='A':   fill=C_P1_QG
            elif ch=='B': fill=C_P2_QG
            elif ch=='a': fill=C_P1_TILE
            elif ch=='b': fill=C_P2_TILE
            else:         fill=C_NEUTRAL

            pygame.draw.rect(surf,fill,(px,py,MINI_CELL-1,MINI_CELL-1))

            # Overlay ancrage valide
            if invoc.mode in (InvocState.ANCHOR_SELECT, InvocState.SHAPE_SELECT):
                if (col,row) in invoc.anchors:
                    ov_col = (C_ANCHOR_SEL if (col,row)==invoc.selected_anchor
                              else C_ANCHOR_HOV if (col,row)==invoc.hovered_anchor
                              else C_ANCHOR_VALID)
                    ov = pygame.Surface((MINI_CELL-1,MINI_CELL-1),pygame.SRCALPHA)
                    ov.fill(ov_col)
                    surf.blit(ov,(px,py))

            # Overlay shape : ancrage en jaune vif, déploiement en vert/rouge
            if anc_cell and (col,row) == anc_cell:
                ov = pygame.Surface((MINI_CELL-1,MINI_CELL-1),pygame.SRCALPHA)
                ov.fill((255,220,0,240))   # jaune ancrage
                surf.blit(ov,(px,py))
            elif (col,row) in deploy_cells:
                ov = pygame.Surface((MINI_CELL-1,MINI_CELL-1),pygame.SRCALPHA)
                ov.fill(C_SHAPE_PREVIEW if shape_valid else C_SHAPE_INVALID)
                surf.blit(ov,(px,py))

            # Unités
            if (col,row) in um:
                dot=C_P1_OUT if um[(col,row)]=="a" else C_P2_OUT
                pygame.draw.circle(surf,dot,
                    (px+MINI_CELL//2,py+MINI_CELL//2),max(2,MINI_CELL//2-1))

    # Label mode
    if invoc.mode == InvocState.ANCHOR_SELECT:
        lbl = f_ps2p.render(f"ANCRAGE L{invoc.niveau}",True,C_ACCENT)
        surf.blit(lbl,(mx0+(MINI_W-lbl.get_width())//2, my0-14))
    elif invoc.mode == InvocState.SHAPE_SELECT:
        lbl = f_ps2p.render(f"SHAPE {invoc.shape_idx+1}/{len(invoc.shapes)}",True,C_ACCENT)
        surf.blit(lbl,(mx0+(MINI_W-lbl.get_width())//2, my0-14))


# =============================================================================
# PANEL SHAPES — s'affiche à droite de la mini map
# =============================================================================

def draw_shape_panel(surf, fonts, f_ps2p, invoc, snap):
    """
    Panel de sélection de shape, affiché à côté de la mini map.
    Montre les 4 shapes disponibles pour le niveau, la rotation.
    """
    if invoc.mode != InvocState.SHAPE_SELECT: return
    f_t,f_b,f_s = fonts

    px0 = _CB + 8
    py0 = LOG_Y + 6
    pw  = BOT_CHP_W - 16
    ph  = LOG_H - 12

    pygame.draw.rect(surf,(16,14,28),(px0,py0,pw,ph))
    pygame.draw.rect(surf,C_ACCENT,(px0,py0,pw,ph),1)

    title = f_ps2p.render(f"L{invoc.niveau}",True,C_ACCENT)
    surf.blit(title,(px0+(pw-title.get_width())//2, py0+4))

    # 4 shapes en miniature
    cell_s = 5   # px par case dans la préview
    gap = 4
    sy = py0 + 22

    for i, shape in enumerate(invoc.shapes):
        selected = (i == invoc.shape_idx)
        bg = (28,26,50) if selected else (18,16,28)
        bord = C_ACCENT if selected else C_BORDER

        # Pour l'affichage dans le panel — normalisation locale uniquement
        pts_raw = rotate_shape(shape, invoc.rotation if selected else 0)
        min_r = min(r for r,c in pts_raw); min_c = min(c for r,c in pts_raw)
        pts = [(r-min_r, c-min_c) for r,c in pts_raw]
        max_r = max(r for r,c in pts)+1
        max_c = max(c for r,c in pts)+1
        sw2 = max_c * cell_s
        sh2 = max_r * cell_s

        box_w = pw - 8; box_h = 28
        bx = px0 + 4
        by = sy + i*(box_h+gap)

        if by + box_h > py0+ph-4: break

        pygame.draw.rect(surf,bg,(bx,by,box_w,box_h))
        pygame.draw.rect(surf,bord,(bx,by,box_w,box_h),1)

        # Dessin de la shape
        ox = bx + (box_w - sw2)//2
        oy = by + (box_h - sh2)//2
        draw_pts = rotate_shape(shape, invoc.rotation if selected else 0)
        for r,c in draw_pts:
            pygame.draw.rect(surf,
                C_P1_OUT if selected else C_DIM,
                (ox+c*cell_s, oy+r*cell_s, cell_s-1, cell_s-1))

        # Numéro
        ns = f_s.render(str(i+1), True, C_ACCENT if selected else C_DIM)
        surf.blit(ns,(bx+3, by+(box_h-ns.get_height())//2))

    # Rotation indicator
    rot_y = sy + len(invoc.shapes)*(28+gap) + 4
    if rot_y < py0+ph-20:
        rs = f_s.render(f"ROT {invoc.rotation*90}°",True,C_DIM)
        surf.blit(rs,(px0+(pw-rs.get_width())//2, rot_y))

    # Hint touches
    hint_y = py0+ph-28
    for txt,col in [("1-4:shape",C_DIM),("R:rot",C_DIM),("ENTER:ok",C_ACCENT),("ESC:annul",(200,80,80))]:
        hs = f_s.render(txt,True,col)
        surf.blit(hs,(px0+4, hint_y))
        hint_y += 14


# =============================================================================
# BOUTON INVOCATION dans la zone DÉS (si étoiles disponibles)
# =============================================================================

def draw_invoc_button(surf, f_ps2p, invoc, snap, sx, side_left, test_niveau=3):
    """Bouton INVOQUER + sélecteur niveau de test [ ] et ]."""
    active = sg(snap,"joueur_actif") or "?"
    if active != "A": return None

    connected = os.environ.get("DDM_GUI_CONNECTED","0") == "1"
    # En mode connecté, affiche le niveau du moteur ; sinon le niveau de test
    display_niveau = (get_invoc_niveau(snap) or test_niveau) if connected else test_niveau

    # Sélecteur niveau
    sel_x = sx + 4; sel_w = HUD_W - 8
    sel_y = DIE_LOG_H - 40
    pygame.draw.rect(surf,(18,16,30),(sel_x,sel_y,sel_w,16))
    pygame.draw.rect(surf,C_BORDER,(sel_x,sel_y,sel_w,16),1)
    if not connected:
        lbl = f_ps2p.render(f"O/P : changer niv",True,C_DIM)
        surf.blit(lbl,(sel_x+4, sel_y+2))
    # Niveau en accent au centre
    lv_s = f_ps2p.render(f"L{display_niveau}",True,C_ACCENT)
    surf.blit(lv_s,(sel_x+(sel_w-lv_s.get_width())//2, sel_y+2))

    # Bouton INVOQUER / ANNULER
    bx = sx + (HUD_W - 100)//2
    by = DIE_LOG_H - 20; bw = 100; bh = 16
    col = C_ACCENT if invoc.mode == InvocState.NORMAL else (200,80,80)
    txt = f"INVOC L{display_niveau}" if invoc.mode == InvocState.NORMAL else "ANNULER"
    pygame.draw.rect(surf,(20,18,32),(bx,by,bw,bh))
    pygame.draw.rect(surf,col,(bx,by,bw,bh),1)
    ls = f_ps2p.render(txt,True,col)
    surf.blit(ls,(bx+(bw-ls.get_width())//2, by+(bh-ls.get_height())//2))
    return pygame.Rect(bx,by,bw,bh)


# =============================================================================
# PLATEAU — identique Phase 2-E
# =============================================================================
def draw_board(surf,rd,snap,hov,hhov,invoc=None,mobs=None):
    grid=sg(snap,"grille") or []
    fac_a=get_player(snap,"A").get("faction","")
    fac_b=get_player(snap,"B").get("faction","")
    ua=get_player(snap,"A").get("unites",[])
    ub=get_player(snap,"B").get("unites",[])
    um={}
    for u in ua: um[(u["col"],u["row"])]=("a",u)
    for u in ub: um[(u["col"],u["row"])]=("b",u)
    _game_mode = os.environ.get("DDM_GAME_MODE", "hvia")
    _all_traps = sg(snap,"traps") or []
    # En HvIA : le joueur humain (A) ne voit pas les pièges ennemis (B)
    _visible_traps = _all_traps if _game_mode == "iaia" else [t for t in _all_traps if t.get("owner") == "A"]
    trap_map = {(t["c"], t["r"]): t for t in _visible_traps}

    # Calculer les cases shape à surbrillancer sur le plateau
    board_shape_cells = set()
    board_shape_valid = False
    board_anc_cell   = None
    board_dep_cells  = set()
    board_shape_valid = False
    if invoc and invoc.mode == InvocState.SHAPE_SELECT and invoc.selected_anchor:
        shape = invoc.shapes[invoc.shape_idx]
        col_a, row_a = invoc.selected_anchor
        board_anc_cell, dep = get_shape_cells(col_a, row_a, shape, invoc.rotation)
        board_dep_cells  = set(dep)
        board_shape_valid = is_shape_valid(col_a, row_a, shape, invoc.rotation, snap, "A")

    # Ancres valides à surbrillancer en mode ANCHOR_SELECT
    board_anchors = set()
    if invoc and invoc.mode == InvocState.ANCHOR_SELECT:
        board_anchors = set(invoc.anchors)

    pygame.draw.rect(surf,C_BOARD_BG,(HUD_W,0,BOARD_W,BOARD_H))
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            poly=cpoly(rd,col,row)
            ch=grid[row][col] if row<len(grid) and col<len(grid[row]) else '.'
            fill=cfill(ch,col,row)
            if hhov==(col,row): fill=tuple(min(255,c+55) for c in fill)
            elif hov==(col,row): fill=tuple(min(255,c+25) for c in fill)
            pygame.draw.polygon(surf,fill,poly)
            pygame.draw.polygon(surf,C_BLIGHT if ch in(P1_TILE,P2_TILE) else C_BORDER,poly,1)

            # Overlay ancres valides
            if (col,row) in board_anchors:
                ov_surf=pygame.Surface((SCREEN_W,SCREEN_H),pygame.SRCALPHA)
                pygame.draw.polygon(ov_surf,(200,200,50,80),poly)
                surf.blit(ov_surf,(0,0))

            # Overlay ancrage sélectionné — jaune vif
            if board_anc_cell and (col,row) == board_anc_cell:
                ov_surf=pygame.Surface((SCREEN_W,SCREEN_H),pygame.SRCALPHA)
                pygame.draw.polygon(ov_surf,(255,220,0,180),poly)
                pygame.draw.polygon(ov_surf,(255,240,50,255),poly,2)
                surf.blit(ov_surf,(0,0))

            # Overlay déploiement — vert/rouge
            elif (col,row) in board_dep_cells:
                ov_surf=pygame.Surface((SCREEN_W,SCREEN_H),pygame.SRCALPHA)
                ov_col=(80,220,80,120) if board_shape_valid else (220,60,60,120)
                border_col=(120,255,120,220) if board_shape_valid else (255,80,80,220)
                pygame.draw.polygon(ov_surf,ov_col,poly)
                pygame.draw.polygon(ov_surf,border_col,poly,2)
                surf.blit(ov_surf,(0,0))

            # Overlay unité sélectionnée — bordure blanche
            if mobs and mobs.mode==MobsState.SELECTED and snap:
                u=_get_unit_A(snap,mobs.selected_idx)
                if u and u["col"]==col and u["row"]==row:
                    ov_surf=pygame.Surface((SCREEN_W,SCREEN_H),pygame.SRCALPHA)
                    pygame.draw.polygon(ov_surf,(255,255,255,200),poly,3)
                    surf.blit(ov_surf,(0,0))

            # Overlay WAITING — pulsation dorée sur toutes les unités A
            if mobs and mobs.mode==MobsState.WAITING and snap:
                units_a = get_player(snap,"A").get("unites",[])
                for ua in units_a:
                    if ua["col"]==col and ua["row"]==row:
                        ov_surf=pygame.Surface((SCREEN_W,SCREEN_H),pygame.SRCALPHA)
                        pygame.draw.polygon(ov_surf,(255,200,0,60),poly)
                        pygame.draw.polygon(ov_surf,(255,200,0,150),poly,2)
                        surf.blit(ov_surf,(0,0))

            # Overlay unité A épuisée (moved+attacked) — grisée
            if snap and sg(snap,"joueur_actif")=="A":
                units_a = get_player(snap,"A").get("unites",[])
                for ua in units_a:
                    if ua["col"]==col and ua["row"]==row:
                        pool_a = get_player(snap,"A").get("pool",{})
                        no_move = ua.get("moved",False) or pool_a.get("MOVE",0)<=0
                        no_atk  = ua.get("attacked",False) or pool_a.get("ATK",0)<=0
                        no_cap  = pool_a.get("CAP",0)<=0
                        if no_move and no_atk and no_cap:
                            ov_surf=pygame.Surface((SCREEN_W,SCREEN_H),pygame.SRCALPHA)
                            pygame.draw.polygon(ov_surf,(0,0,0,100),poly)
                            surf.blit(ov_surf,(0,0))

            # Overlay MOVE — cases accessibles en vert clair
            if mobs and mobs.mode==MobsState.SELECTED:
                if (col,row) in mobs.move_cells:
                    ov_surf=pygame.Surface((SCREEN_W,SCREEN_H),pygame.SRCALPHA)
                    pygame.draw.polygon(ov_surf,(80,255,120,100),poly)
                    pygame.draw.polygon(ov_surf,(120,255,160,200),poly,2)
                    surf.blit(ov_surf,(0,0))

            # Overlay ATK — ennemis attaquables en rouge
            if mobs and mobs.mode==MobsState.SELECTED and mobs.atk_targets:
                enemies_b = get_player(snap,"B").get("unites",[]) if snap else []
                for ti in mobs.atk_targets:
                    if ti < len(enemies_b):
                        e=enemies_b[ti]
                        if (e["col"],e["row"])==(col,row):
                            ov_surf=pygame.Surface((SCREEN_W,SCREEN_H),pygame.SRCALPHA)
                            pygame.draw.polygon(ov_surf,(255,60,60,130),poly)
                            pygame.draw.polygon(ov_surf,(255,100,100,220),poly,2)
                            surf.blit(ov_surf,(0,0))

            # Overlay CAP_TARGET — portée de la capacité ciblée
            if mobs and mobs.mode==MobsState.CAP_TARGET and snap:
                u=_get_unit_A(snap,mobs.selected_idx)
                if u:
                    dist=abs(col-u["col"])+abs(row-u["row"])
                    rng=mobs.cap_range or 2
                    if dist<=rng:
                        ov_surf=pygame.Surface((SCREEN_W,SCREEN_H),pygame.SRCALPHA)
                        if mobs.cap_hov==(col,row):
                            pygame.draw.polygon(ov_surf,(220,80,255,180),poly)
                            pygame.draw.polygon(ov_surf,(240,120,255,255),poly,2)
                        else:
                            pygame.draw.polygon(ov_surf,(160,60,220,80),poly)
                            pygame.draw.polygon(ov_surf,(200,80,255,160),poly,1)
                        surf.blit(ov_surf,(0,0))

            # Overlay ATK QG — QG ennemi attaquable en rouge vif
            if mobs and mobs.mode==MobsState.SELECTED and mobs.qg_atk_cell:
                if (col,row)==mobs.qg_atk_cell:
                    ov_surf=pygame.Surface((SCREEN_W,SCREEN_H),pygame.SRCALPHA)
                    pygame.draw.polygon(ov_surf,(255,40,40,150),poly)
                    pygame.draw.polygon(ov_surf,(255,80,80,240),poly,3)
                    surf.blit(ov_surf,(0,0))

            # Overlay piège
            trap = trap_map.get((col, row))
            if trap:
                owner = trap.get("owner","A")
                t_col = (180,80,255,140) if owner=="A" else (255,140,40,140)
                t_brd = (200,100,255,220) if owner=="A" else (255,180,80,220)
                ov_surf=pygame.Surface((SCREEN_W,SCREEN_H),pygame.SRCALPHA)
                pygame.draw.polygon(ov_surf,t_col,poly)
                pygame.draw.polygon(ov_surf,t_brd,poly,2)
                surf.blit(ov_surf,(0,0))
                cx2,cy2=ccc(rd,col,row)
                rc=rd[row]; cw2=rc["cw"]
                if cw2 > 14:
                    dmg = trap.get("damage",0)
                    f_trap = pygame.font.SysFont(None, max(10, int(cw2*0.55)))
                    lbl = f_trap.render(f"⚠{dmg}", True, (255,255,220))
                    surf.blit(lbl, (cx2 - lbl.get_width()//2, cy2 - lbl.get_height()//2))

            if ch in(P1_QG,P2_QG):
                cx2,cy2=ccc(rd,col,row); rc=rd[row]; cw2=rc["cw"]
                tw=int(cw2*.95)
                mid_ch=rd[GRID_ROWS//2]["ch"]
                squeeze=max(0.3,min(1.0,rc["ch"]/mid_ch))
                th2=min(int(tw*squeeze),int(rc["ch"]*.95))
                fac_str=fac_a if ch==P1_QG else fac_b
                qg_spr=load_qg_spr(fac_str,tw,th2)
                if qg_spr:
                    sw2,sh2=qg_spr.get_size()
                    surf.blit(qg_spr,(cx2-sw2//2,int(rc["y_top"])+(int(rc["ch"])-sh2)//2))
                else:
                    r2=int(min(cw2,rc["ch"])*.22)
                    pygame.draw.circle(surf,(80,130,230) if ch==P1_QG else(230,80,80),(cx2,cy2),r2)

    for(col,row),(side,u) in sorted(um.items(),key=lambda x:x[0][1]):
        r=rd[row]; cw,ch2=r["cw"],r["ch"]
        cx2,cy2=ccc(rd,col,row)
        if u.get("is_champion"):
            spr=load_champ_spr(u.get("faction",""),u.get("nom",""),int(cw*.9),int(ch2*.9))
        else:
            spr=load_spr(fac_slug(u.get("faction","")),u.get("niveau"),
                         u.get("nom",""),u.get("lettre",""),int(cw*.9),int(ch2*.9))
        sw,sh=spr.get_size(); bx,by=cx2-sw//2,cy2-sh//2
        out=C_P1_OUT if side=="a" else C_P2_OUT
        pygame.draw.rect(surf,out,(bx-2,by-2,sw+4,sh+4),2)
        surf.blit(spr,(bx,by))
        if cw>18:
            bw2=int(cw*.7); bh2=max(2,int(ch2*.09))
            bx2=cx2-bw2//2; by2=by+sh+2
            pygame.draw.rect(surf,(18,16,20),(bx2,by2,bw2,bh2))
            pygame.draw.rect(surf,hp_c(u["hp"],u.get("hp_max",1)),
                             (bx2,by2,int(bw2*u["hp"]/max(1,u.get("hp_max",1))),bh2))
            # Icônes de statut
            statuses = []
            if u.get("stunned",0) > 0:
                statuses.append(((255,220,0),  f"S{u['stunned']}"))
            if u.get("poison_stacks",0) > 0:
                statuses.append(((180,60,220),  f"P{u['poison_stacks']}"))
            if u.get("buff_def",0) > 0:
                statuses.append(((60,180,255),  f"D+{u['buff_def']}"))
            if u.get("immovable",False):
                statuses.append(((140,140,140), "I"))
            if statuses and cw > 24:
                ic = max(6, int(cw * 0.18))
                f_ic = pygame.font.SysFont(None, max(8, ic))
                sx = bx2; sy = by2 + bh2 + 1
                for col_ic, lbl in statuses:
                    pygame.draw.rect(surf, col_ic, (sx, sy, ic, ic))
                    if ic >= 8:
                        t_ic = f_ic.render(lbl, True, (0,0,0))
                        surf.blit(t_ic, (sx, sy))
                    sx += ic + 1


# =============================================================================
# HUD (simplifié — reprend Phase 2-E)
# =============================================================================
def parse_rolled_faces(log_lines,side):
    for line in reversed(log_lines):
        if "[DÉS]" not in line: continue
        if f"Joueur {side}" not in line and f"J{side} :" not in line: return []
        faces=[]; rev={"MV":"MOVE","AT":"ATK","DF":"DEF","CP":"CAP","★":"STAR",
                       "MOVE":"MOVE","ATK":"ATK","DEF":"DEF","CAP":"CAP","STAR":"STAR"}
        for part in line.split("|"):
            if "→" in part:
                f=part.split("→")[-1].strip(); faces.append(rev.get(f,f))
        return faces
    return []

def draw_hud_top(surf,fonts,snap,side,sx,side_left,f_ps2p,invoc,dice_cache=None,rolled_cache=None):
    f_t,f_b,f_s=fonts
    out=C_P1_OUT if side=="A" else C_P2_OUT
    # Dés par côté : d'abord des_A/des_B (snapshot complet), sinon cache, sinon "des" legacy
    dice = sg(snap, f"des_{side}") or []
    if not dice and dice_cache and dice_cache.get(side):
        dice = dice_cache[side]
    if not dice:
        dice = sg(snap, "des") or []
    log_lines=sg(snap,"log") or []
    # Faces roulées : d'abord faces_A/faces_B du snapshot, sinon log, sinon cache
    rolled = sg(snap, f"faces_{side}") or []
    if not rolled:
        rolled=parse_rolled_faces(log_lines,side)
    if not rolled and rolled_cache and side in rolled_cache:
        rolled = rolled_cache[side]
    active=sg(snap,"joueur_actif") or "?"

    pygame.draw.rect(surf,C_HUD_TOP,(sx,0,HUD_W,DIE_LOG_H))
    pygame.draw.line(surf,C_BORDER,(sx,DIE_LOG_H),(sx+HUD_W,DIE_LOG_H),1)

    # Layout : dés 25% | log 75%
    die_w = int(HUD_W * 0.25)
    log_w = HUD_W - die_w
    if side_left:
        die_x=sx; log_x=sx+die_w; sep_x=sx+die_w
    else:
        log_x=sx; die_x=sx+log_w; sep_x=sx+log_w
    pygame.draw.line(surf,C_BORDER,(sep_x,2),(sep_x,DIE_LOG_H-2),1)

    # --- Zone DÉS ---
    lbl=f_ps2p.render(f"DES J{side}",True,C_ACCENT if active==side else C_DIM)
    surf.blit(lbl,(die_x+(die_w-lbl.get_width())//2,3))

    connected = os.environ.get("DDM_GUI_CONNECTED","0") == "1"
    invoc_niveau = get_invoc_niveau(snap) if side=="A" and active=="A" else None
    show_invoc = (invoc_niveau is not None) or (side=="A" and not connected)

    # Espace dés : laisse de la place pour le bouton INVOC si nécessaire
    btn_h = 32 if show_invoc else 0
    die_area_top = 18
    die_area_h   = DIE_LOG_H - die_area_top - btn_h - 4

    n_dice=min(len(dice),3)
    if n_dice>0:
        sz=min(42,(die_w-8)//n_dice-4); sz=max(20,sz)
        total_w=n_dice*(sz+4)-4
        start_dx=die_x+(die_w-total_w)//2
        ddy=die_area_top+(die_area_h-sz)//2
        for i,die in enumerate(dice[:3]):
            ddx=start_dx+i*(sz+4)
            lv=die.get("niveau",1) if isinstance(die,dict) else 1
            pygame.draw.rect(surf,DIE_COLORS.get(lv,(100,100,100)),(ddx,ddy,sz,sz),border_radius=4)
            pygame.draw.rect(surf,(0,0,0),(ddx,ddy,sz,sz),2,border_radius=4)
            lv_s=f_s.render(str(lv),True,DIE_SYM_COL.get(lv,(200,200,200)))
            surf.blit(lv_s,(ddx+sz-lv_s.get_width()-2,ddy+sz-lv_s.get_height()-2))
            face=rolled[i] if rolled and i<len(rolled) else ""
            if face:
                draw_face_sym(surf,face,ddx+sz//2,ddy+sz//2-2,sz*2//3,DIE_SYM_COL.get(lv,(20,16,30)))
            else:
                qs=f_s.render("?",True,(80,76,90))
                surf.blit(qs,(ddx+sz//2-qs.get_width()//2,ddy+sz//2-qs.get_height()//2))

    # Bouton INVOC — sous les dés, dans la zone dés uniquement
    btn = None
    if show_invoc and side=="A":
        bx=die_x+4; by=DIE_LOG_H-btn_h+2; bw=die_w-8; bh=btn_h-6
        connected2 = os.environ.get("DDM_GUI_CONNECTED","0") == "1"
        display_niv=(invoc_niveau or invoc.test_niveau)
        col=C_ACCENT if invoc.mode==InvocState.NORMAL else (200,80,80)
        txt=f"INVOC L{display_niv}" if invoc.mode==InvocState.NORMAL else "ANNULER"
        pygame.draw.rect(surf,(20,18,32),(bx,by,bw,bh))
        pygame.draw.rect(surf,col,(bx,by,bw,bh),1)
        ls=f_ps2p.render(txt,True,col)
        surf.blit(ls,(bx+(bw-ls.get_width())//2,by+(bh-ls.get_height())//2))
        btn=pygame.Rect(bx,by,bw,bh)

    # --- Zone LOG — uniquement dés/pool/invoc du tour actif ---
    lbl2=f_ps2p.render("LOG",True,C_DIM)
    surf.blit(lbl2,(log_x+(log_w-lbl2.get_width())//2,3))
    # Filtre les lignes du tour courant
    cur_lines = []
    for line in reversed(log_lines):
        if "=== Tour" in line: break
        if any(k in line for k in ["[DÉS]","[POOL]","[INVOC]","[GUI] En attente"]):
            cur_lines.insert(0, line)
    LH=14; mv=(DIE_LOG_H-18)//LH
    max_chars=log_w//6
    for i,line in enumerate(cur_lines[-mv:]):
        lc=(C_ACCENT if "[INVOC]" in line
            else (178,158,218) if "[DÉS]" in line
            else (148,218,148) if "[POOL]" in line
            else C_DIM)
        surf.blit(f_s.render(line[:max_chars],True,lc),(log_x+4,18+i*LH))

    if side=="A":
        return btn
    return None

SPR_H=44

def draw_hud_units(surf,fonts,snap,side,sx):
    f_t,f_b,f_s=fonts; out=C_P1_OUT if side=="A" else C_P2_OUT; pw=HUD_W
    units=get_player(snap,side).get("unites",[])
    y=UNIT_Y; ah=LOG_Y-UNIT_Y
    pygame.draw.rect(surf,C_HUD_BG,(sx,y,pw,ah))
    pygame.draw.line(surf,C_BORDER,(sx+(pw if side=="A" else 0),y),(sx+(pw if side=="A" else 0),LOG_Y),1)
    surf.blit(f_s.render(f"Unites J{side}",True,C_DIM),(sx+8,y+3)); y+=18
    mx,my=pygame.mouse.get_pos(); hh=None; rh=SPR_H+8
    for i,u in enumerate(units):
        uy=y+i*rh
        if uy+rh>LOG_Y-2: surf.blit(f_s.render(f"+{len(units)-i}",True,C_DIM),(sx+8,uy+2)); break
        is_h=(sx<=mx<=sx+pw and uy<=my<=uy+rh)
        bg=tuple(min(255,c+15) for c in(C_ROW_A if i%2==0 else C_ROW_B)) if is_h else(C_ROW_A if i%2==0 else C_ROW_B)
        pygame.draw.rect(surf,bg,(sx,uy,pw,rh)); pygame.draw.rect(surf,out,(sx,uy,3,rh))
        if is_h: hh=(u["col"],u["row"])
        spr=load_spr(fac_slug(u.get("faction","")),u.get("niveau"),u.get("nom",""),u.get("lettre",""),SPR_H,SPR_H)
        sw2,sh2=spr.get_size(); surf.blit(spr,(sx+6,uy+(rh-sh2)//2))
        tx=sx+SPR_H+10; ty=uy+3
        surf.blit(f_b.render(u.get("nom","?")[:18],True,C_TEXT),(tx,ty))
        surf.blit(f_s.render("Champ." if u.get("is_champion") else f"Lv{u.get('niveau',1)}",True,C_ACCENT if u.get("is_champion") else C_DIM),(tx,ty+16))
        bw=86; bh=4; bx3=tx+34; by3=ty+18; r3=u["hp"]/max(1,u.get("hp_max",1))
        pygame.draw.rect(surf,(18,16,20),(bx3,by3,bw,bh))
        pygame.draw.rect(surf,hp_c(u["hp"],u.get("hp_max",1)),(bx3,by3,int(bw*r3),bh))
        surf.blit(f_s.render(f"{u['hp']}/{u.get('hp_max',0)}",True,C_DIM),(bx3+bw+3,by3-2))
        surf.blit(f_s.render(f"AT{u['atk']} DF{u['def']}",True,C_DIM),(tx,ty+28))
        bx4=sx+pw-52
        if u.get("moved"): pygame.draw.rect(surf,C_MOVED,(bx4,uy+4,22,12)); surf.blit(f_s.render("MOV",True,(100,200,100)),(bx4+1,uy+5))
        if u.get("attacked"): pygame.draw.rect(surf,C_ATK_DONE,(bx4+24,uy+4,22,12)); surf.blit(f_s.render("ATK",True,(200,100,100)),(bx4+25,uy+5))
        pygame.draw.line(surf,C_BORDER,(sx,uy+rh),(sx+pw,uy+rh),1)

        # Tooltip description CAP au survol
        if is_h:
            _side_left = (sx == 0)  # côté gauche si sx=0
            cap_desc = u.get("cap_description") or u.get("ability_description") or u.get("capacite","")
            if not cap_desc:
                ae = u.get("ability_effects","")
                if ae: cap_desc = str(ae)[:120]
            if cap_desc:
                cap_desc = str(cap_desc)
                words = cap_desc.split(); lines_t=[]; cur=""
                for w2 in words:
                    if len(cur)+len(w2)+1<=40: cur=(cur+" "+w2).strip()
                    else: lines_t.append(cur); cur=w2
                if cur: lines_t.append(cur)
                lines_t = lines_t[:4]
                tw2=220; th2=len(lines_t)*14+10
                if _side_left: tx2=sx+pw+4
                else: tx2=sx-tw2-4
                ty2=min(uy, LOG_Y-th2-4)
                pygame.draw.rect(surf,(12,10,22),(tx2,ty2,tw2,th2))
                pygame.draw.rect(surf,C_ACCENT,(tx2,ty2,tw2,th2),1)
                for li,lt in enumerate(lines_t):
                    surf.blit(f_s.render(lt,True,C_TEXT),(tx2+4,ty2+4+li*14))

    return hh

def draw_champion_slot(surf,fonts,snap,side,x,y,w,h,f_ps2p):
    f_t,f_b,f_s=fonts; pdata=get_player(snap,side); champ=pdata.get("champion") or {}; etat=champ.get("etat","dormant")
    pygame.draw.rect(surf,C_CHP_BG,(x,y,w,h)); pygame.draw.rect(surf,C_BORDER,(x,y,w,h),1)
    if not champ: return
    sq=min(w,h)-20; sq=max(sq,20)
    spr=load_champ_spr(champ.get("faction",""),champ.get("nom","?"),sq,sq); sw,sh=spr.get_size()
    if etat=="dormant":
        dark=pygame.Surface((sw,sh)); dark.fill((0,0,0)); dark.set_alpha(150); spr=spr.copy(); spr.blit(dark,(0,0))
    surf.blit(spr,(x+(w-sw)//2,y+(h-sh)//2-8))
    ec=(C_DIM if etat=="dormant" else C_ACCENT if etat=="deployed" else C_HP_LOW)
    et=f_ps2p.render(etat[:8],True,ec); surf.blit(et,(x+(w-et.get_width())//2,y+h-14))

def draw_joueur_bloc(surf,fonts,snap,side,x,y,w,h,f_ps2p):
    f_t,f_b,f_s=fonts; out=C_P1_OUT if side=="A" else C_P2_OUT
    acc=C_JOU_A_ACC if side=="A" else C_JOU_B_ACC; pdata=get_player(snap,side)
    pygame.draw.rect(surf,C_JOU_BG,(x,y,w,h)); pygame.draw.rect(surf,acc,(x,y,w,4)); pygame.draw.rect(surf,C_BORDER,(x,y,w,h),1)
    tour=sg(snap,"tour") or 0; active=sg(snap,"joueur_actif") or "?"
    t=f_ps2p.render(f"JOU {side} T{tour}",True,out); surf.blit(t,(x+(w-t.get_width())//2,y+6))
    LH=18; GAP=6; cy=y+6+f_ps2p.get_height()+GAP
    fac=pdata.get("faction","?"); surf.blit(f_s.render(fac[:24],True,C_DIM),(x+6,cy)); cy+=LH+GAP
    qg=pdata.get("qg",{}); surf.blit(f_s.render(f"QG {qg.get('hp',0)}/{qg.get('hp_max',35)}  DEF:{qg.get('def',0)}",True,C_TEXT),(x+6,cy)); cy+=LH+GAP*2
    champ=pdata.get("champion") or {}
    if champ and cy+LH*2+GAP<y+h-LH-6:
        surf.blit(f_s.render(f">{champ.get('nom','?')[:18]}",True,C_ACCENT),(x+6,cy)); cy+=LH
        ec=(C_DIM if champ.get("etat")=="dormant" else C_ACCENT)
        surf.blit(f_s.render(f"HP{champ.get('hp',0)} [{champ.get('etat','?')}]",True,ec),(x+6,cy)); cy+=LH+GAP*2
    pool=pdata.get("pool",{}); pool_y=y+h-LH*2-6
    surf.blit(f_s.render(f"MV{pool.get('MOVE',0)}  AT{pool.get('ATK',0)}",True,C_DIM),(x+6,pool_y))
    surf.blit(f_s.render(f"DF{pool.get('DEF',0)}  CP{pool.get('CAP',0)}",True,C_DIM),(x+6,pool_y+LH))
    if active==side: pygame.draw.rect(surf,C_ACCENT,(x+w-12,y+6,8,8))
    # Bouton FIN DE TOUR — side A uniquement, quand c'est son tour
    end_btn = None
    if side=="A" and active=="A":
        bw2=w-12; bh2=20; bx2=x+6; by2=y+h-LH*2-30
        col_btn=(60,38,80) if True else C_DIM
        pygame.draw.rect(surf,col_btn,(bx2,by2,bw2,bh2),border_radius=3)
        pygame.draw.rect(surf,C_P1_OUT,(bx2,by2,bw2,bh2),1,border_radius=3)
        lbl=f_s.render("FIN DE TOUR",True,C_P1_OUT)
        surf.blit(lbl,(bx2+(bw2-lbl.get_width())//2,by2+(bh2-lbl.get_height())//2))
        end_btn=pygame.Rect(bx2,by2,bw2,bh2)
    return end_btn

def draw_log_bloc(surf,fonts,title,lines,scroll,x,y,w,h,tc,f_ps2p):
    f_t,f_b,f_s=fonts; pygame.draw.rect(surf,C_LOG_BG,(x,y,w,h)); pygame.draw.rect(surf,C_BORDER,(x,y,w,h),1)
    t=f_ps2p.render(title,True,tc); surf.blit(t,(x+(w-t.get_width())//2,y+4))
    LH=18; mv=(h-24)//LH; st=max(0,len(lines)-mv-scroll)
    max_c = max(1, w//6)
    for i,line in enumerate(lines[st:st+mv]):
        lc=(tc if "[ATK]" in line else(148,218,148) if "[MOV]" in line else C_ACCENT if "[INVOC]" in line else C_DIM)
        surf.blit(f_s.render(line[:max_c],True,lc),(x+4,y+22+i*LH))
    if scroll>0: surf.blit(f_s.render(f"+{scroll}",True,C_DIM),(x+w-30,y+4))

def draw_game_over(surf, fonts, winner: str, snap):
    """Overlay plein écran affiché quand la partie est terminée."""
    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 200))
    surf.blit(overlay, (0, 0))

    f_big, f_med, f_small = fonts

    if winner == "A":
        label = "VICTOIRE  JOUEUR  A"
        color = C_P1_OUT
    elif winner == "B":
        label = "VICTOIRE  JOUEUR  B"
        color = C_P2_OUT
    else:
        label = "MATCH  NUL"
        color = (200, 200, 200)

    lbl = f_big.render(label, True, color)
    surf.blit(lbl, ((SCREEN_W - lbl.get_width()) // 2, SCREEN_H // 2 - 60))

    pa = get_player(snap, "A")
    pb = get_player(snap, "B")
    hp_a = pa.get("qg", {}).get("hp", 0)
    hp_b = pb.get("qg", {}).get("hp", 0)
    sub = f_med.render(f"QG A : {hp_a} HP     QG B : {hp_b} HP", True, C_TEXT)
    surf.blit(sub, ((SCREEN_W - sub.get_width()) // 2, SCREEN_H // 2 + 10))

    hint = f_small.render("Appuie sur ECHAP pour quitter", True, C_DIM)
    surf.blit(hint, ((SCREEN_W - hint.get_width()) // 2, SCREEN_H // 2 + 60))


def draw_help_overlay(surf, fonts, f_ps2p):
    """Overlay touches clavier — affiché au démarrage et avec H."""
    connected = os.environ.get("DDM_GUI_CONNECTED","0") == "1"

    sections = [
        ("NAVIGATION", [
            ("H",           "Afficher/masquer cette aide"),
            ("ESC",         "Annuler action / Quitter"),
            ("A / Q",       "Scroll log A"),
            ("↑ / ↓",       "Scroll log B"),
        ]),
        ("INVOCATION", [
            ("INVOC L?",    "Clic bouton pour démarrer l'invocation"),
            ("1 / 2 / 3",   "Changer de shape"),
            ("R",           "Rotation 90°"),
            ("ENTER",       "Valider la shape"),
            ("ESC",         "Annuler l'invocation"),
        ]),
    ]
    if not connected:
        sections.append(("TEST (mode déconnecté)", [
            ("O / P",       "Niveau invoc -1 / +1"),
            ("C",           "Effacer command.json"),
        ]))
    else:
        sections.append(("PHASE MOBS (mode connecté)", [
            ("Clic unité A",   "Sélectionner une unité"),
            ("Clic case verte","Déplacer l'unité (coûte 1 MOVE)"),
            ("Clic ennemi adj","Attaquer (coûte 1 ATK)"),
            ("C",              "Utiliser capacité de l'unité (1 CAP)"),
            ("F",              "Fin de phase mobs"),
            ("ESC",            "Désélectionner"),
        ]))

    # Dimensions
    col_w = 380; pad = 20; lh = 18
    n_cols = 2
    rows_per_col = sum(len(s[1])+2 for s in sections[:2])
    total_w = col_w * n_cols + pad * 3
    total_h = rows_per_col * lh + pad * 2 + 30
    ox = (SCREEN_W - total_w) // 2
    oy = (SCREEN_H - total_h) // 2

    # Fond
    bg = pygame.Surface((total_w, total_h), pygame.SRCALPHA)
    bg.fill((10, 8, 20, 220))
    surf.blit(bg, (ox, oy))
    pygame.draw.rect(surf, C_ACCENT, (ox, oy, total_w, total_h), 1)

    # Titre
    f_title = fonts[0]
    title = f_ps2p.render("DDM — RACCOURCIS CLAVIER", True, C_ACCENT)
    surf.blit(title, (ox + (total_w - title.get_width())//2, oy + pad//2))

    # Sous-titre
    mode_str = "MODE CONNECTÉ (moteur actif)" if connected else "MODE TEST (standalone)"
    mode_lbl = fonts[2].render(mode_str, True, C_DIM)
    surf.blit(mode_lbl, (ox + (total_w - mode_lbl.get_width())//2, oy + pad//2 + 14))

    # Sections en deux colonnes
    cx = ox + pad
    cy = oy + 42
    for i, (sec_title, entries) in enumerate(sections):
        col_x = ox + pad + (i % n_cols) * (col_w + pad)
        col_y = cy + (i // n_cols) * 0

        # Section title
        st = fonts[1].render(f"── {sec_title} ──", True, C_P1_OUT if i % 2 == 0 else C_P2_OUT)
        surf.blit(st, (col_x, col_y))
        col_y += lh + 2

        for key, desc in entries:
            k_surf = f_ps2p.render(key, True, (220, 220, 140))
            d_surf = fonts[2].render(desc, True, C_TEXT)
            surf.blit(k_surf, (col_x, col_y))
            surf.blit(d_surf, (col_x + 90, col_y + 1))
            col_y += lh

        # Update cy for next row of sections
        if i % n_cols == 1:
            cy += col_y - (oy + 42)

    # Bas
    hint = fonts[2].render("Appuie sur H ou n'importe quelle touche pour fermer", True, C_DIM)
    surf.blit(hint, (ox + (total_w - hint.get_width())//2, oy + total_h - 18))


def draw_command_overlay(surf, fonts, f_ps2p):
    """
    Affiche le contenu du command.json en overlay bas-centre
    pendant 3 secondes après écriture.
    """
    if not COMMAND_PATH.exists(): return
    try:
        with open(COMMAND_PATH,"r",encoding="utf-8") as f:
            cmd = json.load(f)
    except: return

    f_s = fonts[2]
    lines = [
        f"command.json",
        f"action  : {cmd.get('action','?')}",
        f"player  : {cmd.get('player','?')}",
        f"ancrage : {cmd.get('ancrage','?')}",
        f"shape   : {cmd.get('shape_idx','?')}",
        f"rot     : {cmd.get('rotation','?')} ({cmd.get('rotation',0)*90}deg)",
        f"niveau  : {cmd.get('niveau','?')}",
    ]

    lh = 16
    pw = 260; ph = len(lines)*lh + 16
    px = HUD_W + (BOARD_W - pw)//2
    py = BOARD_H//2 - ph//2

    pygame.draw.rect(surf,(10,8,18),(px,py,pw,ph))
    pygame.draw.rect(surf,C_ACCENT,(px,py,pw,ph),1)

    for i,line in enumerate(lines):
        col = C_ACCENT if i==0 else (C_P1_OUT if "ancrage" in line or "shape" in line else C_TEXT)
        surf.blit(f_s.render(line,True,col),(px+8,py+8+i*lh))


def draw_bottom(surf,fonts,snap,ha,hb,sa,sb,f_ps2p,invoc):
    y=LOG_Y; h=LOG_H
    pygame.draw.rect(surf,C_BOT_BG,(0,y,SCREEN_W,h)); pygame.draw.line(surf,C_BORDER,(0,y),(SCREEN_W,y),1)
    draw_log_bloc(surf,fonts,"LOG A",ha,sa,_LA,y,BOT_LOG_W,h,C_P1_OUT,f_ps2p)
    end_turn_btn=draw_joueur_bloc(surf,fonts,snap,"A",_JA,y,BOT_JOU_W,h,f_ps2p)
    draw_champion_slot(surf,fonts,snap,"A",_CA,y,BOT_CHP_W,h,f_ps2p)
    draw_mini_map_interactive(surf,snap,invoc,fonts,f_ps2p)
    draw_shape_panel(surf,fonts,f_ps2p,invoc,snap)
    draw_champion_slot(surf,fonts,snap,"B",_CB,y,BOT_CHP_W,h,f_ps2p)
    draw_joueur_bloc(surf,fonts,snap,"B",_JB,y,BOT_JOU_W,h,f_ps2p)
    draw_log_bloc(surf,fonts,"LOG B",hb,sb,_LB,y,BOT_LOG_W,h,C_P2_OUT,f_ps2p)
    tour=sg(snap,"tour") or 0; active=sg(snap,"joueur_actif") or "?"
    f_s=fonts[2]; ts=f_s.render(f"Tour {tour} - J{active}",True,C_ACCENT)
    surf.blit(ts,(_MM+(BOT_MAP_W-ts.get_width())//2,y+h-16))
    return end_turn_btn

# =============================================================================
# BOUCLE PRINCIPALE
# =============================================================================
def main():
    pygame.init()
    screen=pygame.display.set_mode((SCREEN_W,SCREEN_H), pygame.SCALED | pygame.RESIZABLE)
    pygame.display.set_caption("DDM — Renderer")
    clock=pygame.time.Clock()

    try: f_ps2p=pygame.font.Font(FONT_PATH,9)
    except: f_ps2p=pygame.font.SysFont(None,16)

    fonts=(pygame.font.SysFont(None,20),
           pygame.font.SysFont(None,18),
           pygame.font.SysFont(None,16))

    rd=compute_perspective()
    ha=[]; hb=[]; last_t=-1; sa=sb=0
    hov=None; hhov=None
    invoc=InvocState()
    mobs=MobsState()
    invoc_btn_rect=None
    end_turn_btn=None
    show_help=True   # affiché au démarrage, H pour toggle
    dice_cache = {"A": [], "B": []}   # dés cachés par joueur
    rolled_cache = {"A": [], "B": []}  # faces cachées par joueur
    _invoc_dismissed = False  # True si le joueur a cancel l'invoc ce tour
    _invoc_cmd_log_len = 0   # longueur du log au moment de l'envoi de la commande
    dice_anim = DiceAnim()
    ia_replay = IAReplay()
    _pending_a_dice = []
    _pending_a_faces = []
    _gameover_time = None

    # Signal de connexion au moteur iaia
    _connected = os.environ.get("DDM_GUI_CONNECTED", "0") == "1"
    if _connected:
        try:
            _ready_f = SNAPSHOT_PATH.parent / "renderer_ready.json"
            import json as _j
            _ready_f.write_text(_j.dumps({"ready": True}), encoding="utf-8")
        except Exception as _e:
            print(f"[RENDERER] Erreur signal ready : {_e}")

    running=True
    _last_log_len = 0   # track snapshot log length for intra-turn updates

    # Pause menu (ouvert via ESC en cours de partie)
    pause_open = False
    pause_sel  = 0
    pause_msg  = ""   # message temporaire (ex: "Sauvegarder bientôt dispo")
    pause_items = [
        ("reprendre",   "REPRENDRE"),
        ("sauvegarder", "SAUVEGARDER  (a venir)"),
        ("options",     "OPTIONS  (a venir)"),
        ("quitter",     "QUITTER LA PARTIE"),
    ]

    while running:
        snap=load_snapshot(fast=(mobs.mode==MobsState.WAITING))
        if snap:
            t=sg(snap,"tour") or 0
            if t!=last_t:
                last_t=t; invoc.reset(); mobs.reset()
                _last_log_len = 0
                _invoc_dismissed = False
                active_side = sg(snap,"joueur_actif") or "?"

                # Si c'est le tour A et qu'on a un log B → replay IA d'abord
                log_b = sg(snap, "log_B") or []
                if active_side == "A" and log_b and len(log_b) > 1:
                    ia_replay.start(snap, dice_anim)
                    # Sauvegarde les dés A pour les lancer APRÈS le replay
                    _pending_a_dice = sg(snap, f"des_A") or sg(snap, "des") or []
                    _pending_a_faces = sg(snap, "faces_A") or []
                    if not _pending_a_faces:
                        _log = sg(snap, "log") or []
                        _pending_a_faces = parse_rolled_faces(_log, "A")
                else:
                    # Pas de replay B → lancer dés directement
                    anim_dice = sg(snap, f"des_{active_side}") or sg(snap, "des") or []
                    anim_faces = sg(snap, f"faces_{active_side}") or []
                    if not anim_faces:
                        _log = sg(snap, "log") or []
                        anim_faces = parse_rolled_faces(_log, active_side)
                    if anim_dice and anim_faces:
                        dice_anim.start(anim_dice, anim_faces, active_side)
                    _pending_a_dice = []
                    _pending_a_faces = []
            # Cache les dés du joueur actif
            active_side = sg(snap,"joueur_actif") or "?"
            snap_dice = sg(snap,"des") or []
            if snap_dice and active_side in ("A","B"):
                dice_cache[active_side] = snap_dice
                # Cache les faces roulées
                snap_log = sg(snap,"log") or []
                faces = parse_rolled_faces(snap_log, active_side)
                if faces:
                    rolled_cache[active_side] = faces
            # Capture action lines — both on turn change and intra-turn updates
            log_lines = sg(snap,"log") or []
            if len(log_lines) > _last_log_len:
                act=sg(snap,"joueur_actif") or "?"
                _action_keys = ("[MOV]","[ATK]","[CAP]","éliminé","Contre-attaque","→QG","[INVOC]","[CMD]")
                for line in log_lines[_last_log_len:]:
                    if any(k in line for k in _action_keys):
                        (ha if act=="A" else hb).append(line)
                _last_log_len = len(log_lines)
            # Sort du WAITING si snapshot a changé
            mobs.on_snapshot_update(snap)

            # Update replay IA B
            ia_replay.update(dice_anim)
            # Quand le replay B finit → lance les dés A
            if not ia_replay.is_active() and _pending_a_dice and _pending_a_faces:
                if not dice_anim.is_active():
                    dice_anim.start(_pending_a_dice, _pending_a_faces, "A")
                    _pending_a_dice = []
                    _pending_a_faces = []

            # Auto-démarrage invocation si le moteur attend une commande d'invoc
            # (sauf si animation/replay en cours)
            _connected = os.environ.get("DDM_GUI_CONNECTED","0") == "1"
            if _connected and invoc.mode == InvocState.NORMAL and not dice_anim.is_active() and not ia_replay.is_active():
                inv_niv = get_invoc_niveau(snap)
                if inv_niv is not None and sg(snap,"joueur_actif") == "A":
                    if _invoc_dismissed:
                        # Détecter un retry moteur : log a grandi depuis l'envoi de la commande
                        _cur_log_len = len(sg(snap,"log") or [])
                        if _cur_log_len > _invoc_cmd_log_len:
                            _invoc_dismissed = False
                    if not _invoc_dismissed:
                        invoc.start_invoc(inv_niv, snap)
                        mobs.reset()

        mx,my=pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type==pygame.QUIT:
                running=False
                _write_quit_signal()

            # Pendant l'animation des dés ou le replay IA — skip avec touche/clic
            if dice_anim.is_active() or ia_replay.is_active():
                if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                    if ia_replay.is_active():
                        ia_replay.skip()
                        dice_anim.state = DiceAnim.IDLE
                        # Lance directement les dés A si en attente
                        if _pending_a_dice and _pending_a_faces:
                            dice_anim.start(_pending_a_dice, _pending_a_faces, "A")
                            _pending_a_dice = []
                            _pending_a_faces = []
                    elif dice_anim.is_active():
                        dice_anim.state = DiceAnim.IDLE
                continue

            if event.type==pygame.KEYDOWN:
                if show_help:
                    show_help=False
                    continue
                if event.key==pygame.K_h:
                    show_help=not show_help
                    continue
                if event.key==pygame.K_ESCAPE:
                    if pause_open:
                        # ESC ferme le menu pause + lève le signal moteur
                        pause_open=False; pause_msg=""
                        _set_pause_signal(False)
                    elif invoc.mode!=InvocState.NORMAL:
                        invoc.cancel()  # annule la sélection, sans dismisser l'invoc
                    elif mobs.mode==MobsState.CAP_TARGET:
                        mobs.mode=MobsState.SELECTED
                    else:
                        # Ouvre le menu pause + signal moteur
                        pause_open=True; pause_sel=0; pause_msg=""
                        _set_pause_signal(True)
                        continue
                # Handle pause menu navigation (early-return pour bypasser le reste)
                if pause_open:
                    if event.key in (pygame.K_UP, pygame.K_w):
                        pause_sel = (pause_sel - 1) % len(pause_items)
                        pause_msg = ""
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        pause_sel = (pause_sel + 1) % len(pause_items)
                        pause_msg = ""
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        choice = pause_items[pause_sel][0]
                        if choice == "reprendre":
                            pause_open=False; pause_msg=""
                            _set_pause_signal(False)
                        elif choice == "quitter":
                            _set_pause_signal(False)  # nettoie avant quit
                            running=False
                            _write_quit_signal()
                        else:
                            pause_msg = "Cette option arrive bientot."
                    continue  # bypass autres bindings pendant pause

                # Sélection niveau de test : P = +1, O = -1 (AZERTY friendly)
                # Sélection niveau de test : O/P — uniquement en mode test (sans moteur)
                _connected = os.environ.get("DDM_GUI_CONNECTED","0") == "1"
                if not _connected:
                    if event.key==pygame.K_o:
                        invoc.test_niveau=max(1,invoc.test_niveau-1); invoc.cancel()
                    if event.key==pygame.K_p:
                        invoc.test_niveau=min(5,invoc.test_niveau+1); invoc.cancel()

                # Navigation shapes
                if invoc.mode==InvocState.SHAPE_SELECT:
                    if event.key in(pygame.K_1,pygame.K_KP1): invoc.shape_idx=0
                    if event.key in(pygame.K_2,pygame.K_KP2) and len(invoc.shapes)>1: invoc.shape_idx=1
                    if event.key in(pygame.K_3,pygame.K_KP3) and len(invoc.shapes)>2: invoc.shape_idx=2
                    if event.key in(pygame.K_4,pygame.K_KP4) and len(invoc.shapes)>3: invoc.shape_idx=3
                    if event.key==pygame.K_r:
                        invoc.rotation=(invoc.rotation+1)%4
                    if event.key==pygame.K_RETURN:
                        shape=invoc.shapes[invoc.shape_idx]
                        col_a,row_a=invoc.selected_anchor
                        valid = is_shape_valid(col_a,row_a,shape,invoc.rotation,snap,"A")
                        if valid:
                            write_command(invoc)
                            invoc.reset()
                            _invoc_dismissed = True  # empêche re-déclenchement auto
                            _invoc_cmd_log_len = len(sg(snap,"log") or [])

                # C : cap si unité sélectionnée
                if event.key==pygame.K_c:
                    if mobs.mode==MobsState.SELECTED:
                        u=_get_unit_A(snap,mobs.selected_idx)
                        if u:
                            if u.get("ability_targeted"):
                                # Capacité ciblée → mode CAP_TARGET
                                mobs.mode = MobsState.CAP_TARGET
                                mobs.cap_range = u.get("cap_range", 2)
                                mobs.cap_hov = None
                            else:
                                write_cap_command(u)
                                mobs.send_and_wait(snap)
                    elif mobs.mode==MobsState.CAP_TARGET:
                        # ESC géré ailleurs — C annule aussi
                        mobs.mode = MobsState.SELECTED
                    elif COMMAND_PATH.exists():
                        COMMAND_PATH.unlink()
                # F : fin de phase mobs — envoie end_phase et passe en WAITING
                if event.key==pygame.K_f:
                    if mobs.mode == MobsState.WAITING:
                        pass  # déjà en attente, ignore
                    elif sg(snap,"joueur_actif") == "A":
                        mobs.reset()
                        write_end_phase_command()
                        mobs.send_and_wait(snap)
                # ESC annule aussi la sélection unité
                if event.key==pygame.K_ESCAPE:
                    if mobs.mode==MobsState.SELECTED:
                        mobs.deselect()
                if event.key==pygame.K_a: sa=min(sa+1,max(0,len(ha)-4))
                if event.key==pygame.K_q: sa=max(sa-1,0)
                if event.key==pygame.K_UP: sb=min(sb+1,max(0,len(hb)-4))
                if event.key==pygame.K_DOWN: sb=max(sb-1,0)

            if event.type==pygame.MOUSEWHEEL and my >= LOG_Y:
                if mx < SCREEN_W // 2:
                    sa = max(0, min(sa - event.y, max(0, len(ha) - 4)))
                else:
                    sb = max(0, min(sb - event.y, max(0, len(hb) - 4)))

            if event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
                # Clic bouton FIN DE TOUR
                if end_turn_btn and end_turn_btn.collidepoint(mx,my):
                    if mobs.mode != MobsState.WAITING and sg(snap,"joueur_actif") == "A":
                        mobs.reset()
                        write_end_phase_command()
                        mobs.send_and_wait(snap)

                # Clic bouton INVOQUER
                elif invoc_btn_rect and invoc_btn_rect.collidepoint(mx,my):
                    if invoc.mode==InvocState.NORMAL:
                        _connected = os.environ.get("DDM_GUI_CONNECTED","0") == "1"
                        if _connected:
                            niveau = get_invoc_niveau(snap) or invoc.test_niveau
                        else:
                            niveau = invoc.test_niveau
                        invoc.start_invoc(niveau, snap)
                        _invoc_dismissed = False
                    else:
                        invoc.cancel()
                        _invoc_dismissed = True

                # Clic sur la mini map (invocation)
                elif invoc.mode==InvocState.ANCHOR_SELECT:
                    cell=mini_map_cell_at(mx,my)
                    if cell and cell in invoc.anchors:
                        invoc.select_anchor(*cell)

                # Clic sur le plateau en mode mobs
                elif invoc.mode==InvocState.NORMAL and snap:
                    if mobs.mode == MobsState.WAITING:
                        pass  # attend snapshot moteur
                    else:
                        cell=get_hov((mx,my),rd)
                        if cell:
                            col_c,row_c=cell
                            units_a=get_player(snap,"A").get("unites",[])
                            active=sg(snap,"joueur_actif")

                            if active=="A":
                                if mobs.mode==MobsState.NORMAL:
                                    # Sélection d'une unité A
                                    for i,u in enumerate(units_a):
                                        if u["col"]==col_c and u["row"]==row_c:
                                            mobs.select(i,snap)
                                            break

                                elif mobs.mode==MobsState.CAP_TARGET:
                                    u=_get_unit_A(snap,mobs.selected_idx)
                                    if u:
                                        # Confirme la cible — envoie la commande avec target
                                        write_cap_command(u, target_row=row_c, target_col=col_c)
                                        mobs.send_and_wait(snap)

                                elif mobs.mode==MobsState.SELECTED:
                                    u=_get_unit_A(snap,mobs.selected_idx)
                                    if u:
                                        # Clic sur case MOVE
                                        if (col_c,row_c) in mobs.move_cells:
                                            write_move_command(u,col_c,row_c)
                                            mobs.send_and_wait(snap)

                                        # Clic sur ennemi attaquable
                                        else:
                                            enemies_b=get_player(snap,"B").get("unites",[])
                                            found=False
                                            for ti in mobs.atk_targets:
                                                if ti<len(enemies_b):
                                                    e=enemies_b[ti]
                                                    if e["col"]==col_c and e["row"]==row_c:
                                                        write_attack_command(u,e)
                                                        mobs.send_and_wait(snap)
                                                        found=True
                                                        break
                                            # Clic sur QG ennemi attaquable
                                            if not found and mobs.qg_atk_cell:
                                                if (col_c,row_c)==mobs.qg_atk_cell:
                                                    write_attack_qg_command(u)
                                                    mobs.send_and_wait(snap)
                                                    found=True
                                            if not found:
                                                mobs.deselect()

        # Hover sur mini map
        if invoc.mode==InvocState.ANCHOR_SELECT:
            cell=mini_map_cell_at(mx,my)
            invoc.hovered_anchor=cell if cell in (invoc.anchors if invoc.anchors else []) else None

        hov=get_hov((mx,my),rd)
        if mobs.mode==MobsState.CAP_TARGET:
            mobs.cap_hov = hov

        screen.fill(C_BG)

        draw_board(screen,rd,snap,hov,hhov,invoc,mobs)
        invoc_btn_rect=draw_hud_top(screen,fonts,snap,"A",0,True,f_ps2p,invoc,dice_cache,rolled_cache)
        draw_hud_top(screen,fonts,snap,"B",SCREEN_W-HUD_W,False,f_ps2p,invoc,dice_cache,rolled_cache)
        ha2=draw_hud_units(screen,fonts,snap,"A",0)
        hb2=draw_hud_units(screen,fonts,snap,"B",SCREEN_W-HUD_W)
        hhov=ha2 or hb2
        end_turn_btn=draw_bottom(screen,fonts,snap,ha,hb,sa,sb,f_ps2p,invoc)

        screen.blit(fonts[2].render(f"FPS {int(clock.get_fps())}",True,C_BORDER),(SCREEN_W-70,SCREEN_H-20))

        # Animation lancer de dés
        if dice_anim.is_active():
            dice_anim.draw(screen, fonts)

        # Replay tour IA B
        if ia_replay.is_active():
            ia_replay.draw(screen, fonts, rd)

        # Indicateur WAITING
        if mobs.mode == MobsState.WAITING:
            wlbl = fonts[1].render("⏳ EN ATTENTE MOTEUR...", True, (255,200,0))
            screen.blit(wlbl,(HUD_W+(BOARD_W-wlbl.get_width())//2, 8))

        # (overlay debug command supprimé — était intrusif pendant le traitement normal)
        if show_help:
            draw_help_overlay(screen, fonts, f_ps2p)

        # Écran de fin de partie
        game_winner = sg(snap, "winner") if snap else None
        if not game_winner:
            pa = get_player(snap, "A") if snap else {}
            pb = get_player(snap, "B") if snap else {}
            hp_a = pa.get("qg", {}).get("hp", -1)
            hp_b = pb.get("qg", {}).get("hp", -1)
            if hp_a == 0 and hp_b == 0:
                game_winner = "draw"
            elif hp_a == 0:
                game_winner = "B"
            elif hp_b == 0:
                game_winner = "A"
        if game_winner:
            draw_game_over(screen, fonts, game_winner, snap)
            if _gameover_time is None:
                _gameover_time = time.time()
            elif time.time() - _gameover_time >= 5.0:
                _post = pathlib.Path(__file__).parent / "ddm_post_game.py"
                subprocess.Popen([sys.executable, str(_post)], env=os.environ.copy())
                running = False

        # Overlay menu pause (par dessus tout le reste)
        if pause_open:
            _draw_pause_menu(screen, fonts, pause_items, pause_sel, pause_msg)

        pygame.display.flip()
        clock.tick(FPS)

    # Nettoie le signal pause si encore présent (sécurité)
    _set_pause_signal(False)
    pygame.quit(); sys.exit()

if __name__=="__main__": main()
