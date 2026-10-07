# =============================================================================
# DDM — Menu Principal
#
# Point d'entrée GUI — Menu → Sélection Faction → Champion → Config → Jeu
#
# Usage :
#   python ddm_menu.py
# =============================================================================

import pygame, sys, os, math, json, time, random

# =============================================================================
# CHEMINS
# =============================================================================
_DDM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH       = os.path.join(_DDM_ROOT, "assets", "PressStart2P-Regular.ttf")
FACTIONS_JSON   = os.path.join(_DDM_ROOT, "data", "Data_8_Factions.json")
SPRITES_ROOT    = os.path.join(_DDM_ROOT, "assets", "sprites")
ENGINE_DIR      = _DDM_ROOT
RENDERER_PATH   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ddm_renderer.py")

def _load_agent_prefs(agent_name):
    """Charge faction_id + champion_letter depuis data/<agent>_prefs.json.
    Retourne (faction_id, champion_letter) ou (None, None) si absent/invalide."""
    path = os.path.join(ENGINE_DIR, "data", f"{agent_name}_prefs.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        pref = d.get("preferred", {})
        fac = pref.get("faction")
        champ = pref.get("champion")
        if fac is not None and champ:
            return int(fac), str(champ).upper()
    except Exception:
        pass
    return None, None
import subprocess

# =============================================================================
# CONSTANTES ÉCRAN
# =============================================================================
SCREEN_W, SCREEN_H = 1920, 1080
FPS = 60

# =============================================================================
# PALETTE
# =============================================================================
C_BG_TOP      = (18, 14, 32)
C_BG_BOT      = (42, 38, 52)
C_BRICK_TOP   = [(22, 18, 36), (26, 22, 40), (20, 16, 34), (24, 20, 38)]
C_BRICK_BOT   = [(48, 44, 56), (52, 48, 60), (44, 40, 54), (55, 50, 62)]
C_MORTAR      = (14, 10, 24)
C_MORTAR_BOT  = (32, 28, 40)

C_BANNER_TOP  = (170, 40, 28)
C_BANNER_MID  = (150, 32, 24)
C_BANNER_BOT  = (125, 25, 20)
C_BANNER_EDGE = (190, 110, 45)
C_LAVA_DRIP   = (160, 35, 22)

C_TITLE       = (200, 160, 50)
C_TITLE_SHADOW= (80, 60, 15)

C_MENU_BG     = (20, 24, 55)
C_MENU_BORDER = (200, 160, 50)
C_SEL         = (230, 190, 55)
C_UNSEL       = (115, 105, 130)
C_HINT        = (170, 140, 55)
C_VERSION     = (80, 72, 95)

C_BOARD_LIGHT = (44, 40, 55)
C_BOARD_DARK  = (30, 26, 40)
C_BOARD_EDGE  = (55, 50, 65)
C_QG_MARKER   = (200, 165, 55)

C_DIE_BLUE_L  = (65, 100, 210)
C_DIE_BLUE_M  = (40, 65, 170)
C_DIE_BLUE_D  = (25, 40, 120)
C_DIE_PURP_L  = (100, 60, 160)
C_DIE_PURP_M  = (70, 40, 130)
C_DIE_PURP_D  = (45, 25, 90)
C_DIE_WHT_L   = (220, 220, 230)
C_DIE_WHT_M   = (180, 180, 195)
C_DIE_WHT_D   = (130, 130, 145)

# =============================================================================
# BACKGROUND
# =============================================================================
_bg_surface = None

def draw_background(screen):
    global _bg_surface
    if _bg_surface is not None:
        screen.blit(_bg_surface, (0, 0))
        return

    _bg_surface = pygame.Surface((SCREEN_W, SCREEN_H))
    rng = random.Random(42)
    _bg_surface.fill(C_BG_TOP)

    brick_h, brick_w = 40, 96
    transition_y = SCREEN_H * 0.48

    for row in range(SCREEN_H // brick_h + 1):
        offset = (brick_w // 2) if row % 2 else 0
        y = row * brick_h
        ratio = min(1.0, max(0.0, (y - transition_y * 0.7) / (transition_y * 0.6)))
        mort = tuple(int(C_MORTAR[i] + (C_MORTAR_BOT[i] - C_MORTAR[i]) * ratio) for i in range(3))

        for col in range(-1, SCREEN_W // brick_w + 2):
            x = col * brick_w + offset
            base = rng.choice(C_BRICK_BOT if ratio > 0.5 else C_BRICK_TOP)
            v = rng.randint(-6, 6)
            fill = tuple(max(0, min(255, base[i]+v)) for i in range(3))
            pygame.draw.rect(_bg_surface, mort, (x, y, brick_w, brick_h))
            pygame.draw.rect(_bg_surface, fill, (x+2, y+2, brick_w-3, brick_h-3))
            if rng.random() > 0.6:
                lighter = tuple(min(255, c+8) for c in fill)
                pygame.draw.rect(_bg_surface, lighter, (x+4, y+4, brick_w//3, brick_h//3))

    screen.blit(_bg_surface, (0, 0))


# =============================================================================
# BANNIÈRE + TITRE
# =============================================================================
def draw_banner(screen, f_title, t):
    bh = 120
    for y in range(bh):
        r = y / bh
        if r < 0.35:
            r2 = r / 0.35
            c = [int(C_BANNER_TOP[i]+(C_BANNER_MID[i]-C_BANNER_TOP[i])*r2) for i in range(3)]
        else:
            r2 = (r - 0.35) / 0.65
            c = [int(C_BANNER_MID[i]+(C_BANNER_BOT[i]-C_BANNER_MID[i])*r2) for i in range(3)]
        pygame.draw.line(screen, c, (0, y), (SCREEN_W, y))

    for ey in [6, 10, bh-8, bh-5]:
        pts = [(x, ey + math.sin(x*0.013+t*0.4+ey)*2.5) for x in range(0, SCREEN_W, 3)]
        if len(pts) > 2:
            pygame.draw.lines(screen, C_BANNER_EDGE, False, pts, 1)

    for i in range(15):
        dx = 80 + i*128 + int(20*math.sin(i*2.1))
        dh = int(6 + 10*math.sin(t*0.7+i*1.9))
        for dy in range(dh):
            bright = max(0, 200-dy*20)
            c = (min(255, C_LAVA_DRIP[0]+bright//4), C_LAVA_DRIP[1], C_LAVA_DRIP[2])
            w = max(1, 3-dy//4)
            pygame.draw.line(screen, c, (dx, bh+dy), (dx+w, bh+dy))

    title_text = "DUNGEON  DICE  MONSTERS"
    shadow = f_title.render(title_text, True, C_TITLE_SHADOW)
    title  = f_title.render(title_text, True, C_TITLE)
    tx = (SCREEN_W - title.get_width()) // 2
    ty = (bh - title.get_height()) // 2
    screen.blit(shadow, (tx+3, ty+3))
    screen.blit(title, (tx, ty))


# =============================================================================
# MINI PLATEAU
# =============================================================================
def draw_mini_board(screen):
    cols, rows = 7, 11
    cell = 32
    bw, bh2 = cols*cell, rows*cell
    bx = (SCREEN_W - bw)//2 + 10
    by = 162
    pygame.draw.rect(screen, (18,15,28), (bx-4, by-4, bw+8, bh2+8))
    pygame.draw.rect(screen, C_BOARD_EDGE, (bx-4, by-4, bw+8, bh2+8), 1)
    for r in range(rows):
        for c in range(cols):
            fill = C_BOARD_LIGHT if (r+c)%2==0 else C_BOARD_DARK
            pygame.draw.rect(screen, fill, (bx+c*cell, by+r*cell, cell, cell))
    mk = 8
    qx = bx + (cols//2)*cell + cell//2 - mk//2
    pygame.draw.rect(screen, C_QG_MARKER, (qx, by+cell//2-mk//2, mk, mk), 1)
    pygame.draw.rect(screen, C_QG_MARKER, (qx, by+(rows-1)*cell+cell//2-mk//2, mk, mk), 1)


# =============================================================================
# DÉS ISOMÉTRIQUES
# =============================================================================
def _draw_die_symbol(screen, sym, cx, cy, sz, col):
    if sym == "arrow_down":
        pygame.draw.line(screen, col, (cx, cy-sz), (cx, cy+sz), 2)
        pygame.draw.line(screen, col, (cx-sz, cy+1), (cx, cy+sz), 2)
        pygame.draw.line(screen, col, (cx+sz, cy+1), (cx, cy+sz), 2)
    elif sym == "diamond":
        pts = [(cx, cy-sz), (cx+sz, cy), (cx, cy+sz), (cx-sz, cy)]
        pygame.draw.polygon(screen, col, pts, 2)
    elif sym == "star":
        pts = []
        for i in range(5):
            a = math.pi/2 + i*2*math.pi/5
            pts.append((cx+int(sz*math.cos(a)), cy-int(sz*math.sin(a))))
            a2 = a + math.pi/5
            pts.append((cx+int(sz//2*math.cos(a2)), cy-int(sz//2*math.sin(a2))))
        pygame.draw.polygon(screen, col, pts, 1)
    elif sym == "bolt":
        pts = [(cx-sz//2, cy-sz), (cx+sz//3, cy-sz//4), (cx-sz//4, cy), (cx+sz//2, cy+sz)]
        pygame.draw.lines(screen, col, False, pts, 2)
    elif sym == "arrow_right":
        pygame.draw.line(screen, col, (cx-sz, cy), (cx+sz, cy), 2)
        pygame.draw.line(screen, col, (cx+1, cy-sz), (cx+sz, cy), 2)
        pygame.draw.line(screen, col, (cx+1, cy+sz), (cx+sz, cy), 2)


def _draw_iso_die(screen, cx, cy, sz, col_t, col_l, col_r, syms, t_off, t):
    bob = int(4*math.sin(t*1.0+t_off))
    cy += bob
    hw = sz//2
    hh = sz//3

    top    = (cx, cy - sz//2)
    left   = (cx - hw, cy - sz//2 + hh)
    right  = (cx + hw, cy - sz//2 + hh)
    center = (cx, cy - sz//2 + hh*2)
    bot_l  = (cx - hw, cy + sz//2)
    bot_r  = (cx + hw, cy + sz//2)
    bottom = (cx, cy + sz//2 + hh)

    # Ombre au sol
    ov = pygame.Surface((sz+20, 12), pygame.SRCALPHA)
    pygame.draw.ellipse(ov, (0,0,0,50), (0,0,sz+20,12))
    screen.blit(ov, (cx-sz//2-10, cy+sz//2+hh-2))

    # 3 faces
    top_pts = [top, right, center, left]
    left_pts = [left, center, bottom, bot_l]
    right_pts = [right, bot_r, bottom, center]

    pygame.draw.polygon(screen, col_t, top_pts)
    pygame.draw.polygon(screen, col_l, left_pts)
    pygame.draw.polygon(screen, col_r, right_pts)
    pygame.draw.polygon(screen, (0,0,0), top_pts, 2)
    pygame.draw.polygon(screen, (0,0,0), left_pts, 2)
    pygame.draw.polygon(screen, (0,0,0), right_pts, 2)

    # Symboles
    sym_col = (0,0,0) if col_t[0] > 150 else (220,220,240)
    ssz = max(7, sz//7)

    tcx = sum(p[0] for p in top_pts)//4
    tcy = sum(p[1] for p in top_pts)//4
    _draw_die_symbol(screen, syms[0], tcx, tcy, ssz, sym_col)

    lcx = sum(p[0] for p in left_pts)//4
    lcy = sum(p[1] for p in left_pts)//4
    _draw_die_symbol(screen, syms[1], lcx, lcy, ssz, sym_col)

    rcx = sum(p[0] for p in right_pts)//4
    rcy = sum(p[1] for p in right_pts)//4
    _draw_die_symbol(screen, syms[2], rcx, rcy, ssz, sym_col)


def draw_deco_dice(screen, t):
    bx, by = 1050, 650
    _draw_iso_die(screen, bx-30, by-15, 105,
                  C_DIE_BLUE_L, C_DIE_BLUE_D, C_DIE_BLUE_M,
                  ["arrow_down", "star", "diamond"], 0, t)
    _draw_iso_die(screen, bx+68, by-30, 88,
                  C_DIE_PURP_L, C_DIE_PURP_D, C_DIE_PURP_M,
                  ["arrow_down", "bolt", "star"], 2.0, t)
    _draw_iso_die(screen, bx+160, by-22, 98,
                  C_DIE_WHT_L, C_DIE_WHT_D, C_DIE_WHT_M,
                  ["star", "bolt", "arrow_right"], 4.0, t)


# =============================================================================
# MENU BOX
# =============================================================================
MENU_ENTRIES = [
    ("NOUVELLE PARTIE", "new_game"),
    ("TOURNOI",         "tournament"),
    ("ENCYCLOPEDIE",    "encyclopedia"),
    ("CHARGER PARTIE",  "load_game"),
    ("OPTIONS",         "options"),
    ("QUITTER",         "quit"),
]

def draw_menu_box(screen, f_menu, sel, t):
    bw, bh2 = 350, len(MENU_ENTRIES)*46+36
    bx = SCREEN_W//2 - bw//2 - 90
    by = 560
    pygame.draw.rect(screen, C_MENU_BG, (bx, by, bw, bh2))
    pygame.draw.rect(screen, C_MENU_BORDER, (bx, by, bw, bh2), 2)
    pygame.draw.rect(screen, C_MENU_BORDER, (bx+5, by+5, bw-10, bh2-10), 1)

    for i, (label, _) in enumerate(MENU_ENTRIES):
        y = by + 22 + i*46
        x = bx + 28
        if i == sel:
            hl = pygame.Surface((bw-14, 32), pygame.SRCALPHA)
            hl.fill((200,160,50,30))
            screen.blit(hl, (bx+7, y-4))
            pulse = int(4*math.sin(t*5))
            cur = f_menu.render("\u25ba", True, C_SEL)
            screen.blit(cur, (x-2+pulse//2, y+1))
            screen.blit(f_menu.render(label, True, C_SEL), (x+24, y))
        else:
            screen.blit(f_menu.render(label, True, C_UNSEL), (x+24, y))
    return bx, by, bw, bh2


# =============================================================================
# DATA — chargement factions
# =============================================================================
_factions_data = None

def load_factions():
    global _factions_data
    if _factions_data is not None:
        return _factions_data
    try:
        with open(FACTIONS_JSON, "r", encoding="utf-8") as f:
            _factions_data = json.load(f).get("factions", [])
    except Exception as e:
        print(f"[MENU] Erreur chargement factions : {e}")
        _factions_data = []
    return _factions_data


import unicodedata, re as _re

def _slug(t):
    t = t.lower().strip()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return _re.sub(r"[^a-z0-9]+", "_", t).strip("_")

def _fac_slug(nom):
    part = nom.split("\u2013")[0].split("-")[0].strip()
    return _slug(part)


# =============================================================================
# SPRITES — chargement avec cache
# =============================================================================
_sprite_cache = {}

def _load_sprite(path, tw, th):
    key = f"{path}_{tw}_{th}"
    if key in _sprite_cache:
        return _sprite_cache[key]
    if not os.path.isfile(path):
        _sprite_cache[key] = None
        return None
    try:
        src = pygame.image.load(path).convert_alpha()
        sw, sh = src.get_size()
        r = min((tw * 0.92) / sw, (th * 0.92) / sh)
        s = pygame.transform.scale(src, (max(1, int(sw*r)), max(1, int(sh*r))))
        _sprite_cache[key] = s
        return s
    except:
        _sprite_cache[key] = None
        return None


def _find_champion_sprite(fac_s, lettre, nom):
    fac_dir = os.path.join(SPRITES_ROOT, fac_s)
    if not os.path.isdir(fac_dir):
        return None
    slug_nom = _slug(nom)
    target = f"{fac_s}_champion_{lettre.lower()}_{slug_nom}.png"
    path = os.path.join(fac_dir, target)
    if os.path.isfile(path):
        return path
    # Fallback: cherche un fichier champion avec la bonne lettre
    for fname in os.listdir(fac_dir):
        if f"champion_{lettre.lower()}" in fname:
            return os.path.join(fac_dir, fname)
    return None


def _find_unit_sprite(fac_s, niveau, nom):
    fac_dir = os.path.join(SPRITES_ROOT, fac_s)
    if not os.path.isdir(fac_dir):
        return None
    slug_nom = _slug(nom)
    target = f"{fac_s}_lv{niveau}_{slug_nom}.png"
    path = os.path.join(fac_dir, target)
    if os.path.isfile(path):
        return path
    return None


# =============================================================================
# COULEURS FACTION — accent couleur par faction
# =============================================================================
FACTION_COLORS = {
    1: (80, 130, 220),   # Humains — bleu
    2: (180, 50, 80),    # Démons — rouge sombre
    3: (60, 180, 80),    # Reptiliens — vert
    4: (100, 200, 220),  # Cyborgs — cyan
    5: (180, 120, 50),   # Orcs — orange
    6: (140, 100, 200),  # Lycans — violet
    7: (220, 180, 50),   # Égypte — doré
    8: (160, 60, 200),   # Abominations — magenta
}

# =============================================================================
# FONDS FACTION — procéduraux, cachés après 1er rendu
# =============================================================================
_faction_bg_cache = {}

def draw_faction_bg(screen, faction_id, rect=None):
    """Dessine le fond thématique de la faction.
    Si rect=(x,y,w,h) est fourni, dessine uniquement dans cette zone.
    Caché après 1er rendu (par faction_id + rect size).
    """
    key = (faction_id, rect[2] if rect else SCREEN_W, rect[3] if rect else SCREEN_H)
    if key in _faction_bg_cache:
        pos = (rect[0], rect[1]) if rect else (0, 0)
        screen.blit(_faction_bg_cache[key], pos)
        return

    w = rect[2] if rect else SCREEN_W
    h = rect[3] if rect else SCREEN_H
    surf = pygame.Surface((w, h))
    rng = random.Random(faction_id * 1337)

    # Override temporaire des dimensions pour les fonctions de dessin
    global _bg_w, _bg_h
    _bg_w, _bg_h = w, h

    builders = {
        1: _bg_humains, 2: _bg_demons, 3: _bg_reptiliens, 4: _bg_cyborgs,
        5: _bg_orcs, 6: _bg_lycans, 7: _bg_egypte, 8: _bg_abominations,
    }
    fn = builders.get(faction_id, _bg_default)
    fn(surf, rng)

    _bg_w, _bg_h = SCREEN_W, SCREEN_H  # restaure

    _faction_bg_cache[key] = surf
    pos = (rect[0], rect[1]) if rect else (0, 0)
    screen.blit(surf, pos)

# Dimensions courantes pour les bg builders
_bg_w, _bg_h = SCREEN_W, SCREEN_H


def _vline(surf, col, x, y1, y2, w=1):
    pygame.draw.line(surf, col, (x, y1), (x, y2), w)

def _gradient_fill(surf, c_top, c_bot):
    w, h = surf.get_size()
    for y in range(h):
        r = y / h
        c = [int(c_top[i] + (c_bot[i] - c_top[i]) * r) for i in range(3)]
        pygame.draw.line(surf, c, (0, y), (w, y))

def _overlay(surf, color_alpha, rect=None):
    w, h = surf.get_size()
    r = rect or (0, 0, w, h)
    ov = pygame.Surface((r[2], r[3]), pygame.SRCALPHA)
    ov.fill(color_alpha)
    surf.blit(ov, (r[0], r[1]))


# --- 1. Humains — bleu acier, or, remparts ---
def _bg_humains(surf, rng):
    _gradient_fill(surf, (12, 16, 30), (8, 10, 22))

    # Remparts silhouettes en bas
    for i in range(8):
        bx = i * 260 - 40 + rng.randint(-20, 20)
        bw = rng.randint(100, 160)
        bh = rng.randint(180, 320)
        by = _bg_h - bh
        _overlay(surf, (30, 50, 90, 25), (bx, by, bw, bh))
        # Créneaux
        for cx in range(bx, bx + bw, 28):
            _overlay(surf, (35, 55, 95, 30), (cx, by - 16, 18, 16))

    # Runes hexagonales discrètes — batch
    rune_ov = pygame.Surface((_bg_w, _bg_h), pygame.SRCALPHA)
    for _ in range(25):
        cx = rng.randint(0, _bg_w)
        cy = rng.randint(0, _bg_h)
        sz = rng.randint(20, 50)
        pts = [(cx + int(sz * math.cos(math.pi/3*i)), cy + int(sz * math.sin(math.pi/3*i))) for i in range(6)]
        pygame.draw.polygon(rune_ov, (50, 80, 150, 15), pts, 1)
    surf.blit(rune_ov, (0, 0))

    # Lignes techno-runiques verticales
    for _ in range(12):
        x = rng.randint(50, _bg_w - 50)
        y1 = rng.randint(200, 500)
        y2 = rng.randint(y1 + 100, _bg_h)
        _overlay(surf, (60, 100, 180, 12), (x, y1, 2, y2 - y1))
        # Petits ticks
        for ty in range(y1, y2, rng.randint(20, 40)):
            _overlay(surf, (80, 130, 200, 18), (x - 4, ty, 10, 1))

    # Lueur dorée du QG (centre bas)
    for r in range(200, 0, -2):
        alpha = max(0, int(8 * (1 - r / 200)))
        ov = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
        pygame.draw.circle(ov, (200, 165, 50, alpha), (r, r), r)
        surf.blit(ov, (_bg_w//2 - r, _bg_h - r - 30))


# --- 2. Démons — violet, noir, rouge sombre ---
def _bg_demons(surf, rng):
    _gradient_fill(surf, (18, 8, 18), (10, 4, 12))

    # Grande rune circulaire en bas — batch
    demon_ov = pygame.Surface((_bg_w, _bg_h), pygame.SRCALPHA)
    cx, cy = _bg_w // 2, _bg_h - 80
    for r in [250, 220, 180, 140]:
        pygame.draw.circle(demon_ov, (120, 30, 60, 18), (cx, cy), r, 2)
    for i in range(12):
        a = i * math.pi * 2 / 12
        px = cx + int(200 * math.cos(a))
        py = cy + int(200 * math.sin(a))
        pygame.draw.rect(demon_ov, (150, 40, 70, 20), (px - 3, py - 3, 6, 6))
    surf.blit(demon_ov, (0, 0))

    # Flammes violettes montantes
    flame_ov = pygame.Surface((_bg_w, _bg_h), pygame.SRCALPHA)
    for _ in range(30):
        fx = rng.randint(0, _bg_w)
        fy = rng.randint(_bg_h // 2, _bg_h)
        fh = rng.randint(40, 150)
        fw = rng.randint(3, 8)
        for dy in range(fh):
            alpha = max(0, int(18 * (1 - dy / fh)))
            pygame.draw.rect(flame_ov, (120, 30, 100, alpha), (fx - fw//2, fy - dy, fw, 1))
    surf.blit(flame_ov, (0, 0))

    # Chaînes brisées diagonales — batch
    chain_ov = pygame.Surface((_bg_w, _bg_h), pygame.SRCALPHA)
    for _ in range(8):
        sx = rng.randint(0, _bg_w)
        sy = rng.randint(0, _bg_h)
        angle = rng.uniform(-0.8, 0.8)
        length = rng.randint(100, 300)
        for d in range(0, length, 12):
            px = sx + int(d * math.cos(angle))
            py = sy + int(d * math.sin(angle))
            pygame.draw.rect(chain_ov, (100, 40, 50, 15), (px, py, 4, 8))
    surf.blit(chain_ov, (0, 0))

    # Silhouettes de cornes dans les coins — batch
    horn_ov = pygame.Surface((_bg_w, _bg_h), pygame.SRCALPHA)
    for corner_x, flip in [(80, 1), (_bg_w - 80, -1)]:
        for i in range(30):
            t = i / 30
            px = corner_x + flip * int(40 * t * t)
            py = int(60 + 200 * t)
            pygame.draw.rect(horn_ov, (80, 20, 40, 10), (px, py, 5, 3))
    surf.blit(horn_ov, (0, 0))


# --- 3. Reptiliens — vert toxique, ocre, napalm ---
def _bg_reptiliens(surf, rng):
    _gradient_fill(surf, (14, 18, 10), (10, 14, 8))

    # Horizon désertique abstrait
    horizon_y = _bg_h * 0.45
    for y in range(int(horizon_y), _bg_h):
        r = (y - horizon_y) / (_bg_h - horizon_y)
        c = (int(18 + 12 * r), int(16 + 8 * r), int(8 + 4 * r))
        pygame.draw.line(surf, c, (0, y), (_bg_w, y))

    # Écailles géométriques (losanges en grille) — batch
    scale_ov = pygame.Surface((_bg_w, _bg_h), pygame.SRCALPHA)
    for row in range(0, _bg_h, 40):
        off = 20 if (row // 40) % 2 else 0
        for col in range(-20, _bg_w + 20, 40):
            cx, cy = col + off, row
            pts = [(cx, cy - 18), (cx + 18, cy), (cx, cy + 18), (cx - 18, cy)]
            pygame.draw.polygon(scale_ov, (40, 100, 45, 8), pts, 1)
    surf.blit(scale_ov, (0, 0))

    # Arcs de trajectoire de bombardement
    for _ in range(6):
        sx = rng.randint(100, _bg_w - 100)
        sy = rng.randint(int(horizon_y), _bg_h - 100)
        dx = rng.randint(-300, 300)
        for t in range(40):
            tt = t / 40
            px = sx + int(dx * tt)
            py = sy - int(120 * math.sin(math.pi * tt))
            _overlay(surf, (180, 60, 30, 12), (px, py, 2, 2))
        # Impact
        ix = sx + dx
        iy = sy
        for r in range(25, 0, -1):
            alpha = max(0, int(10 * (1 - r / 25)))
            ov = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
            pygame.draw.circle(ov, (180, 70, 30, alpha), (r, r), r)
            surf.blit(ov, (ix - r, iy - r))

    # Brume verdâtre en bas
    for y in range(_bg_h - 120, _bg_h):
        alpha = int(20 * ((y - (_bg_h - 120)) / 120))
        _overlay(surf, (40, 140, 50, alpha), (0, y, _bg_w, 1))


# --- 4. Cyborgs — cyan, gris froid, circuits ---
def _bg_cyborgs(surf, rng):
    _gradient_fill(surf, (10, 14, 20), (6, 10, 16))

    # Grille hexagonale de fond — batch sur une seule surface alpha
    hex_ov = pygame.Surface((_bg_w, _bg_h), pygame.SRCALPHA)
    hex_sz = 35
    for row in range(-1, _bg_h // (hex_sz * 2) + 2):
        for col in range(-1, _bg_w // (hex_sz * 2) + 2):
            off = hex_sz if row % 2 else 0
            cx = col * hex_sz * 2 + off
            cy = row * int(hex_sz * 1.7)
            pts = [(cx + int(hex_sz * 0.9 * math.cos(math.pi/3*i)),
                    cy + int(hex_sz * 0.9 * math.sin(math.pi/3*i))) for i in range(6)]
            pygame.draw.polygon(hex_ov, (40, 90, 110, 10), pts, 1)
    surf.blit(hex_ov, (0, 0))

    # Nodes connectés — batch
    node_ov = pygame.Surface((_bg_w, _bg_h), pygame.SRCALPHA)
    nodes = [(rng.randint(50, _bg_w-50), rng.randint(50, _bg_h-50)) for _ in range(20)]
    for i, (nx, ny) in enumerate(nodes):
        pygame.draw.circle(node_ov, (60, 180, 200, 25), (nx, ny), 6)
        pygame.draw.circle(node_ov, (80, 200, 220, 35), (nx, ny), 3)
        for j, (nx2, ny2) in enumerate(nodes):
            if i < j and math.hypot(nx2-nx, ny2-ny) < 300:
                pygame.draw.line(node_ov, (50, 160, 180, 10), (nx, ny), (nx2, ny2), 1)
    surf.blit(node_ov, (0, 0))

    # Rectangles translucides (tuiles reconfigurées)
    for _ in range(10):
        rx = rng.randint(0, _bg_w - 120)
        ry = rng.randint(0, _bg_h - 80)
        rw = rng.randint(60, 120)
        rh = rng.randint(40, 80)
        _overlay(surf, (40, 100, 120, 8), (rx, ry, rw, rh))
        _overlay(surf, (60, 140, 160, 12), (rx, ry, rw, 1))


# --- 5. Orcs — rouille, brun métal, plaques rivetées ---
def _bg_orcs(surf, rng):
    _gradient_fill(surf, (18, 12, 8), (12, 8, 6))

    # Grande plaque de métal cabossée
    plate_x = _bg_w // 2 - 400
    plate_y = 100
    plate_w = 800
    plate_h = _bg_h - 200
    _overlay(surf, (40, 28, 18, 30), (plate_x, plate_y, plate_w, plate_h))
    _overlay(surf, (60, 40, 25, 20), (plate_x, plate_y, plate_w, 3))
    _overlay(surf, (30, 20, 12, 20), (plate_x, plate_y + plate_h - 3, plate_w, 3))

    # Rivets
    for rx in range(plate_x + 15, plate_x + plate_w, 50):
        for ry in [plate_y + 12, plate_y + plate_h - 12]:
            ov = pygame.Surface((10, 10), pygame.SRCALPHA)
            pygame.draw.circle(ov, (80, 55, 35, 30), (5, 5), 4)
            pygame.draw.circle(ov, (50, 35, 22, 25), (5, 5), 2)
            surf.blit(ov, (rx - 5, ry - 5))

    # Bosses/cabosses
    for _ in range(15):
        bx = rng.randint(plate_x + 30, plate_x + plate_w - 30)
        by = rng.randint(plate_y + 30, plate_y + plate_h - 30)
        br = rng.randint(15, 50)
        ov = pygame.Surface((br*2, br*2), pygame.SRCALPHA)
        pygame.draw.circle(ov, (50, 35, 22, 12), (br, br), br)
        pygame.draw.circle(ov, (65, 45, 28, 8), (br - 3, br - 3), br - 4, 1)
        surf.blit(ov, (bx - br, by - br))

    # Totem stylisé (centre)
    tx = _bg_w // 2
    ty = _bg_h // 2 - 60
    for i in range(8):
        tw = 40 - i * 3
        th = 30
        _overlay(surf, (70, 45, 25, 18), (tx - tw//2, ty + i * 32, tw, th))
        # Yeux du totem
        if i in [1, 3, 5]:
            _overlay(surf, (180, 80, 30, 20), (tx - 10, ty + i * 32 + 10, 6, 6))
            _overlay(surf, (180, 80, 30, 20), (tx + 4, ty + i * 32 + 10, 6, 6))

    # Étincelles
    for _ in range(40):
        ex = rng.randint(plate_x, plate_x + plate_w)
        ey = rng.randint(plate_y, plate_y + plate_h)
        _overlay(surf, (220, 160, 60, rng.randint(8, 20)), (ex, ey, 2, 2))


# --- 6. Lycans — bleu nuit, argent, forêt nocturne ---
def _bg_lycans(surf, rng):
    _gradient_fill(surf, (8, 10, 24), (6, 8, 18))

    # Grande lune décentrée — batch glow
    moon_x, moon_y = _bg_w * 3 // 4, 160
    moon_ov = pygame.Surface((_bg_w, _bg_h), pygame.SRCALPHA)
    for r in range(120, 0, -4):
        alpha = max(0, int(25 * (1 - r / 120)))
        pygame.draw.circle(moon_ov, (180, 190, 220, alpha), (moon_x, moon_y), r)
    # Disque lunaire croissant
    pygame.draw.circle(moon_ov, (200, 210, 230, 40), (moon_x, moon_y), 45)
    pygame.draw.circle(moon_ov, (8, 10, 24, 200), (moon_x + 15, moon_y - 5), 38)
    surf.blit(moon_ov, (0, 0))

    # Silhouettes de pins + griffures — batch
    tree_ov = pygame.Surface((_bg_w, _bg_h), pygame.SRCALPHA)
    for _ in range(25):
        tx = rng.randint(0, _bg_w)
        th = rng.randint(80, 220)
        tw = rng.randint(25, 60)
        ty = _bg_h - rng.randint(0, 200)
        pygame.draw.rect(tree_ov, (15, 18, 30, 20), (tx - 3, ty - th//3, 6, th//3))
        for layer in range(3):
            ly = ty - th + layer * th // 4
            lw = tw - layer * 8
            pts = [(tx, ly), (tx - lw, ly + th//4), (tx + lw, ly + th//4)]
            pygame.draw.polygon(tree_ov, (12, 20, 32, 18), pts)
    surf.blit(tree_ov, (0, 0))

    # Griffures diagonales — batch
    claw_ov = pygame.Surface((_bg_w, _bg_h), pygame.SRCALPHA)
    for _ in range(12):
        sx = rng.randint(0, _bg_w)
        sy = rng.randint(0, _bg_h)
        for claw in range(3):
            offset = claw * 12
            length = rng.randint(60, 180)
            ex = sx + int(length * 0.7) + offset
            ey = sy + length + offset
            pygame.draw.line(claw_ov, (100, 110, 150, 12), (sx + offset, sy + offset), (ex, ey), 2)
    surf.blit(claw_ov, (0, 0))

    # Brume basse argentée
    for y in range(_bg_h - 80, _bg_h):
        alpha = int(12 * ((y - (_bg_h - 80)) / 80))
        _overlay(surf, (100, 110, 140, alpha), (0, y, _bg_w, 1))


# --- 7. Égypte — or, beige, turquoise, temple ---
def _bg_egypte(surf, rng):
    _gradient_fill(surf, (18, 16, 10), (14, 12, 8))

    # Disque solaire en haut
    sun_x, sun_y = _bg_w // 2, 50
    for r in range(180, 0, -2):
        alpha = max(0, int(12 * (1 - r / 180)))
        ov = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
        pygame.draw.circle(ov, (220, 180, 50, alpha), (r, r), r)
        surf.blit(ov, (sun_x - r, sun_y - r))

    # Mur de temple — briques sable
    for row in range(_bg_h // 36 + 1):
        off = 20 if row % 2 else 0
        y = row * 36
        for col in range(-1, _bg_w // 72 + 2):
            x = col * 72 + off
            shade = rng.randint(-3, 3)
            c = (22 + shade, 20 + shade, 12 + shade)
            pygame.draw.rect(surf, c, (x + 1, y + 1, 70, 34))

    # Frises hiéroglyphiques horizontales
    for band_y in [180, _bg_h - 160]:
        _overlay(surf, (180, 150, 40, 15), (0, band_y, _bg_w, 24))
        # Petits symboles
        for sx in range(0, _bg_w, 30):
            sym = rng.choice(["rect", "circle", "tri", "line"])
            sc = (200, 170, 50, 18)
            ov = pygame.Surface((24, 20), pygame.SRCALPHA)
            if sym == "rect":
                pygame.draw.rect(ov, sc, (4, 2, 12, 16), 1)
            elif sym == "circle":
                pygame.draw.circle(ov, sc, (12, 10), 7, 1)
            elif sym == "tri":
                pygame.draw.polygon(ov, sc, [(12, 2), (4, 16), (20, 16)], 1)
            else:
                pygame.draw.line(ov, sc, (4, 10), (20, 10), 1)
                pygame.draw.line(ov, sc, (12, 2), (12, 18), 1)
            surf.blit(ov, (sx, band_y + 2))

    # Obélisques — batch
    obel_ov = pygame.Surface((_bg_w, _bg_h), pygame.SRCALPHA)
    for ox in [180, _bg_w - 200]:
        oh = 350
        ow = 22
        pygame.draw.rect(obel_ov, (40, 35, 22, 25), (ox, _bg_h - oh, ow, oh))
        pygame.draw.polygon(obel_ov, (200, 170, 50, 20),
                            [(ox, _bg_h - oh), (ox + ow, _bg_h - oh),
                             (ox + ow//2, _bg_h - oh - 20)])
    surf.blit(obel_ov, (0, 0))

    # Lignes hiéroglyphiques lumineuses qui s'effacent
    for _ in range(20):
        lx = rng.randint(100, _bg_w - 100)
        ly = rng.randint(200, _bg_h - 200)
        ll = rng.randint(40, 120)
        for d in range(ll):
            alpha = max(0, int(15 * (1 - d / ll)))
            _overlay(surf, (200, 170, 50, alpha), (lx + d, ly, 1, 1))


# --- 8. Abominations — cyan, magenta, glitches, fractal ---
def _bg_abominations(surf, rng):
    _gradient_fill(surf, (8, 4, 14), (4, 2, 10))

    # Grand fractal géométrique central (Sierpinski-like) — batch
    frac_ov = pygame.Surface((_bg_w, _bg_h), pygame.SRCALPHA)

    def _sierpinski(cx, cy, sz, depth):
        if depth <= 0 or sz < 8:
            return
        pts = [(cx, cy - sz), (cx - int(sz*0.86), cy + sz//2), (cx + int(sz*0.86), cy + sz//2)]
        col = (100, 40, 160, 12) if depth % 2 else (40, 160, 180, 10)
        pygame.draw.polygon(frac_ov, col, pts, 1)
        nsz = sz // 2
        _sierpinski(cx, cy - nsz, nsz, depth - 1)
        _sierpinski(cx - int(nsz*0.86), cy + nsz//2, nsz, depth - 1)
        _sierpinski(cx + int(nsz*0.86), cy + nsz//2, nsz, depth - 1)

    _sierpinski(_bg_w//2, _bg_h//2 - 50, 300, 4)

    # Polygones impossibles flottants
    for _ in range(15):
        px = rng.randint(50, _bg_w - 50)
        py = rng.randint(50, _bg_h - 50)
        sides = rng.choice([3, 4, 5, 6, 7])
        sz = rng.randint(20, 70)
        rot = rng.uniform(0, math.pi * 2)
        pts = [(px + int(sz * math.cos(rot + i * 2 * math.pi / sides)),
                py + int(sz * math.sin(rot + i * 2 * math.pi / sides))) for i in range(sides)]
        col = rng.choice([(60, 180, 200, 12), (180, 50, 180, 12), (120, 60, 200, 10)])
        pygame.draw.polygon(frac_ov, col, pts, 1)
    surf.blit(frac_ov, (0, 0))

    # Scanlines
    scan_ov = pygame.Surface((_bg_w, _bg_h), pygame.SRCALPHA)
    for y in range(0, _bg_h, 3):
        pygame.draw.line(scan_ov, (0, 0, 0, 8), (0, y), (_bg_w, y))
    surf.blit(scan_ov, (0, 0))

    # Bandes "bug" horizontales
    for _ in range(8):
        by = rng.randint(0, _bg_h)
        bh = rng.randint(2, 6)
        bx = rng.randint(0, _bg_w // 2)
        bw = rng.randint(100, 500)
        col = rng.choice([(0, 200, 220, 15), (200, 40, 180, 15), (180, 180, 40, 10)])
        _overlay(surf, col, (bx, by, bw, bh))

    # Décalages de couches
    for _ in range(6):
        rx = rng.randint(0, _bg_w)
        ry = rng.randint(0, _bg_h)
        rw = rng.randint(40, 200)
        rh = rng.randint(10, 40)
        offset = rng.choice([-8, -4, 4, 8])
        _overlay(surf, (60, 180, 200, 8), (rx + offset, ry, rw, rh))
        _overlay(surf, (200, 40, 180, 6), (rx - offset, ry + 2, rw, rh))


# --- Fallback ---
def _bg_default(surf, rng):
    _gradient_fill(surf, (14, 12, 22), (8, 6, 14))


# =============================================================================
# ÉCRAN SÉLECTION FACTION
# =============================================================================
def faction_select_screen(screen, fonts, clock, side="A", default_fac_id=None):
    """
    Écran de sélection de faction.
    side = "A" (joueur) ou "B" (IA).
    default_fac_id : pré-sélectionne la faction avec cet ID (préférence agent).
    Retourne l'index de la faction choisie (0-7) ou None si annulé.
    """
    f_title, f_menu, f_small, f_tiny = fonts
    factions = load_factions()
    if not factions:
        return None

    default_sel = next((i for i, f in enumerate(factions) if f.get("id") == default_fac_id), None) if default_fac_id is not None else None
    sel = default_sel if default_sel is not None else 0
    t0 = time.time()

    # Pré-charger les sprites des champions (premier de chaque faction)
    # pour l'aperçu dans le panneau droit
    champ_sprites = {}
    for i, fac in enumerate(factions):
        fac_s = _fac_slug(fac["nom"])
        for c in fac.get("champions", [])[:5]:
            path = _find_champion_sprite(fac_s, c["lettre"], c["nom"])
            if path:
                champ_sprites[(i, c["lettre"])] = path

    while True:
        t = time.time() - t0
        fac = factions[sel]
        fac_color = FACTION_COLORS.get(fac["id"], C_SEL)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_UP, pygame.K_w):
                    sel = (sel - 1) % len(factions)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    sel = (sel + 1) % len(factions)
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return sel
                elif event.key == pygame.K_ESCAPE:
                    return None
            # Souris — hover sur la liste gauche
            if event.type == pygame.MOUSEMOTION:
                mx, my = event.pos
                list_x, list_y = 40, 120
                for i in range(len(factions)):
                    ey = list_y + i * 68
                    if list_x < mx < list_x + 520 and ey < my < ey + 62:
                        sel = i
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                list_x, list_y = 40, 120
                for i in range(len(factions)):
                    ey = list_y + i * 68
                    if list_x < mx < list_x + 520 and ey < my < ey + 62:
                        return i

        # === DRAW (faction select) ===
        screen.fill((12, 10, 22))

        # Panneau détails fond faction thématique
        _panel_x = 600
        _panel_y = 100
        _panel_w = SCREEN_W - _panel_x - 40
        _panel_h = SCREEN_H - _panel_y - 60
        draw_faction_bg(screen, fac["id"], rect=(_panel_x, _panel_y, _panel_w, _panel_h))

        # --- Barre titre ---
        bar_h = 80
        pygame.draw.rect(screen, (18, 15, 32), (0, 0, SCREEN_W, bar_h))
        pygame.draw.line(screen, fac_color, (0, bar_h-1), (SCREEN_W, bar_h-1), 2)

        side_label = "VOTRE FACTION" if side == "A" else "FACTION ADVERSAIRE (IA)"
        title_surf = f_title.render(f"CHOISISSEZ {side_label}", True, C_TITLE)
        # Si trop large, utiliser une font plus petite
        if title_surf.get_width() > SCREEN_W - 40:
            title_surf = f_menu.render(f"CHOISISSEZ {side_label}", True, C_TITLE)
        screen.blit(title_surf, ((SCREEN_W - title_surf.get_width()) // 2,
                                 (bar_h - title_surf.get_height()) // 2))

        # --- Liste factions (gauche) ---
        list_x = 40
        list_y = 100
        list_w = 520
        item_h = 68

        for i, f in enumerate(factions):
            iy = list_y + i * item_h
            is_sel = (i == sel)
            fc = FACTION_COLORS.get(f["id"], C_UNSEL)

            # Fond item
            bg = (28, 24, 48) if is_sel else (18, 15, 30)
            pygame.draw.rect(screen, bg, (list_x, iy, list_w, item_h - 4))

            # Barre accent gauche
            bar_col = fc if is_sel else tuple(c//3 for c in fc)
            pygame.draw.rect(screen, bar_col, (list_x, iy, 5, item_h - 4))

            # Bordure sélection
            if is_sel:
                pygame.draw.rect(screen, fc, (list_x, iy, list_w, item_h - 4), 2)

            # Numéro
            num_col = fc if is_sel else C_UNSEL
            num_s = f_menu.render(f"[{f['id']}]", True, num_col)
            screen.blit(num_s, (list_x + 14, iy + 8))

            # Nom faction — nom court (avant le –)
            nom_parts = f["nom"].split("\u2013")
            nom_court = nom_parts[0].strip()
            nom_col = (240, 235, 250) if is_sel else (160, 155, 170)
            ns = f_menu.render(nom_court[:22], True, nom_col)
            screen.blit(ns, (list_x + 65, iy + 8))

            # Sous-titre (après le –)
            if len(nom_parts) > 1:
                sub = nom_parts[1].strip()[:35]
                sub_col = fc if is_sel else (90, 85, 105)
                ss = f_tiny.render(sub, True, sub_col)
                screen.blit(ss, (list_x + 65, iy + 30))

            # Style court à droite
            style_short = f.get("style", "")[:30]
            st_s = f_tiny.render(style_short, True, (80, 76, 98) if not is_sel else (140, 135, 160))
            screen.blit(st_s, (list_x + 65, iy + 46))

            # Badge préférence agent
            if default_sel is not None and i == default_sel:
                badge = f_tiny.render("★ PREF. AGENT", True, (200, 160, 50))
                screen.blit(badge, (list_x + list_w - badge.get_width() - 10, iy + 8))

        # --- Panneau détails (droite) ---
        panel_x = 600
        panel_y = 100
        panel_w = SCREEN_W - panel_x - 40
        panel_h = SCREEN_H - panel_y - 60

        # Fond panel semi-transparent (laisse le bg faction visible)
        panel_ov = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel_ov.fill((14, 12, 26, 180))
        screen.blit(panel_ov, (panel_x, panel_y))
        pygame.draw.rect(screen, fac_color, (panel_x, panel_y, panel_w, panel_h), 1)
        pygame.draw.rect(screen, fac_color, (panel_x, panel_y, panel_w, 4))

        # --- Zone gauche du panel (texte) ---
        text_w = panel_w - 340   # réserve 320px à droite pour le QG
        py = panel_y + 16

        # Nom complet
        full_name = fac["nom"]
        fn_s = f_menu.render(full_name[:42], True, fac_color)
        screen.blit(fn_s, (panel_x + 20, py))
        py += fn_s.get_height() + 12

        # Style
        style_label = f_tiny.render("STYLE", True, (100, 96, 120))
        screen.blit(style_label, (panel_x + 20, py))
        py += 16
        _draw_wrapped(screen, f_tiny, fac.get("style", "?"),
                      panel_x + 20, py, text_w - 20, (180, 175, 195))
        py += 50

        # Gameplay
        gp_label = f_tiny.render("GAMEPLAY", True, (100, 96, 120))
        screen.blit(gp_label, (panel_x + 20, py))
        py += 16
        _draw_wrapped(screen, f_tiny, fac.get("gameplay", "?"),
                      panel_x + 20, py, text_w - 20, (170, 165, 188))
        py += 80

        # Monstres par niveau
        mons = fac.get("monstres", [])
        levels = {}
        for m in mons:
            lv = m.get("niveau", 0)
            levels[lv] = levels.get(lv, 0) + 1

        ml_label = f_tiny.render("UNITES PAR NIVEAU", True, (100, 96, 120))
        screen.blit(ml_label, (panel_x + 20, py))
        py += 18
        for lv in sorted(levels.keys()):
            cnt = levels[lv]
            bar_w_max = 180
            bar_fill = int(bar_w_max * cnt / max(levels.values()))
            lv_s = f_tiny.render(f"Lv{lv}", True, (160, 155, 175))
            screen.blit(lv_s, (panel_x + 20, py))
            pygame.draw.rect(screen, (30, 26, 45), (panel_x + 70, py + 2, bar_w_max, 10))
            pygame.draw.rect(screen, fac_color, (panel_x + 70, py + 2, bar_fill, 10))
            cnt_s = f_tiny.render(str(cnt), True, (140, 135, 158))
            screen.blit(cnt_s, (panel_x + 70 + bar_w_max + 8, py))
            py += 18

        # --- QG sprite (droite du panel) ---
        qg_x = panel_x + panel_w - 320
        qg_y = panel_y + 24
        qg_sz = 280
        fac_s = _fac_slug(fac["nom"])
        qg_path = os.path.join(SPRITES_ROOT, "QG", f"QG_{fac_s}.png")
        qg_spr = _load_sprite(qg_path, qg_sz, qg_sz)

        # Fond slot QG
        pygame.draw.rect(screen, (12, 10, 22), (qg_x, qg_y, qg_sz, qg_sz))
        pygame.draw.rect(screen, tuple(c//2 for c in fac_color),
                         (qg_x, qg_y, qg_sz, qg_sz), 1)

        if qg_spr:
            sw, sh = qg_spr.get_size()
            screen.blit(qg_spr, (qg_x + (qg_sz-sw)//2, qg_y + (qg_sz-sh)//2))
        else:
            qs = f_menu.render("QG", True, (50, 45, 65))
            screen.blit(qs, (qg_x + qg_sz//2 - qs.get_width()//2,
                             qg_y + qg_sz//2 - qs.get_height()//2))

        # Label sous le QG
        qg_label = f_tiny.render("QUARTIER GENERAL", True, (90, 85, 108))
        screen.blit(qg_label, (qg_x + (qg_sz - qg_label.get_width())//2,
                                qg_y + qg_sz + 4))

        py += 16

        # Champions — 5 portraits en ligne
        champ_label = f_tiny.render("CHAMPIONS", True, (100, 96, 120))
        screen.blit(champ_label, (panel_x + 20, py))
        py += 18

        champs = fac.get("champions", [])
        spr_sz = 80
        gap = 12

        for ci, c in enumerate(champs[:5]):
            cx = panel_x + 20 + ci * (spr_sz + gap)
            cy = py

            pygame.draw.rect(screen, (22, 18, 36), (cx, cy, spr_sz, spr_sz))
            pygame.draw.rect(screen, fac_color, (cx, cy, spr_sz, spr_sz), 1)

            path = champ_sprites.get((sel, c["lettre"]))
            if path:
                spr = _load_sprite(path, spr_sz, spr_sz)
                if spr:
                    sw, sh = spr.get_size()
                    screen.blit(spr, (cx + (spr_sz-sw)//2, cy + (spr_sz-sh)//2))
                else:
                    qs = f_menu.render("?", True, (60, 55, 80))
                    screen.blit(qs, (cx + spr_sz//2 - qs.get_width()//2,
                                     cy + spr_sz//2 - qs.get_height()//2))
            else:
                qs = f_menu.render("?", True, (60, 55, 80))
                screen.blit(qs, (cx + spr_sz//2 - qs.get_width()//2,
                                 cy + spr_sz//2 - qs.get_height()//2))

            ls = f_tiny.render(c["lettre"], True, fac_color)
            screen.blit(ls, (cx + 3, cy + 2))
            ns = f_tiny.render(c["nom"][:12], True, (160, 155, 175))
            screen.blit(ns, (cx, cy + spr_sz + 3))

        py += spr_sz + 24

        # Stats résumé champions
        if champs:
            avg_hp  = sum(c.get("stats",{}).get("HP",0)  for c in champs) // len(champs)
            avg_atk = sum(c.get("stats",{}).get("ATK",0) for c in champs) // len(champs)
            avg_def = sum(c.get("stats",{}).get("DEF",0) for c in champs) // len(champs)
            stat_s = f_tiny.render(f"Moy. Champions: HP={avg_hp}  ATK={avg_atk}  DEF={avg_def}", True, (130, 125, 148))
            screen.blit(stat_s, (panel_x + 20, py))

        # --- Hints bas ---
        hint_y = SCREEN_H - 40
        hints = [
            ("\u2191\u2193 / Souris", "Parcourir"),
            ("ENTREE", "Valider"),
            ("ESC", "Retour"),
        ]
        hx = 40
        for key, desc in hints:
            ks = f_tiny.render(key, True, C_SEL)
            ds = f_tiny.render(f" {desc}", True, C_UNSEL)
            screen.blit(ks, (hx, hint_y))
            screen.blit(ds, (hx + ks.get_width(), hint_y))
            hx += ks.get_width() + ds.get_width() + 30

        pygame.display.flip()
        clock.tick(FPS)


def _draw_wrapped(screen, font, text, x, y, max_w, color):
    """Dessine du texte avec retour à la ligne automatique."""
    words = text.split()
    line = ""
    ly = y
    for w in words:
        test = f"{line} {w}".strip()
        tw = font.size(test)[0]
        if tw > max_w and line:
            screen.blit(font.render(line, True, color), (x, ly))
            ly += font.get_height() + 2
            line = w
        else:
            line = test
    if line:
        screen.blit(font.render(line, True, color), (x, ly))


# =============================================================================
# ÉCRAN SÉLECTION CHAMPION
# =============================================================================
def champion_select_screen(screen, fonts, clock, faction_idx, side="A", default_champ_letter=None):
    """
    Écran de sélection du champion pour la faction choisie.
    default_champ_letter : pré-sélectionne le champion avec cette lettre (préférence agent).
    Retourne l'index du champion (0-4) ou None si annulé.
    """
    f_title, f_menu, f_small, f_tiny = fonts
    factions = load_factions()
    if not factions or faction_idx >= len(factions):
        return None

    fac = factions[faction_idx]
    champs = fac.get("champions", [])
    if not champs:
        return None

    fac_color = FACTION_COLORS.get(fac["id"], C_SEL)
    fac_s = _fac_slug(fac["nom"])
    default_sel = next((i for i, c in enumerate(champs) if c.get("lettre","").upper() == (default_champ_letter or "").upper()), None) if default_champ_letter else None
    sel = default_sel if default_sel is not None else 0

    # Pré-charger les sprites champions
    spr_paths = {}
    for c in champs:
        path = _find_champion_sprite(fac_s, c["lettre"], c["nom"])
        if path:
            spr_paths[c["lettre"]] = path

    # QG sprite path
    qg_path = os.path.join(SPRITES_ROOT, "QG", f"QG_{fac_s}.png")

    while True:
        champ = champs[sel]
        stats = champ.get("stats", {})

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_LEFT, pygame.K_a):
                    sel = (sel - 1) % len(champs)
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    sel = (sel + 1) % len(champs)
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return sel
                elif event.key == pygame.K_ESCAPE:
                    return None
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                # Clic sur un portrait champion
                for i in range(len(champs)):
                    cx = _champ_slot_x(i, len(champs))
                    cy = 140
                    if cx < mx < cx + 160 and cy < my < cy + 160:
                        sel = i
                # Clic bouton valider
                btn_x = (SCREEN_W - 220) // 2
                btn_y = SCREEN_H - 80
                if btn_x < mx < btn_x + 220 and btn_y < my < btn_y + 40:
                    return sel
            if event.type == pygame.MOUSEMOTION:
                mx, my = event.pos
                for i in range(len(champs)):
                    cx = _champ_slot_x(i, len(champs))
                    cy = 140
                    if cx < mx < cx + 160 and cy < my < cy + 160:
                        sel = i

        # === DRAW (champion select) ===
        screen.fill((12, 10, 22))

        # --- Barre titre ---
        bar_h = 80
        pygame.draw.rect(screen, (18, 15, 32), (0, 0, SCREEN_W, bar_h))
        pygame.draw.line(screen, fac_color, (0, bar_h-1), (SCREEN_W, bar_h-1), 2)

        side_label = "VOTRE CHAMPION" if side == "A" else "CHAMPION ADVERSAIRE"
        nom_court = fac["nom"].split("\u2013")[0].strip()
        title_text = f"{nom_court} — {side_label}"
        title_surf = f_menu.render(title_text, True, C_TITLE)
        screen.blit(title_surf, ((SCREEN_W - title_surf.get_width()) // 2,
                                 (bar_h - title_surf.get_height()) // 2))

        # --- 5 portraits champions en haut ---
        portrait_sz = 160
        portrait_y = 110

        for i, c in enumerate(champs):
            is_sel = (i == sel)
            cx = _champ_slot_x(i, len(champs))
            cy = portrait_y

            # Fond
            bg = (28, 24, 48) if is_sel else (18, 15, 30)
            pygame.draw.rect(screen, bg, (cx, cy, portrait_sz, portrait_sz))

            # Bordure
            bord = fac_color if is_sel else (40, 36, 55)
            bw = 3 if is_sel else 1
            pygame.draw.rect(screen, bord, (cx, cy, portrait_sz, portrait_sz), bw)

            # Sprite
            path = spr_paths.get(c["lettre"])
            if path:
                spr = _load_sprite(path, portrait_sz, portrait_sz)
                if spr:
                    sw, sh = spr.get_size()
                    screen.blit(spr, (cx + (portrait_sz-sw)//2, cy + (portrait_sz-sh)//2))

            # Lettre en haut gauche
            ls = f_small.render(c["lettre"], True, fac_color if is_sel else (80, 75, 100))
            screen.blit(ls, (cx + 6, cy + 4))

            # Nom sous le portrait
            name_col = (240, 235, 250) if is_sel else (130, 125, 148)
            ns = f_tiny.render(c["nom"][:20], True, name_col)
            screen.blit(ns, (cx + (portrait_sz - ns.get_width())//2, cy + portrait_sz + 6))

            # Badge préférence agent
            if default_sel is not None and i == default_sel:
                badge = f_tiny.render("★", True, (200, 160, 50))
                screen.blit(badge, (cx + portrait_sz - badge.get_width() - 4, cy + 4))

            # Indicateur sélection (triangle bas)
            if is_sel:
                tx = cx + portrait_sz // 2
                ty = cy + portrait_sz + 22
                pygame.draw.polygon(screen, fac_color,
                                    [(tx-8, ty), (tx+8, ty), (tx, ty+10)])

        # --- Panel détail du champion sélectionné ---
        detail_y = portrait_y + portrait_sz + 50
        detail_x = 80
        detail_w = SCREEN_W - 160
        detail_h = SCREEN_H - detail_y - 100

        # Fond faction thématique dans le panel
        draw_faction_bg(screen, fac["id"], rect=(detail_x, detail_y, detail_w, detail_h))
        # Overlay semi-transparent pour lisibilité
        det_ov = pygame.Surface((detail_w, detail_h), pygame.SRCALPHA)
        det_ov.fill((14, 12, 26, 180))
        screen.blit(det_ov, (detail_x, detail_y))
        pygame.draw.rect(screen, fac_color, (detail_x, detail_y, detail_w, detail_h), 1)
        pygame.draw.rect(screen, fac_color, (detail_x, detail_y, detail_w, 3))

        # --- Gauche : grand sprite + stats ---
        big_sz = 220
        big_x = detail_x + 30
        big_y = detail_y + 20

        # Grand sprite
        pygame.draw.rect(screen, (22, 18, 36), (big_x, big_y, big_sz, big_sz))
        pygame.draw.rect(screen, fac_color, (big_x, big_y, big_sz, big_sz), 1)
        path = spr_paths.get(champ["lettre"])
        if path:
            spr = _load_sprite(path, big_sz, big_sz)
            if spr:
                sw, sh = spr.get_size()
                screen.blit(spr, (big_x + (big_sz-sw)//2, big_y + (big_sz-sh)//2))

        # Nom + rôle sous le sprite
        name_s = f_menu.render(champ["nom"], True, fac_color)
        screen.blit(name_s, (big_x, big_y + big_sz + 10))

        role_s = f_tiny.render(champ.get("role", "")[:50], True, (160, 155, 178))
        screen.blit(role_s, (big_x, big_y + big_sz + 32))

        # Stats barres
        stat_y = big_y + big_sz + 54
        stat_w = big_sz
        max_stat = 25  # échelle
        for stat_name, stat_key, color in [
            ("HP",  "HP",  (78, 198, 78)),
            ("ATK", "ATK", (218, 78, 78)),
            ("DEF", "DEF", (78, 138, 218)),
        ]:
            val = stats.get(stat_key, 0)
            label = f_tiny.render(f"{stat_name}", True, (160, 155, 178))
            screen.blit(label, (big_x, stat_y))
            # Barre
            bar_x = big_x + 40
            bar_w_max = stat_w - 80
            bar_fill = int(bar_w_max * val / max_stat)
            pygame.draw.rect(screen, (30, 26, 45), (bar_x, stat_y + 2, bar_w_max, 12))
            pygame.draw.rect(screen, color, (bar_x, stat_y + 2, bar_fill, 12))
            # Valeur
            val_s = f_tiny.render(str(val), True, (200, 195, 215))
            screen.blit(val_s, (bar_x + bar_w_max + 8, stat_y))
            stat_y += 22

        # --- Droite : description capacités ---
        text_x = detail_x + big_sz + 80
        text_w = detail_w - big_sz - 120
        text_y = detail_y + 20

        # Action spéciale
        cap_label = f_small.render("ACTION SPECIALE", True, fac_color)
        screen.blit(cap_label, (text_x, text_y))
        text_y += 24
        action_text = champ.get("action_speciale", "Aucune")
        _draw_wrapped(screen, f_tiny, action_text, text_x, text_y, text_w, (180, 175, 198))
        text_y += 120

        # Effet défensif
        def_label = f_small.render("EFFET DEFENSIF", True, fac_color)
        screen.blit(def_label, (text_x, text_y))
        text_y += 24
        def_text = champ.get("effet_defensif", "Aucun")
        _draw_wrapped(screen, f_tiny, def_text, text_x, text_y, text_w, (170, 165, 188))
        text_y += 80

        # Design visuel
        vis_label = f_small.render("APPARENCE", True, (100, 96, 120))
        screen.blit(vis_label, (text_x, text_y))
        text_y += 24
        vis_text = champ.get("design_visuel", "?")
        _draw_wrapped(screen, f_tiny, vis_text, text_x, text_y, text_w, (130, 125, 148))

        # --- QG petit en bas à droite ---
        qg_mini = 120
        qg_x = detail_x + detail_w - qg_mini - 20
        qg_y2 = detail_y + detail_h - qg_mini - 20
        qg_spr = _load_sprite(qg_path, qg_mini, qg_mini)
        if qg_spr:
            sw, sh = qg_spr.get_size()
            screen.blit(qg_spr, (qg_x + (qg_mini-sw)//2, qg_y2 + (qg_mini-sh)//2))

        # --- Bouton valider ---
        btn_w, btn_h2 = 220, 36
        btn_x = (SCREEN_W - btn_w) // 2
        btn_y = SCREEN_H - 80
        pygame.draw.rect(screen, (20, 18, 40), (btn_x, btn_y, btn_w, btn_h2))
        pygame.draw.rect(screen, fac_color, (btn_x, btn_y, btn_w, btn_h2), 2)
        btn_text = f_small.render("VALIDER", True, fac_color)
        screen.blit(btn_text, (btn_x + (btn_w - btn_text.get_width())//2,
                                btn_y + (btn_h2 - btn_text.get_height())//2))

        # --- Hints ---
        hint_y = SCREEN_H - 35
        hints = [
            ("\u2190\u2192 / Souris", "Parcourir"),
            ("ENTREE", "Valider"),
            ("ESC", "Retour"),
        ]
        hx = 40
        for key, desc in hints:
            ks = f_tiny.render(key, True, C_SEL)
            ds = f_tiny.render(f" {desc}", True, C_UNSEL)
            screen.blit(ks, (hx, hint_y))
            screen.blit(ds, (hx + ks.get_width(), hint_y))
            hx += ks.get_width() + ds.get_width() + 30

        pygame.display.flip()
        clock.tick(FPS)


def _champ_slot_x(idx, total):
    """Position X d'un slot champion centré horizontalement."""
    slot_w = 160
    gap = 24
    total_w = total * slot_w + (total - 1) * gap
    start_x = (SCREEN_W - total_w) // 2
    return start_x + idx * (slot_w + gap)


# =============================================================================
# HELPERS CATALOGUE DÉS (correspondance niveau → indices catalogue)
# =============================================================================

# Base index et taille du pool par niveau dans create_starter_dice()
# L1: indices 0-2 (3 dés), L2: 3-5 (3 dés), L3: 6-7, L4: 8-9, L5: 10
_LEVEL_BASE_IDX  = {1: 0, 2: 3, 3: 6, 4: 8, 5: 10}
_LEVEL_POOL_SIZE = {1: 3, 2: 3, 3: 2, 4: 2, 5: 1}

# Composition de référence sac étendu (22 dés)
_EXTENDED_BASE  = {1: 6, 2: 6, 3: 5, 4: 3, 5: 2}
_EXTENDED_TOTAL = 22


def _extended_level_caps(bag_size: int) -> dict:
    """Caps par niveau pour un sac étendu de taille bag_size (même algo que le moteur)."""
    raw = {lv: n * bag_size / _EXTENDED_TOTAL for lv, n in _EXTENDED_BASE.items()}
    floored = {lv: int(v) for lv, v in raw.items()}
    remainder = bag_size - sum(floored.values())
    by_frac = sorted(raw.keys(), key=lambda lv: -(raw[lv] - floored[lv]))
    for lv in by_frac[:remainder]:
        floored[lv] += 1
    return floored


def _roster_to_bag_indices(roster_names, faction_data):
    """
    Retourne une liste d'indices catalogue (1 dé par mob, niveau dé = niveau mob).
    roster_names : liste de noms de mobs sélectionnés dans le draft.
    """
    by_name = {m["nom"]: m for m in faction_data.get("monstres", [])}
    level_count = {}
    indices = []
    for nom in roster_names:
        mob = by_name.get(nom)
        if not mob:
            continue
        lv = mob.get("niveau", 1)
        base = _LEVEL_BASE_IDX.get(lv, 0)
        pool = _LEVEL_POOL_SIZE.get(lv, 1)
        k = level_count.get(lv, 0)
        indices.append(base + (k % pool))
        level_count[lv] = k + 1
    return indices


# =============================================================================
# ÉCRAN CONFIG SAC DE DÉS
# =============================================================================
def config_sac_screen(screen, fonts, clock, factions, fac_a, champ_a, fac_b, champ_b):
    """
    Écran de configuration du sac de dés.
    Retourne dict {bag_size, bag_type} ou None si annulé.
    """
    f_title, f_menu, f_small, f_tiny = fonts

    fac_a_data = factions[fac_a]
    fac_b_data = factions[fac_b]
    champ_a_data = fac_a_data["champions"][champ_a]
    champ_b_data = fac_b_data["champions"][champ_b]
    fac_color_a = FACTION_COLORS.get(fac_a_data["id"], C_SEL)
    fac_color_b = FACTION_COLORS.get(fac_b_data["id"], C_SEL)

    # Options
    size_options = [(11, "RAPIDE", "11 des - parties courtes"), (22, "ETENDU", "22 des - parties longues")]
    type_options = [("S", "STANDARD", "Sac equilibre (core)"), ("E", "ETENDU+", "Composition fixe avancee"), ("P", "PERSO", "Construis ton sac")]

    sel_size = 0   # 0=11, 1=22
    sel_type = 0   # 0=standard, 1=custom
    sel_row  = 0   # 0=taille, 1=type, 2=lancer

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return None
                elif event.key in (pygame.K_UP, pygame.K_w):
                    sel_row = (sel_row - 1) % 3
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    sel_row = (sel_row + 1) % 3
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    if sel_row == 0: sel_size = (sel_size - 1) % len(size_options)
                    elif sel_row == 1: sel_type = (sel_type - 1) % len(type_options)
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    if sel_row == 0: sel_size = (sel_size + 1) % len(size_options)
                    elif sel_row == 1: sel_type = (sel_type + 1) % len(type_options)
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if sel_row == 2:
                        return {"bag_size": size_options[sel_size][0],
                                "bag_type": type_options[sel_type][0]}
                    else:
                        sel_row = min(sel_row + 1, 2)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                # Bouton lancer
                btn_x = (SCREEN_W - 300) // 2
                btn_y = 750
                if btn_x < mx < btn_x + 300 and btn_y < my < btn_y + 50:
                    return {"bag_size": size_options[sel_size][0],
                            "bag_type": type_options[sel_type][0]}

        # === DRAW ===
        screen.fill((12, 10, 22))

        # Barre titre
        bar_h = 80
        pygame.draw.rect(screen, (18, 15, 32), (0, 0, SCREEN_W, bar_h))
        accent = (200, 160, 50)
        pygame.draw.line(screen, accent, (0, bar_h-1), (SCREEN_W, bar_h-1), 2)
        title_surf = f_title.render("CONFIGURATION", True, C_TITLE)
        screen.blit(title_surf, ((SCREEN_W - title_surf.get_width()) // 2,
                                 (bar_h - title_surf.get_height()) // 2))

        # --- Récap sélections en haut ---
        recap_y = 110
        cx = SCREEN_W // 2

        # Joueur A
        recap_a = f_small.render("JOUEUR A", True, fac_color_a)
        screen.blit(recap_a, (cx - 400, recap_y))
        fac_a_name = fac_a_data["nom"].split("\u2013")[0].strip()
        screen.blit(f_tiny.render(f"{fac_a_name} — {champ_a_data['nom']}", True, (180, 175, 195)),
                    (cx - 400, recap_y + 22))

        # Sprite champion A petit
        fac_s_a = _fac_slug(fac_a_data["nom"])
        path_a = _find_champion_sprite(fac_s_a, champ_a_data["lettre"], champ_a_data["nom"])
        if path_a:
            spr_a = _load_sprite(path_a, 60, 60)
            if spr_a:
                screen.blit(spr_a, (cx - 480, recap_y + 2))

        # VS
        vs_s = f_menu.render("VS", True, (200, 160, 50))
        screen.blit(vs_s, (cx - vs_s.get_width()//2, recap_y + 8))

        # Joueur B
        recap_b = f_small.render("IA  B", True, fac_color_b)
        screen.blit(recap_b, (cx + 200, recap_y))
        fac_b_name = fac_b_data["nom"].split("\u2013")[0].strip()
        screen.blit(f_tiny.render(f"{fac_b_name} — {champ_b_data['nom']}", True, (180, 175, 195)),
                    (cx + 200, recap_y + 22))

        # Sprite champion B
        fac_s_b = _fac_slug(fac_b_data["nom"])
        path_b = _find_champion_sprite(fac_s_b, champ_b_data["lettre"], champ_b_data["nom"])
        if path_b:
            spr_b = _load_sprite(path_b, 60, 60)
            if spr_b:
                screen.blit(spr_b, (cx + 480, recap_y + 2))

        # Séparateur
        pygame.draw.line(screen, (40, 36, 55), (cx - 500, recap_y + 55), (cx + 540, recap_y + 55), 1)

        # --- Options ---
        opt_x = cx - 300
        opt_w = 600
        opt_y = 200

        # TAILLE DU SAC
        _draw_option_row(screen, fonts, "TAILLE DU SAC", size_options, sel_size,
                         opt_x, opt_y, opt_w, sel_row == 0, accent)
        opt_y += 140

        # TYPE DE SAC
        _draw_option_row(screen, fonts, "CONFIGURATION DU SAC", type_options, sel_type,
                         opt_x, opt_y, opt_w, sel_row == 1, accent)
        opt_y += 140

        # --- Détail de la config sélectionnée ---
        info_y = opt_y + 20
        info_x = cx - 280

        pygame.draw.rect(screen, (18, 15, 30), (info_x, info_y, 560, 180))
        pygame.draw.rect(screen, (40, 36, 55), (info_x, info_y, 560, 180), 1)

        screen.blit(f_small.render("RESUME", True, accent), (info_x + 20, info_y + 12))

        bag_sz = size_options[sel_size]
        bag_tp = type_options[sel_type]
        details = [
            f"Sac : {bag_sz[0]} des ({bag_sz[1].lower()})",
            f"Config : {bag_tp[1]} — {bag_tp[2]}",
            "",
            f"Joueur A : {fac_a_name} — {champ_a_data['nom']}",
            f"IA     B : {fac_b_name} — {champ_b_data['nom']}",
        ]
        for i, line in enumerate(details):
            col = (160, 155, 178) if line else (0, 0, 0)
            if "Joueur A" in line: col = fac_color_a
            elif "IA" in line: col = fac_color_b
            screen.blit(f_tiny.render(line, True, col), (info_x + 20, info_y + 38 + i * 22))

        # --- Bouton LANCER ---
        btn_w, btn_h2 = 300, 50
        btn_x = (SCREEN_W - btn_w) // 2
        btn_y = 750
        is_btn_sel = (sel_row == 2)

        bg_btn = (30, 28, 55) if is_btn_sel else (20, 18, 40)
        pygame.draw.rect(screen, bg_btn, (btn_x, btn_y, btn_w, btn_h2))
        bord_col = accent if is_btn_sel else (60, 55, 75)
        pygame.draw.rect(screen, bord_col, (btn_x, btn_y, btn_w, btn_h2), 2)

        btn_text = f_menu.render("LANCER LA PARTIE", True, accent if is_btn_sel else C_UNSEL)
        screen.blit(btn_text, (btn_x + (btn_w - btn_text.get_width())//2,
                               btn_y + (btn_h2 - btn_text.get_height())//2))

        if is_btn_sel:
            # Curseurs ► ◄
            cur_l = f_menu.render("\u25ba", True, accent)
            cur_r = f_menu.render("\u25c4", True, accent)
            screen.blit(cur_l, (btn_x - 25, btn_y + 14))
            screen.blit(cur_r, (btn_x + btn_w + 8, btn_y + 14))

        # --- Hints ---
        hint_y = SCREEN_H - 40
        hints = [
            ("\u2191\u2193", "Option"),
            ("\u2190\u2192", "Changer"),
            ("ENTREE", "Valider"),
            ("ESC", "Retour"),
        ]
        hx = 40
        for key, desc in hints:
            ks = f_tiny.render(key, True, C_SEL)
            ds = f_tiny.render(f" {desc}", True, C_UNSEL)
            screen.blit(ks, (hx, hint_y))
            screen.blit(ds, (hx + ks.get_width(), hint_y))
            hx += ks.get_width() + ds.get_width() + 30

        pygame.display.flip()
        clock.tick(FPS)


def _draw_option_row(screen, fonts, label, options, sel_idx, x, y, w, is_active, accent):
    """Dessine une rangée d'options à choix horizontal."""
    f_title, f_menu, f_small, f_tiny = fonts

    # Label
    label_col = accent if is_active else (100, 96, 120)
    screen.blit(f_small.render(label, True, label_col), (x, y))

    # Options en ligne
    opt_y = y + 28
    n = len(options)
    opt_w = w // n - 10

    for i, opt in enumerate(options):
        ox = x + i * (opt_w + 10)
        is_sel = (i == sel_idx)

        # Fond
        bg = (28, 24, 50) if is_sel and is_active else (22, 18, 36) if is_sel else (16, 13, 28)
        pygame.draw.rect(screen, bg, (ox, opt_y, opt_w, 80))

        # Bordure
        if is_sel and is_active:
            pygame.draw.rect(screen, accent, (ox, opt_y, opt_w, 80), 2)
        elif is_sel:
            pygame.draw.rect(screen, (80, 75, 100), (ox, opt_y, opt_w, 80), 1)
        else:
            pygame.draw.rect(screen, (35, 30, 48), (ox, opt_y, opt_w, 80), 1)

        # Texte principal (index 1 du tuple)
        main_text = opt[1] if len(opt) > 1 else str(opt[0])
        main_col = accent if is_sel and is_active else (200, 195, 215) if is_sel else C_UNSEL
        ms = f_menu.render(main_text, True, main_col)
        screen.blit(ms, (ox + (opt_w - ms.get_width())//2, opt_y + 14))

        # Sous-texte (index 2 du tuple)
        if len(opt) > 2:
            sub_col = (150, 145, 168) if is_sel else (90, 85, 108)
            ss = f_tiny.render(opt[2], True, sub_col)
            screen.blit(ss, (ox + (opt_w - ss.get_width())//2, opt_y + 48))

        # Indicateur sélection
        if is_sel:
            pygame.draw.rect(screen, accent if is_active else (80, 75, 100),
                             (ox, opt_y + 76, opt_w, 4))


# =============================================================================
# HINTS BAS D'ÉCRAN (menu principal)
# =============================================================================
def draw_bottom_hints(screen, f_small, f_tiny, t):
    hint = f_small.render("APPUYEZ SUR ENTREE", True, C_HINT)
    hx = (SCREEN_W - hint.get_width())//2
    hy = SCREEN_H - 60
    screen.blit(hint, (hx, hy))
    pygame.draw.line(screen, C_HINT, (hx, hy+hint.get_height()+4), (hx+hint.get_width(), hy+hint.get_height()+4), 1)
    ver = f_tiny.render("DDM v0.4 - Creator Build", True, C_VERSION)
    screen.blit(ver, (SCREEN_W-ver.get_width()-20, SCREEN_H-30))


# =============================================================================
# MODE SELECT SCREEN
# =============================================================================
_MODE_ENTRIES = [
    ("⚔  Joueur vs IA",        "hvia"),
    ("👁  IA vs IA (spectateur)", "iaia"),
    ("🆚  Joueur vs Joueur",    "hvh"),
]

def mode_select_screen(screen, fonts, clock):
    """Retourne 'hvia', 'iaia' ou 'hvh'. None si ESC."""
    f_title, f_menu, f_small, f_tiny = fonts
    sel = 0
    t0 = time.time()

    entries = [
        ("Joueur vs IA",          "hvia"),
        ("IA vs IA  (spectateur)", "iaia"),
        ("Joueur vs Joueur",       "hvh"),
    ]
    subtitles = [
        "Tu controles le Joueur A",
        "Regarde deux IA s'affronter",
        "Deux joueurs sur le meme ecran",
    ]
    bw, bh = 480, len(entries) * 70 + 40
    bx = SCREEN_W // 2 - bw // 2
    by = SCREEN_H // 2 - bh // 2 - 30

    while True:
        t = time.time() - t0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_UP, pygame.K_w):
                    sel = (sel - 1) % len(entries)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    sel = (sel + 1) % len(entries)
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return entries[sel][1]
                elif event.key == pygame.K_ESCAPE:
                    return None
            if event.type == pygame.MOUSEMOTION:
                mx, my = event.pos
                for i in range(len(entries)):
                    ey = by + 20 + i * 70
                    if bx < mx < bx + bw and ey - 4 < my < ey + 56:
                        sel = i
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                for i, (_, mode) in enumerate(entries):
                    ey = by + 20 + i * 70
                    if bx < mx < bx + bw and ey - 4 < my < ey + 56:
                        return mode

        draw_background(screen)
        draw_banner(screen, f_title, t)

        # Titre de l'écran
        titre = f_menu.render("CHOISIR UN MODE", True, C_TITLE)
        screen.blit(titre, (SCREEN_W // 2 - titre.get_width() // 2, by - 50))

        # Boîte
        pygame.draw.rect(screen, C_MENU_BG, (bx, by, bw, bh))
        pygame.draw.rect(screen, C_MENU_BORDER, (bx, by, bw, bh), 2)
        pygame.draw.rect(screen, C_MENU_BORDER, (bx + 5, by + 5, bw - 10, bh - 10), 1)

        for i, (label, _) in enumerate(entries):
            ey = by + 20 + i * 70
            if i == sel:
                hl = pygame.Surface((bw - 14, 58), pygame.SRCALPHA)
                hl.fill((200, 160, 50, 30))
                screen.blit(hl, (bx + 7, ey - 4))
                pulse = int(4 * math.sin(t * 5))
                cur = f_menu.render("\u25ba", True, C_SEL)
                screen.blit(cur, (bx + 18 + pulse // 2, ey + 4))
                screen.blit(f_menu.render(label, True, C_SEL), (bx + 44, ey + 2))
                sub = f_tiny.render(subtitles[i], True, C_HINT)
                screen.blit(sub, (bx + 44, ey + 28))
            else:
                screen.blit(f_menu.render(label, True, C_UNSEL), (bx + 44, ey + 2))
                sub = f_tiny.render(subtitles[i], True, (70, 65, 80))
                screen.blit(sub, (bx + 44, ey + 28))

        hint = f_tiny.render("ENTREE  confirmer      ECHAP  retour", True, C_HINT)
        screen.blit(hint, (SCREEN_W // 2 - hint.get_width() // 2, by + bh + 20))

        pygame.display.flip()
        clock.tick(FPS)


# =============================================================================
# SÉLECTION ADVERSAIRE (HvIA)
# =============================================================================

_OPPONENT_LLM = [
    # (key, label, description, tier, tier_color)
    ("greedy",  "GREEDY",  "IA locale pure — reactif",              "BASELINE",      (120, 115, 135)),
    ("haiku",   "HAIKU",   "Attrition — focus fire sur blesses",    "BASELINE",      (120, 115, 135)),
    ("gemini",  "GEMINI",  "Methodique — defenseur ancre permanent","BASELINE",      (120, 115, 135)),
    ("chatgpt", "CHATGPT", "Tempo — punit les unites isolees",      "INTERMEDIAIRE", (90,  160, 210)),
    ("mistral", "MISTRAL", "Calcule — optimise tout le pool CAP",   "INTERMEDIAIRE", (90,  160, 210)),
    ("grok",    "GROK",    "Rush brut — assaut des le tour 1",      "INTERMEDIAIRE", (90,  160, 210)),
    ("sonnet",  "SONNET",  "Efficacite ressources — defense avant", "AVANCE",        (200, 140,  50)),
    ("opus",    "OPUS",    "Tempo abilities — advance-first",       "AVANCE",        (200, 140,  50)),
    ("deepseek","DEEPSEEK","Meute mobile — flanc & combo MOVE+ATK", "AVANCE",        (200, 140,  50)),
    ("qwen3",   "QWEN3",   "Chaos & illusions — frappes imprevisibles","AVANCE",     (200, 140,  50)),
    ("glm",     "GLM",     "Controle de zone patient — coup fatal QG","AVANCE",      (200, 140,  50)),
]

_OPPONENT_RL = [
    # (key, label, description, tier, tier_color)
    ("jin",    "JIN",    "Curriculum standard       seed 42",    "RL",  (120, 200, 100)),
    ("jio",    "JIO",    "Variance curriculum       seed 137",   "RL",  (120, 200, 100)),
    ("cross",  "CROSS",  "Curriculum inverse        seed 99",    "RL",  (120, 200, 100)),
    ("jaeha",  "JAEHA",  "Generaliste explorateur",              "RL",  (120, 200, 100)),
    ("neosia", "NEOSIA", "Meta-agent contre RL  CHAMPION",       "RL+", (200, 140,  50)),
    ("zenom",  "ZENOM",  "211 stages LLM+RL  self-play  BOSS",  "RL+", (180,  80, 220)),
]


def opponent_select_screen(screen, fonts, clock):
    """
    Sélection de l'adversaire IA pour le mode HvIA.
    Retourne la clé du profil ('greedy', 'haiku', 'jin', 'neosia', ...) ou None si ESC.
    Deux colonnes navigables : LLM (gauche) et RL (droite).
    """
    f_title, f_menu, f_small, f_tiny = fonts
    nL = len(_OPPONENT_LLM)
    nR = len(_OPPONENT_RL)
    # Curseur logique : (col, idx). col 0 = LLM, col 1 = RL.
    col  = 0
    sel  = 0
    t0   = time.time()

    COL_W   = 510
    COL_GAP = 44
    BOX_W   = COL_W * 2 + COL_GAP + 40
    ENTRY_H = 52
    BOX_H   = max(nL, nR) * ENTRY_H + 110
    bx = SCREEN_W // 2 - BOX_W // 2
    by = SCREEN_H // 2 - BOX_H // 2 - 20
    lx = bx + 20
    rx = lx + COL_W + COL_GAP

    C_RL_HDR     = (120, 200, 100)

    def current_choice():
        if col == 0:
            return _OPPONENT_LLM[sel][0]
        return _OPPONENT_RL[sel][0]

    while True:
        t = time.time() - t0
        cur_n = nL if col == 0 else nR
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_UP, pygame.K_w):
                    sel = (sel - 1) % cur_n
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    sel = (sel + 1) % cur_n
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    col = 0
                    sel = min(sel, nL - 1)
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    col = 1
                    sel = min(sel, nR - 1)
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return current_choice()
                elif event.key == pygame.K_ESCAPE:
                    return None
            if event.type == pygame.MOUSEMOTION:
                mx, my = event.pos
                for i in range(nL):
                    ey = by + 66 + i * ENTRY_H
                    if lx < mx < lx + COL_W and ey - 4 < my < ey + ENTRY_H - 4:
                        col = 0; sel = i
                for i in range(nR):
                    ey = by + 66 + i * ENTRY_H
                    if rx < mx < rx + COL_W and ey - 4 < my < ey + ENTRY_H - 4:
                        col = 1; sel = i
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                for i in range(nL):
                    ey = by + 66 + i * ENTRY_H
                    if lx < mx < lx + COL_W and ey - 4 < my < ey + ENTRY_H - 4:
                        return _OPPONENT_LLM[i][0]
                for i in range(nR):
                    ey = by + 66 + i * ENTRY_H
                    if rx < mx < rx + COL_W and ey - 4 < my < ey + ENTRY_H - 4:
                        return _OPPONENT_RL[i][0]

        draw_background(screen)
        draw_banner(screen, f_title, t)

        # Titre
        titre = f_menu.render("CHOISIR L'ADVERSAIRE", True, C_TITLE)
        screen.blit(titre, (SCREEN_W // 2 - titre.get_width() // 2, by - 50))

        # Boîte
        pygame.draw.rect(screen, C_MENU_BG, (bx, by, BOX_W, BOX_H))
        pygame.draw.rect(screen, C_MENU_BORDER, (bx, by, BOX_W, BOX_H), 2)
        pygame.draw.rect(screen, C_MENU_BORDER, (bx + 5, by + 5, BOX_W - 10, BOX_H - 10), 1)

        # Séparateur vertical
        sx = lx + COL_W + COL_GAP // 2
        pygame.draw.line(screen, (55, 50, 65), (sx, by + 16), (sx, by + BOX_H - 16), 1)

        # En-tête colonne gauche
        h_llm = f_small.render("PROFILS LLM", True, C_HINT)
        screen.blit(h_llm, (lx, by + 16))

        # En-tête colonne droite
        h_rl = f_small.render("AGENTS RL", True, C_RL_HDR)
        screen.blit(h_rl, (rx, by + 16))

        # Helper pour dessiner une entrée (sélectionnable)
        def draw_entry(x_root, i, entry, is_sel):
            key, label, desc, tier, tier_col = entry
            ey = by + 50 + i * ENTRY_H
            if is_sel:
                hl = pygame.Surface((COL_W - 8, ENTRY_H - 4), pygame.SRCALPHA)
                hl.fill((200, 160, 50, 30))
                screen.blit(hl, (x_root + 2, ey - 2))
                pulse = int(3 * math.sin(t * 5))
                screen.blit(f_small.render("►", True, C_SEL),
                            (x_root + 8 + pulse // 2, ey + 8))
                screen.blit(f_menu.render(label, True, C_SEL),    (x_root + 26, ey + 3))
                screen.blit(f_tiny.render(desc,  True, C_HINT),    (x_root + 26, ey + 28))
                ts = f_tiny.render(tier, True, tier_col)
                screen.blit(ts, (x_root + COL_W - ts.get_width() - 8, ey + 6))
            else:
                screen.blit(f_menu.render(label, True, C_UNSEL),       (x_root + 26, ey + 3))
                screen.blit(f_tiny.render(desc,  True, (68, 62, 78)),   (x_root + 26, ey + 28))
                ts = f_tiny.render(tier, True, (58, 54, 68))
                screen.blit(ts, (x_root + COL_W - ts.get_width() - 8, ey + 6))

        # Entrées LLM (col gauche)
        for i, entry in enumerate(_OPPONENT_LLM):
            draw_entry(lx, i, entry, is_sel=(col == 0 and i == sel))

        # Entrées RL (col droite, sélectionnables désormais)
        for i, entry in enumerate(_OPPONENT_RL):
            draw_entry(rx, i, entry, is_sel=(col == 1 and i == sel))

        hint = f_tiny.render(
            "FLECHES naviguer (gauche/droite = colonne)   ENTREE confirmer   ECHAP retour",
            True, C_HINT)
        screen.blit(hint, (SCREEN_W // 2 - hint.get_width() // 2, by + BOX_H + 18))

        pygame.display.flip()
        clock.tick(FPS)


# =============================================================================
# MAIN MENU LOOP
# =============================================================================
def main_menu_screen(screen, fonts, clock):
    f_title, f_menu, f_small, f_tiny = fonts
    sel = 0
    t0 = time.time()

    while True:
        t = time.time() - t0
        for event in pygame.event.get():
            if event.type == pygame.QUIT: return "quit"
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_UP, pygame.K_w):
                    sel = (sel-1) % len(MENU_ENTRIES)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    sel = (sel+1) % len(MENU_ENTRIES)
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return MENU_ENTRIES[sel][1]
                elif event.key == pygame.K_ESCAPE:
                    return "quit"
            if event.type == pygame.MOUSEMOTION:
                mx, my = event.pos
                bx = SCREEN_W//2 - 350//2 - 90
                for i in range(len(MENU_ENTRIES)):
                    ey = 560 + 22 + i*46
                    if bx < mx < bx+350 and ey-4 < my < ey+36:
                        sel = i
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                bx = SCREEN_W//2 - 350//2 - 90
                for i, (_, act) in enumerate(MENU_ENTRIES):
                    ey = 560 + 22 + i*46
                    if bx < mx < bx+350 and ey-4 < my < ey+36:
                        return act

        draw_background(screen)
        draw_banner(screen, f_title, t)
        draw_mini_board(screen)
        draw_deco_dice(screen, t)
        draw_menu_box(screen, f_menu, sel, t)
        draw_bottom_hints(screen, f_small, f_tiny, t)
        pygame.display.flip()
        clock.tick(FPS)


# =============================================================================
# MAIN
# =============================================================================
def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.SCALED | pygame.RESIZABLE)
    pygame.display.set_caption("DDM - Menu")
    clock = pygame.time.Clock()

    try:
        f_title = pygame.font.Font(FONT_PATH, 42)
        f_menu  = pygame.font.Font(FONT_PATH, 15)
        f_small = pygame.font.Font(FONT_PATH, 11)
        f_tiny  = pygame.font.Font(FONT_PATH, 9)
    except:
        f_title = pygame.font.SysFont(None, 64)
        f_menu  = pygame.font.SysFont(None, 28)
        f_small = pygame.font.SysFont(None, 22)
        f_tiny  = pygame.font.SysFont(None, 18)

    fonts = (f_title, f_menu, f_small, f_tiny)

    while True:
        action = main_menu_screen(screen, fonts, clock)
        if action == "quit":
            break
        elif action == "new_game":
            # State machine : ESC retourne à l'écran précédent (pas au menu principal)
            # Si ESC à la 1ère étape (mode) → retour menu principal
            factions = load_factions()
            mode = ai_profile = ai_profile_a = ai_profile_b = None
            fac_a = champ_a = fac_b = champ_b = config = None
            ai_profile = "greedy"

            step = 0
            cancel_to_menu = False
            while step < 6:
                if step == 0:
                    # Écran 0 — Sélection du mode
                    res = mode_select_screen(screen, fonts, clock)
                    if res is None: cancel_to_menu = True; break
                    mode = res
                    step = 1
                elif step == 1:
                    # Écran 0b — Sélection adversaire(s) selon mode
                    if mode == "hvia":
                        res = opponent_select_screen(screen, fonts, clock)
                        if res is None: step = 0; continue
                        ai_profile = res
                    elif mode == "iaia":
                        res_a = opponent_select_screen(screen, fonts, clock)
                        if res_a is None: step = 0; continue
                        print(f"[MENU] IAvIA — Profil A : {res_a}")
                        res_b = opponent_select_screen(screen, fonts, clock)
                        if res_b is None: continue  # back to choose A
                        print(f"[MENU] IAvIA — Profil B : {res_b}")
                        ai_profile_a, ai_profile_b = res_a, res_b
                    # mode == "hvh" : pas d'opponent
                    step = 2
                elif step == 2:
                    # Écran 1 — Sélection Faction A
                    res = faction_select_screen(screen, fonts, clock, side="A")
                    if res is None: step = 1; continue
                    fac_a = res
                    print(f"[MENU] Faction A: [{fac_a+1}] {factions[fac_a]['nom']}")
                    step = 3
                elif step == 3:
                    # Écran 2 — Sélection Champion A
                    res = champion_select_screen(screen, fonts, clock, fac_a, side="A")
                    if res is None: step = 2; continue
                    champ_a = res
                    cd = factions[fac_a]["champions"][champ_a]
                    print(f"[MENU] Champion A: {cd['lettre']} - {cd['nom']}")
                    step = 4
                elif step == 4:
                    # Écran 3+4 — Faction B + Champion B (sautés en IAvIA = random)
                    if mode == "iaia":
                        import random
                        fac_b   = random.randrange(len(factions))
                        champ_b = random.randrange(len(factions[fac_b]["champions"]))
                        print(f"[MENU] Mode IAvIA — Faction B auto: {factions[fac_b]['nom']}")
                        step = 5
                    else:
                        _pref_fac, _pref_champ = _load_agent_prefs(ai_profile)
                        res = faction_select_screen(screen, fonts, clock, side="B", default_fac_id=_pref_fac)
                        if res is None: step = 3; continue
                        fac_b = res
                        print(f"[MENU] Faction B: [{fac_b+1}] {factions[fac_b]['nom']}")
                        _champ_hint = _pref_champ if (_pref_fac is not None and factions[fac_b].get("id") == _pref_fac) else None
                        res = champion_select_screen(screen, fonts, clock, fac_b, side="B", default_champ_letter=_champ_hint)
                        if res is None: continue  # retry faction B
                        champ_b = res
                        cd = factions[fac_b]["champions"][champ_b]
                        print(f"[MENU] Champion B: {cd['lettre']} - {cd['nom']}")
                        step = 5
                elif step == 5:
                    # Écran 5 — Config sac de dés
                    res = config_sac_screen(screen, fonts, clock, factions, fac_a, champ_a, fac_b, champ_b)
                    if res is None: step = 4; continue
                    config = res
                    step = 6  # done

            if cancel_to_menu:
                continue

            # === LANCEMENT DE LA PARTIE ===
            fac_id_a = factions[fac_a]["id"]
            fac_id_b = factions[fac_b]["id"]
            letter_a = factions[fac_a]["champions"][champ_a]["lettre"]
            letter_b = factions[fac_b]["champions"][champ_b]["lettre"]
            bag_size  = config["bag_size"]
            bag_type  = config["bag_type"]
            # Note : mode étendu = composition proportionnelle (6L1+6L2+5L3+3L4+2L5)
            # scalée à bag_size (cf build_extended_dice_bag dans engine).
            # Donc bag_size de 11 ou 22 fonctionnent tous les deux.

            # Si mode personnalisé → sac custom + draft d'armée
            dice_indices_a = None
            dice_indices_b = None
            draft_roster_a = None
            draft_roster_b = None

            if bag_type == "P":
                indices = config_bag_perso_screen(screen, fonts, clock, bag_size)
                if indices is None:
                    continue
                dice_indices_a = indices
                draft_roster_a = draft_army_screen(
                    screen, fonts, clock, factions[fac_a], "JOUEUR A", bag_size)
                if draft_roster_a is None:
                    continue
                if mode == "iaia":
                    draft_roster_b = draft_army_screen(
                        screen, fonts, clock, factions[fac_b], "IA B", bag_size)
                    if draft_roster_b is None:
                        continue

            # Étendu : draft d'armée → sac dérivé du roster (niveau mob = niveau dé)
            elif bag_type == "E":
                draft_roster_a = draft_army_screen(
                    screen, fonts, clock, factions[fac_a], "JOUEUR A", bag_size)
                if draft_roster_a is None:
                    continue
                dice_indices_a = _roster_to_bag_indices(draft_roster_a, factions[fac_a])
                if mode == "iaia":
                    draft_roster_b = draft_army_screen(
                        screen, fonts, clock, factions[fac_b], "IA B", bag_size)
                    if draft_roster_b is None:
                        continue
                    dice_indices_b = _roster_to_bag_indices(draft_roster_b, factions[fac_b])
                bag_type = "P"  # moteur lit les indices

            print(f"\n{'='*60}")
            print(f"[MENU] LANCEMENT PARTIE — mode={mode}")
            print(f"  Joueur A : {factions[fac_a]['nom']} — Champion {letter_a}")
            print(f"  Joueur B : {factions[fac_b]['nom']} — Champion {letter_b}")
            print(f"  Sac      : {bag_size} dés, type {bag_type}")
            print(f"{'='*60}\n")

            launch_game(screen, fac_id_a, letter_a, fac_id_b, letter_b, bag_size, mode,
                        bag_type=bag_type, dice_indices_a=dice_indices_a, dice_indices_b=dice_indices_b,
                        draft_roster_a=draft_roster_a, draft_roster_b=draft_roster_b,
                        ai_profile=ai_profile,
                        ai_profile_a=ai_profile_a, ai_profile_b=ai_profile_b)
            break  # quitte le menu après lancement
        elif action == "tournament":
            factions = load_factions()
            fac_a = faction_select_screen(screen, fonts, clock, side="A")
            if fac_a is None:
                continue
            champ_a = champion_select_screen(screen, fonts, clock, fac_a, side="A")
            if champ_a is None:
                continue
            letter_a = factions[fac_a]["champions"][champ_a]["lettre"]
            screen.fill((12, 10, 22))
            _tm = fonts[2].render("PREPARATION DU TOURNOI...", True, C_TITLE)
            screen.blit(_tm, ((SCREEN_W - _tm.get_width()) // 2, SCREEN_H // 2 - 15))
            pygame.display.flip()
            time.sleep(0.4)
            pygame.quit()
            run_tournament_loop(fac_a, letter_a, bag_size=11)
            # Re-init pour retour au menu
            global _bg_surface
            pygame.init()
            screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.SCALED | pygame.RESIZABLE)
            pygame.display.set_caption("DDM - Menu")
            clock  = pygame.time.Clock()
            fonts  = _reload_fonts()
            _bg_surface = None
        elif action == "encyclopedia":
            pygame.quit()
            enc_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ddm_encyclopedia.py")
            subprocess.run([sys.executable, enc_path])
            pygame.init()
            screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.SCALED | pygame.RESIZABLE)
            pygame.display.set_caption("DDM - Menu")
            clock  = pygame.time.Clock()
            fonts  = _reload_fonts()
            _bg_surface = None
        elif action == "load_game":
            _placeholder(screen, fonts, clock, "CHARGER PARTIE - A VENIR")
        elif action == "options":
            _placeholder(screen, fonts, clock, "OPTIONS - A VENIR")

    pygame.quit()
    sys.exit()


# =============================================================================
# ÉCRAN SÉLECTEUR DE SAC PERSONNALISÉ
# =============================================================================

_DIE_TYPES = [
    # (label, sous-label, level, catalog_indices, faces_desc)
    ("L1 Blanc",  "Base",    1, [0, 1, 2],    "MOVEx2 DEFx1 ATKx1 STARx2"),
    ("L2 Stable", "Equil.",  2, [3, 4],       "MOVEx1 DEFx1 ATKx1 CAPx1 STARx1"),
    ("L2 Agro",   "Offens.", 2, [5],          "MOVEx1 ATKx2 CAPx1 DEFx1 STARx1"),
    ("L3 Bleu",   "Traps",   3, [6, 7],       "MOVEx1 ATKx1 CAPx2 DEFx1 STARx1"),
    ("L4 Rouge",  "Elite",   4, [8, 9],       "ATKx2 MOVEx1 CAPx2 STARx1"),
    ("L5 Noir",   "Apex",    5, [10],         "ATKx1 MOVEx1 CAPx1 DEFx1 STARx2"),
]

_DIE_LEVEL_COLORS = {
    1: (200, 200, 200),
    2: (100, 200, 100),
    3: (80, 140, 255),
    4: (220, 80, 80),
    5: (60, 60, 60),
}


def config_bag_perso_screen(screen, fonts, clock, bag_size):
    """
    Écran de construction du sac personnalisé.
    Retourne list[int] d'indices catalogue ou None si annulé.
    bag_size : taille cible.
    """
    f_title, f_menu, f_small, f_tiny = fonts
    accent = (200, 160, 50)

    counts = [0] * len(_DIE_TYPES)
    sel = 0

    def _total():
        return sum(counts)

    def _to_indices():
        result = []
        for ti, cnt in enumerate(counts):
            pool = _DIE_TYPES[ti][3]
            for k in range(cnt):
                result.append(pool[k % len(pool)])
        return result

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return None
                elif event.key in (pygame.K_UP, pygame.K_w):
                    sel = (sel - 1) % len(_DIE_TYPES)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    sel = (sel + 1) % len(_DIE_TYPES)
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    if counts[sel] > 0:
                        counts[sel] -= 1
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    if _total() < bag_size:
                        counts[sel] += 1
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if _total() == bag_size:
                        return _to_indices()
                    elif _total() < bag_size:
                        counts[sel] += min(1, bag_size - _total())

        # Draw
        screen.fill((12, 10, 22))

        # Titre
        bar_h = 80
        pygame.draw.rect(screen, (18, 15, 32), (0, 0, SCREEN_W, bar_h))
        pygame.draw.line(screen, accent, (0, bar_h - 1), (SCREEN_W, bar_h - 1), 2)
        ts = f_title.render("SAC PERSONNALISE", True, C_TITLE)
        screen.blit(ts, ((SCREEN_W - ts.get_width()) // 2, (bar_h - ts.get_height()) // 2))

        # Compteur total
        total = _total()
        total_col = (100, 220, 100) if total == bag_size else (220, 100, 100) if total > bag_size else accent
        tot_s = f_menu.render(f"{total} / {bag_size} des", True, total_col)
        screen.blit(tot_s, ((SCREEN_W - tot_s.get_width()) // 2, bar_h + 10))

        # Lignes de dés
        row_h = 110
        start_y = bar_h + 60
        col_x = (SCREEN_W - 700) // 2

        for i, (label, sub, level, _, faces) in enumerate(_DIE_TYPES):
            ry = start_y + i * row_h
            is_sel = (i == sel)
            die_col = _DIE_LEVEL_COLORS.get(level, (200, 200, 200))

            # Fond
            bg = (28, 24, 50) if is_sel else (16, 13, 28)
            pygame.draw.rect(screen, bg, (col_x, ry, 700, row_h - 8))
            border = accent if is_sel else (40, 36, 55)
            pygame.draw.rect(screen, border, (col_x, ry, 700, row_h - 8), 2)

            # Pastille couleur niveau
            pygame.draw.circle(screen, die_col, (col_x + 30, ry + (row_h - 8) // 2), 18)

            # Nom + sous-label
            nx = col_x + 60
            ns = f_small.render(label, True, die_col if is_sel else (180, 175, 200))
            screen.blit(ns, (nx, ry + 8))
            ss = f_tiny.render(sub, True, (120, 115, 140))
            screen.blit(ss, (nx, ry + 34))
            fs = f_tiny.render(faces, True, (100, 96, 118))
            screen.blit(fs, (nx, ry + 54))

            # Compteur + arrows
            cnt = counts[i]
            cx2 = col_x + 520
            arrow_col = accent if is_sel else (80, 75, 100)
            al = f_menu.render("<", True, arrow_col)
            ar = f_menu.render(">", True, arrow_col)
            screen.blit(al, (cx2, ry + 28))
            cnt_s = f_menu.render(str(cnt), True, (220, 215, 235))
            screen.blit(cnt_s, (cx2 + 50, ry + 28))
            screen.blit(ar, (cx2 + 100, ry + 28))

        # Hints
        hint_y = SCREEN_H - 40
        hints = [
            ("\u2191\u2193", "Type"), ("\u2190\u2192", "Quantite"),
            ("ENTREE", "Confirmer" if total == bag_size else f"Manque {bag_size - total}"),
            ("ESC", "Retour"),
        ]
        hx = 40
        for key, desc in hints:
            ks = f_tiny.render(key, True, C_SEL)
            ds = f_tiny.render(f" {desc}  ", True, C_UNSEL)
            screen.blit(ks, (hx, hint_y))
            screen.blit(ds, (hx + ks.get_width(), hint_y))
            hx += ks.get_width() + ds.get_width()

        pygame.display.flip()
        clock.tick(FPS)


# =============================================================================
# ÉCRAN DRAFT D'ARMÉE (mode étendu)
# =============================================================================

def draft_army_screen(screen, fonts, clock, faction_data, player_label, bag_size=22):
    """
    Army builder pour le mode étendu.
    Caps par niveau calculés proportionnellement à bag_size.
    Retourne une liste plate avec répétitions ou None si annulé.
    """
    f_title, f_menu, f_small, f_tiny = fonts
    accent = (200, 160, 50)
    lv_colors = {1: (200, 200, 200), 2: (100, 200, 100), 3: (80, 140, 255),
                 4: (220, 80, 80), 5: (140, 50, 200)}

    INDIV_CAP    = {1: 3, 2: 3, 3: 3, 4: 3, 5: 1}
    TOTAL_TARGET = bag_size

    monstres = faction_data.get("monstres", [])
    by_level = {}
    for m in monstres:
        lv = m.get("niveau", 1)
        by_level.setdefault(lv, []).append(m)

    # entries plates : (type, mob_dict_ou_level, count)
    # count = nb d'exemplaires alloués (pour les mobs), 0 pour les headers
    def _build_entries(levels):
        out = []
        for lv in levels:
            if lv not in by_level:
                continue
            out.append(("header", lv, 0))
            for m in by_level[lv]:
                out.append(("mob", m, 0))
        return out

    left_entries  = _build_entries([1, 2, 3])
    right_entries = _build_entries([4, 5])
    entries = left_entries + right_entries
    n_left  = len(left_entries)

    # counts dict : nom → count (entries sont immutables en tuple, on track séparé)
    counts = {}  # nom → count

    def _lv_of(entry):
        _, val, _ = entry
        if isinstance(val, dict):
            return val.get("niveau", 1)
        return val

    def _lv_used(lv):
        return sum(counts.get(m.get("nom"), 0)
                   for _, m, _ in entries
                   if isinstance(m, dict) and m.get("niveau") == lv)

    def _total():
        return sum(counts.values())

    def _nav_next(cur):
        for i in range(cur + 1, len(entries)):
            if entries[i][0] == "mob":
                return i
        return cur

    def _nav_prev(cur):
        for i in range(cur - 1, -1, -1):
            if entries[i][0] == "mob":
                return i
        return cur

    sel = 0
    while sel < len(entries) and entries[sel][0] == "header":
        sel += 1

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return None
                elif event.key in (pygame.K_UP, pygame.K_w):
                    sel = _nav_prev(sel)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    sel = _nav_next(sel)
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    _, mob, _ = entries[sel]
                    nom = mob.get("nom")
                    if counts.get(nom, 0) > 0:
                        counts[nom] = counts.get(nom, 0) - 1
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    _, mob, _ = entries[sel]
                    nom = mob.get("nom")
                    lv  = mob.get("niveau", 1)
                    cur = counts.get(nom, 0)
                    indiv_max  = INDIV_CAP.get(lv, 3)
                    total_free = TOTAL_TARGET - _total()
                    if cur < indiv_max and total_free > 0:
                        counts[nom] = cur + 1
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if _total() == TOTAL_TARGET:
                        roster = []
                        for _, m, _ in entries:
                            if isinstance(m, dict):
                                nom = m.get("nom")
                                roster.extend([nom] * counts.get(nom, 0))
                        return roster

        # ── Draw ──
        screen.fill((12, 10, 22))
        bar_h = 80
        pygame.draw.rect(screen, (18, 15, 32), (0, 0, SCREEN_W, bar_h))
        pygame.draw.line(screen, accent, (0, bar_h - 1), (SCREEN_W, bar_h - 1), 2)

        ts = f_title.render(f"DRAFT ARMEE — {player_label}", True, C_TITLE)
        screen.blit(ts, ((SCREEN_W - ts.get_width()) // 2, (bar_h - ts.get_height()) // 2))

        total = _total()
        tot_col = (100, 220, 100) if total == TOTAL_TARGET else accent
        tot_s = f_menu.render(f"{total} / {TOTAL_TARGET} slots", True, tot_col)
        screen.blit(tot_s, ((SCREEN_W - tot_s.get_width()) // 2, bar_h + 10))

        pygame.draw.line(screen, (40, 36, 55), (SCREEN_W // 2, bar_h + 50),
                         (SCREEN_W // 2, SCREEN_H - 55), 1)

        row_h   = 48
        hdr_h   = 38
        start_y = bar_h + 55
        col_w   = 820
        margin  = 30
        col1_x  = margin
        col2_x  = SCREEN_W // 2 + margin

        def _draw_col(col_entries, offset, col_x):
            y = start_y
            for local_i, entry in enumerate(col_entries):
                global_i = offset + local_i
                etype, val, _ = entry
                if etype == "header":
                    lv   = val
                    col  = lv_colors.get(lv, (200, 200, 200))
                    used = _lv_used(lv)
                    slot_col = (100, 220, 100) if used > 0 else col
                    hs = f_small.render(f"── NIV {lv}  ({used} slots) ──", True, slot_col)
                    screen.blit(hs, (col_x, y))
                    y += hdr_h
                else:
                    nom   = val.get("nom", "?")
                    stats = val.get("stats", {}) or {}
                    lv    = val.get("niveau", 1)
                    cnt   = counts.get(nom, 0)
                    is_sel_row = (global_i == sel)

                    bg     = (28, 24, 50) if is_sel_row else (16, 13, 28)
                    border = accent if is_sel_row else (40, 36, 55)
                    pygame.draw.rect(screen, bg,     (col_x, y, col_w - margin, row_h - 5))
                    pygame.draw.rect(screen, border, (col_x, y, col_w - margin, row_h - 5), 1)

                    # Nom
                    name_col = (220, 215, 235) if cnt > 0 else (100, 96, 118)
                    ns = f_small.render(nom, True, name_col)
                    screen.blit(ns, (col_x + 12, y + 10))

                    # Stats
                    hp  = stats.get("HP", "?")
                    atk = stats.get("ATK", "?")
                    dfn = stats.get("DEF", 0)
                    ss = f_tiny.render(f"HP:{hp} ATK:{atk} DEF:{dfn}", True, (110, 106, 130))
                    screen.blit(ss, (col_x + 12, y + 28))

                    # Compteur +/-
                    cx2 = col_x + col_w - margin - 120
                    arr_col = accent if is_sel_row else (80, 75, 100)
                    cnt_col = (100, 220, 100) if cnt > 0 else (80, 75, 100)
                    screen.blit(f_menu.render("<", True, arr_col), (cx2,      y + 10))
                    screen.blit(f_menu.render(str(cnt), True, cnt_col), (cx2 + 30, y + 10))
                    screen.blit(f_menu.render(">", True, arr_col), (cx2 + 60, y + 10))

                    y += row_h

        _draw_col(left_entries,  0,      col1_x)
        _draw_col(right_entries, n_left, col2_x)

        # Hints
        hint_y = SCREEN_H - 40
        confirm_txt = f"Confirmer" if total == TOTAL_TARGET else f"Manque {TOTAL_TARGET - total}"
        hints = [
            ("\u2191\u2193", "Naviguer"),
            ("\u2190\u2192", "Quantite"),
            ("ENTREE", confirm_txt),
            ("ESC", "Retour"),
        ]
        hx = 40
        for key, desc in hints:
            ks = f_tiny.render(key, True, C_SEL)
            ds = f_tiny.render(f" {desc}  ", True, C_UNSEL)
            screen.blit(ks, (hx, hint_y))
            screen.blit(ds, (hx + ks.get_width(), hint_y))
            hx += ks.get_width() + ds.get_width()

        pygame.display.flip()
        clock.tick(FPS)


def launch_game(screen, fac_id_a, champ_a, fac_id_b, champ_b, bag_size, mode="hvia",
                bag_type="S", dice_indices_a=None, dice_indices_b=None,
                draft_roster_a=None, draft_roster_b=None, ai_profile="greedy",
                ai_profile_a=None, ai_profile_b=None):
    """
    Lance le moteur (subprocess nouvelle console) + renderer (subprocess).
    Ferme le menu Pygame.
    """
    # --- Écran de transition ---
    f = pygame.font.SysFont(None, 32)
    screen.fill((12, 10, 22))
    t1 = f.render("LANCEMENT DE LA PARTIE...", True, (200, 160, 50))
    screen.blit(t1, ((SCREEN_W - t1.get_width())//2, SCREEN_H//2 - 40))
    t2 = f.render("Le moteur et le renderer vont demarrer.", True, (140, 135, 158))
    screen.blit(t2, ((SCREEN_W - t2.get_width())//2, SCREEN_H//2 + 10))
    pygame.display.flip()
    time.sleep(1.5)

    # --- Fermer le menu Pygame ---
    pygame.quit()

    # --- Purger les snapshots de la partie précédente ---
    _snap_dir = os.path.join(ENGINE_DIR, "engine", "snapshots")
    for _fname in ("latest.json", "renderer_ready.json", "renderer_quit.json", "pause.json", "_command", "command.json"):
        _p = os.path.join(_snap_dir, _fname)
        try:
            if os.path.exists(_p):
                os.remove(_p)
        except Exception:
            pass

    # --- Construire la commande moteur ---
    engine_cmd = [
        sys.executable, "-m", "engine.ddm_p4_loop",
        "--mode", "iaia" if mode == "iaia" else "gui",
        "--faction-a", str(fac_id_a),
        "--faction-b", str(fac_id_b),
        "--champion-a", str(champ_a),
        "--champion-b", str(champ_b),
        "--bag", str(bag_size),
        "--bag-type", bag_type,
    ]

    print(f"[LAUNCH] Moteur : {' '.join(engine_cmd)}")
    print(f"[LAUNCH] CWD    : {ENGINE_DIR}")

    # Env partagé engine + renderer
    env = os.environ.copy()
    env["DDM_GUI_CONNECTED"] = "1"
    env["DDM_GAME_MODE"]   = "iaia" if mode == "iaia" else "hvia"
    env["DDM_AI_PROFILE"]  = ai_profile
    # IAvIA : profils par côté (override DDM_AI_PROFILE pour ce mode)
    if ai_profile_a is not None:
        env["DDM_AI_PROFILE_A"] = ai_profile_a
    if ai_profile_b is not None:
        env["DDM_AI_PROFILE_B"] = ai_profile_b
    if dice_indices_a is not None:
        env["DDM_DICE_INDICES_A"] = json.dumps(dice_indices_a)
    if dice_indices_b is not None:
        env["DDM_DICE_INDICES_B"] = json.dumps(dice_indices_b)
    if draft_roster_a is not None:
        env["DDM_DRAFT_ROSTER_A"] = json.dumps(draft_roster_a)
    if draft_roster_b is not None:
        env["DDM_DRAFT_ROSTER_B"] = json.dumps(draft_roster_b)

    # --- Lancer le moteur dans une nouvelle console ---
    try:
        if sys.platform == "win32":
            engine_proc = subprocess.Popen(
                engine_cmd,
                cwd=ENGINE_DIR,
                env=env,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        else:
            engine_proc = subprocess.Popen(
                engine_cmd,
                cwd=ENGINE_DIR,
                env=env,
            )
        print(f"[LAUNCH] Moteur PID: {engine_proc.pid}")
    except Exception as e:
        print(f"[LAUNCH] ERREUR moteur : {e}")
        return

    # --- Lancer le renderer sans délai fixe — l'engine l'attend via renderer_ready.json ---

    print(f"[LAUNCH] Renderer : {RENDERER_PATH}")
    try:
        renderer_proc = subprocess.Popen(
            [sys.executable, RENDERER_PATH],
            env=env,
        )
        print(f"[LAUNCH] Renderer PID: {renderer_proc.pid}")
    except Exception as e:
        print(f"[LAUNCH] ERREUR renderer : {e}")
        return

    print("[LAUNCH] Partie lancee. Le menu se ferme.")


# =============================================================================
# MODE TOURNOI
# Conférence LLM (haut, 8 équipes, 3 rounds) + Conférence RL (bas, 4 agents, 2 rounds)
# Les deux conférences flow gauche→droite ; le vainqueur de chaque conf s'affronte en GF.
# =============================================================================

# ── Tuiles ────────────────────────────────────────────────────────────────────
_T_BW, _T_BH, _T_GAP = 220, 46, 10

# ── Colonnes X ────────────────────────────────────────────────────────────────
# LLM (haut) : QF→SF→LF  |  GF (commun)  |  RL (bas) : même SF et LF que LLM
_T_QF_X = 60    # LLM Quarts
_T_SF_X = 370   # LLM Demis  = RL Demis (même colonne, sections y différentes)
_T_LF_X = 680   # LLM Finale conf = RL Finale conf
_T_GF_X = 990   # Grand Finale

# ── Centres Y — section LLM (haut) ───────────────────────────────────────────
_T_QF_CY = [285, 425, 565, 705]             # remonté de 35px (bas LLM = y756 < sep 775)
_T_SF_CY = [(_T_QF_CY[0]+_T_QF_CY[1])//2,
             (_T_QF_CY[2]+_T_QF_CY[3])//2]  # [355, 635]
_T_LF_CY = (_T_SF_CY[0]+_T_SF_CY[1])//2    # 495 — LLM Final

# ── Centres Y — section RL (bas, après séparateur à y=775) ───────────────────
_T_RL_CY  = [850, 945]                      # descendu ~20px (haut RL = y799 > sep+24)
_T_RF_CY  = (_T_RL_CY[0]+_T_RL_CY[1])//2   # 897 — RL Final

# ── Grand Finale — deux slots indépendants ────────────────────────────────────
_T_GF_LLM_CY = _T_LF_CY   # 530 — connecteur horizontal depuis LLM Final
_T_GF_RL_CY  = _T_RF_CY   # 885 — connecteur horizontal depuis RL Final

# ── GF → Champion (convergence Y-shape) ──────────────────────────────────────
_T_CH_X   = 1270
_T_CH_CY  = (_T_GF_LLM_CY + _T_GF_RL_CY) // 2  # 707
_T_CH_W   = 160
_T_CH_H   = 90

# ── Boss Final (Zenom) ────────────────────────────────────────────────────────
_T_ZN_X   = 1490   # Zenom box (x=1490 → 1710)
_T_ZN_CY  = _T_CH_CY          # 707 — même centre Y que champion
_T_ZN_W   = _T_BW             # 220 — même largeur que les autres boîtes

_T_SEP_Y  = 775   # ligne séparatrice LLM / RL
_T_SNAP   = os.path.join(ENGINE_DIR, "engine", "snapshots", "latest.json")
_T_TIER   = {
    "greedy": 1, "haiku": 1, "gemini": 1,
    "chatgpt": 2, "mistral": 2, "grok": 2,
    "sonnet": 3, "opus": 3, "deepseek": 3, "qwen3": 3, "glm": 3,
    "jin": 4, "jio": 4, "cross": 4, "jaeha": 4, "neosia": 4,
    "zenom": 5,   # boss final — tier max
}
_T_RL_POOL = ["jin", "jio", "cross", "jaeha", "neosia"]  # 5 agents, 4 tirés par tournoi


def _tb1y(cy): return cy - _T_GAP // 2 - _T_BH
def _tb2y(cy): return cy + _T_GAP // 2


# ── Helpers données ───────────────────────────────────────────────────────────

def _weighted_pick(parts, a, b):
    wa = _T_TIER.get(parts[a]['ai_profile'], 1)
    wb = _T_TIER.get(parts[b]['ai_profile'], 1)
    return a if random.random() < wa / (wa + wb) else b


def _llm_teams(bracket, mid):
    ls, lw = bracket['llm_seeds'], bracket['llm_w']
    if mid == 0: return ls[0], ls[7]
    if mid == 1: return ls[3], ls[4]
    if mid == 2: return ls[2], ls[5]
    if mid == 3: return ls[1], ls[6]
    if mid == 4: return lw[0], lw[1]
    if mid == 5: return lw[2], lw[3]
    if mid == 6: return lw[4], lw[5]


def _rl_teams(bracket, mid):
    rs, rw = bracket['rl_seeds'], bracket['rl_w']
    # Bracket 5 équipes avec play-in
    if mid == 0: return rs[3], rs[4]   # play-in  : seed4 vs seed5
    if mid == 1: return rs[0], rw[0]   # SF1      : seed1 vs vainqueur play-in
    if mid == 2: return rs[1], rs[2]   # SF2      : seed2 vs seed3
    if mid == 3: return rw[1], rw[2]   # RL Final : vainqueur SF1 vs vainqueur SF2


def _find_player_match(bracket):
    pi = bracket['player_idx']
    for mid in range(7):
        if bracket['llm_w'][mid] is None:
            ta, tb = _llm_teams(bracket, mid)
            if ta is not None and tb is not None and (ta == pi or tb == pi):
                return ('llm', mid)
    if bracket['include_rl'] and bracket['llm_w'][6] == pi and bracket['gf_w'] is None:
        if bracket['rl_w'][3] is not None:   # RL Final (idx 3) terminée
            return ('gf', 0)
    # Boss Final : vainqueur GF (ou LLM Final si pas de RL) affronte Zenom
    prev_winner = bracket['gf_w'] if bracket['include_rl'] else bracket['llm_w'][6]
    if prev_winner == pi and bracket['boss_w'] is None:
        return ('boss', 0)
    return None


def _generate_tournament(factions, player_fac_idx, player_champ_letter, include_rl=False):
    # Exclure RL agents ET Zenom du pool LLM
    llm_profiles = [k for k in _T_TIER if k not in _T_RL_POOL and k != 'zenom']
    random.shuffle(llm_profiles)
    fac_pool = [i for i in range(len(factions)) if i != player_fac_idx]
    random.shuffle(fac_pool)

    parts = [{'name': 'JOUEUR', 'faction_id': factions[player_fac_idx]['id'],
              'champ': player_champ_letter, 'ai_profile': 'greedy',
              'is_player': True, 'conf': 'llm', 'locked': False}]

    for i in range(7):
        fid  = fac_pool[i % len(fac_pool)]
        prof = llm_profiles[i % len(llm_profiles)]
        cl   = random.choice(factions[fid]['champions'])['lettre']
        parts.append({'name': prof.upper(), 'faction_id': factions[fid]['id'],
                      'champ': cl, 'ai_profile': prof,
                      'is_player': False, 'conf': 'llm', 'locked': False})

    rl_fac = [i for i in range(len(factions)) if i != player_fac_idx]
    random.shuffle(rl_fac)
    # Tous les 5 agents RL (indices 8-12 dans parts)
    for i, agent in enumerate(_T_RL_POOL):
        fid = rl_fac[i % len(rl_fac)]
        cl  = random.choice(factions[fid]['champions'])['lettre']
        parts.append({'name': agent.upper(), 'faction_id': factions[fid]['id'],
                      'champ': cl, 'ai_profile': agent,
                      'is_player': False, 'conf': 'rl', 'locked': not include_rl})

    # Zenom — boss final (index 13 dans parts)
    zn_fac = random.choice(fac_pool)
    zn_cl  = random.choice(factions[zn_fac]['champions'])['lettre']
    parts.append({'name': 'ZENOM', 'faction_id': factions[zn_fac]['id'],
                  'champ': zn_cl, 'ai_profile': 'opus',
                  'is_player': False, 'conf': 'boss', 'locked': False, 'is_boss': True})

    llm_seeds = list(range(8));   random.shuffle(llm_seeds)
    rl_seeds  = list(range(8, 13)); random.shuffle(rl_seeds)  # 5 agents
    return {
        'parts': parts, 'player_idx': 0,
        'llm_seeds': llm_seeds, 'llm_w': [None]*7,
        'rl_seeds':  rl_seeds,  'rl_w':  [None]*4,  # play-in + SF1 + SF2 + Final
        'gf_w': None, 'boss_w': None, 'include_rl': include_rl,
    }


def _resolve_round_ai(bracket, match_key):
    conf, played_mid = match_key
    parts = bracket['parts']
    if conf == 'llm':
        if played_mid <= 3:   mids, rl_sync = [0,1,2,3], 0
        elif played_mid <= 5: mids, rl_sync = [4,5],     1
        else:                 mids, rl_sync = [6],        2
        for mid in mids:
            if mid == played_mid or bracket['llm_w'][mid] is not None: continue
            ta, tb = _llm_teams(bracket, mid)
            if ta is not None and tb is not None:
                bracket['llm_w'][mid] = _weighted_pick(parts, ta, tb)
        if bracket['include_rl']:
            if rl_sync >= 0:
                # Après LLM QF : play-in (0) + SF2 (2) indépendants du play-in
                for mid in [0, 2]:
                    if bracket['rl_w'][mid] is None:
                        ta, tb = _rl_teams(bracket, mid)
                        if ta is not None and tb is not None:
                            bracket['rl_w'][mid] = _weighted_pick(parts, ta, tb)
            if rl_sync >= 1:
                # Après LLM SF : SF1 (1, dépend du play-in) puis Final (3)
                for mid in [1, 3]:
                    if bracket['rl_w'][mid] is None:
                        ta, tb = _rl_teams(bracket, mid)
                        if ta is not None and tb is not None:
                            bracket['rl_w'][mid] = _weighted_pick(parts, ta, tb)


def _finalize_bracket(bracket):
    parts = bracket['parts']
    for mid in range(7):
        if bracket['llm_w'][mid] is None:
            ta, tb = _llm_teams(bracket, mid)
            if ta is not None and tb is not None:
                bracket['llm_w'][mid] = _weighted_pick(parts, ta, tb)
    for mid in range(4):
        if bracket['rl_w'][mid] is None:
            ta, tb = _rl_teams(bracket, mid)
            if ta is not None and tb is not None:
                bracket['rl_w'][mid] = _weighted_pick(parts, ta, tb)
    if bracket['include_rl'] and bracket['gf_w'] is None:
        lf, rf = bracket['llm_w'][6], bracket['rl_w'][3]
        if lf is not None and rf is not None:
            bracket['gf_w'] = _weighted_pick(parts, lf, rf)
    # Boss Final auto-résolu : Zenom gagne toujours si le joueur n'y est pas
    if bracket['boss_w'] is None:
        zenom_idx = next(i for i, p in enumerate(parts) if p.get('is_boss'))
        bracket['boss_w'] = zenom_idx   # Zenom l'emporte


# ── Match physique ─────────────────────────────────────────────────────────────

def _run_match_blocking(fac_a, champ_a, fac_b, champ_b, bag_size, ai_profile):
    env = os.environ.copy()
    env.update({"DDM_GUI_CONNECTED": "1", "DDM_GAME_MODE": "hvia",
                "DDM_AI_PROFILE": ai_profile})
    engine_cmd = [sys.executable, "-m", "engine.ddm_p4_loop", "--mode", "gui",
                  "--faction-a", str(fac_a), "--faction-b", str(fac_b),
                  "--champion-a", champ_a, "--champion-b", champ_b,
                  "--bag", str(bag_size), "--bag-type", "S"]
    _snap_dir2 = os.path.join(ENGINE_DIR, "engine", "snapshots")
    for _fname2 in ("latest.json", "renderer_ready.json", "renderer_quit.json", "pause.json"):
        _p2 = os.path.join(_snap_dir2, _fname2)
        try:
            if os.path.exists(_p2):
                os.remove(_p2)
        except Exception:
            pass
    try:
        kw = {"creationflags": subprocess.CREATE_NEW_CONSOLE} if sys.platform == "win32" else {}
        ep = subprocess.Popen(engine_cmd, cwd=ENGINE_DIR, env=env, **kw)
        rp = subprocess.Popen([sys.executable, RENDERER_PATH], env=env)
        rp.wait(); ep.terminate()
    except Exception as e:
        print(f"[TOURNOI] Erreur : {e}"); return "draw"
    try:
        with open(_T_SNAP, encoding="utf-8") as f:
            return json.load(f).get("winner", "draw")
    except Exception as e:
        print(f"[TOURNOI] Snapshot : {e}"); return "draw"


# ── Dessin bracket ─────────────────────────────────────────────────────────────

def _draw_tourn_bracket(screen, fonts, bracket, player_match, phase, last_res, t):
    f_title, f_menu, f_small, f_tiny = fonts
    parts = bracket['parts']
    pi    = bracket['player_idx']
    lw    = bracket['llm_w']
    rw    = bracket['rl_w']
    blink = int(t * 3) % 2 == 0
    inc   = bracket['include_rl']

    # ── Overlay sombre sur le fond pierre ─────────────────────────────────────
    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 155))
    screen.blit(overlay, (0, 0))

    def ln(a, b, col, w=2): pygame.draw.line(screen, col, a, b, w)

    def pair_conn(x_src, cy_a, cy_b, x_dst, cy_dst, col):
        mx = (x_src + _T_BW + x_dst) // 2
        ln((x_src+_T_BW, cy_a), (mx, cy_a), col)
        ln((x_src+_T_BW, cy_b), (mx, cy_b), col)
        ln((mx, cy_a), (mx, cy_b), col)
        ln((mx, cy_dst), (x_dst, cy_dst), col)

    def horiz(x1, x2, cy, col): ln((x1, cy), (x2, cy), col)

    # Couleurs connecteurs — contrastées sur fond assombri
    C_DIM = (110, 100, 130)              # lignes inactives : gris-violet visible
    cllm  = lambda done: C_MENU_BORDER if done else C_DIM
    crl   = lambda done: (80, 210, 130) if done else C_DIM

    # ── Connecteurs LLM ───────────────────────────────────────────────────────
    pair_conn(_T_QF_X, _T_QF_CY[0], _T_QF_CY[1], _T_SF_X, _T_SF_CY[0],
              cllm(lw[0] and lw[1]))
    pair_conn(_T_QF_X, _T_QF_CY[2], _T_QF_CY[3], _T_SF_X, _T_SF_CY[1],
              cllm(lw[2] and lw[3]))
    pair_conn(_T_SF_X, _T_SF_CY[0], _T_SF_CY[1], _T_LF_X, _T_LF_CY,
              cllm(lw[4] and lw[5]))
    # LLM Final → GF
    horiz(_T_LF_X+_T_BW, _T_GF_X, _T_GF_LLM_CY, cllm(lw[6]))

    # ── Connecteurs RL (5 équipes : play-in → SF1 → Final) ───────────────────
    if inc:
        # Play-in → SF1 slot 2 (montée vers le haut)
        if rw[0] is not None:
            pi_mid_x = (_T_QF_X + _T_BW + _T_SF_X) // 2
            ln((_T_QF_X + _T_BW, _T_RF_CY), (pi_mid_x, _T_RF_CY), crl(True))
            ln((pi_mid_x, _T_RF_CY), (pi_mid_x, _T_RL_CY[0]), crl(True))
            ln((pi_mid_x, _T_RL_CY[0]), (_T_SF_X, _T_RL_CY[0]), crl(True))
        else:
            pi_mid_x = (_T_QF_X + _T_BW + _T_SF_X) // 2
            ln((_T_QF_X + _T_BW, _T_RF_CY), (pi_mid_x, _T_RF_CY), crl(False))
            ln((pi_mid_x, _T_RF_CY), (pi_mid_x, _T_RL_CY[0]), crl(False))
            ln((pi_mid_x, _T_RL_CY[0]), (_T_SF_X, _T_RL_CY[0]), crl(False))
        # SF1 + SF2 → RL Final
        pair_conn(_T_SF_X, _T_RL_CY[0], _T_RL_CY[1], _T_LF_X, _T_RF_CY,
                  crl(rw[1] and rw[2]))
        horiz(_T_LF_X+_T_BW, _T_GF_X, _T_GF_RL_CY, crl(rw[3]))

    # ── Connecteurs GF → Champion ──────────────────────────────────────────────
    # ── Connecteur GF → Finaliste → Zenom (toujours visible, s'allume progressivement) ──
    mid_x  = (_T_GF_X + _T_BW + _T_CH_X) // 2
    gf_done = bracket['gf_w'] is not None
    boss_done = bracket['boss_w'] is not None
    c_gf   = C_MENU_BORDER if gf_done else C_DIM
    c_boss = (C_MENU_BORDER if bracket['boss_w'] == bracket['player_idx']
              else ((220,50,50) if not boss_done else (80,30,30)))
    # Y-shape GF → Finaliste
    for gf_cy in [_T_GF_LLM_CY, _T_GF_RL_CY]:
        ln((_T_GF_X+_T_BW, gf_cy), (mid_x, gf_cy), c_gf)
    ln((mid_x, _T_GF_LLM_CY), (mid_x, _T_GF_RL_CY), c_gf)
    ln((mid_x, _T_CH_CY), (_T_CH_X, _T_CH_CY), c_gf)
    # Finaliste → Zenom
    ln((_T_CH_X + _T_CH_W, _T_CH_CY), (_T_ZN_X, _T_ZN_CY), c_boss)

    # ── Fonction dessin boîte ──────────────────────────────────────────────────
    def draw_box(x, y, pidx, mid_id, slot, is_llm=True):
        if pidx is None:
            pygame.draw.rect(screen, C_MENU_BG, (x, y, _T_BW, _T_BH))
            pygame.draw.rect(screen, (50,45,62), (x, y, _T_BW, _T_BH), 1)
            q = f_tiny.render("???", True, (75,68,90))
            screen.blit(q, (x+_T_BW//2-q.get_width()//2, y+_T_BH//2-q.get_height()//2))
            return
        p = parts[pidx]
        mw   = lw[mid_id] if is_llm else rw[mid_id]
        cur  = (player_match is not None and player_match == (('llm' if is_llm else 'rl'), mid_id))
        won  = (mw == pidx)
        lost = (mw is not None and mw != pidx)
        ispl = p['is_player']
        lock = p.get('locked', False)

        if lock:
            bg = (28,28,40);   bdr = (70,65,85);   col_t = (90,85,105)
        elif won:
            bg = (50,40,10);   bdr = C_MENU_BORDER; col_t = (240,200,65)
        elif lost:
            bg = (30,28,42);   bdr = (65,60,80);   col_t = (90,85,105)
        elif ispl:
            pulse = (140,210,255) if (cur and blink) else (90,160,230)
            bg = (20,38,72);   bdr = pulse;          col_t = (130,195,255)
        elif cur and blink:
            bg = (40,35,62);   bdr = C_MENU_BORDER;  col_t = (220,210,185)
        elif is_llm:
            bg = (28,32,68);   bdr = (130,120,155); col_t = (210,205,190)
        else:
            bg = (18,50,38);   bdr = (60,160,100);  col_t = (110,230,165)

        pygame.draw.rect(screen, bg,  (x, y, _T_BW, _T_BH))
        pygame.draw.rect(screen, bdr, (x, y, _T_BW, _T_BH), 2)
        lbl = f_small.render(p['name'], True, col_t)
        mxw = _T_BW - 16
        if lbl.get_width() > mxw:
            sc = mxw/lbl.get_width()
            lbl = pygame.transform.smoothscale(lbl, (int(lbl.get_width()*sc), int(lbl.get_height()*sc)))
        screen.blit(lbl, (x+9, y+_T_BH//2-lbl.get_height()//2))

    # ── Boîtes LLM QF ─────────────────────────────────────────────────────────
    for mid, cy in enumerate(_T_QF_CY):
        ta, tb = _llm_teams(bracket, mid)
        for slot, pidx, yy in [(0,ta,_tb1y(cy)),(1,tb,_tb2y(cy))]:
            draw_box(_T_QF_X, yy, pidx, mid, slot, is_llm=True)

    # ── Boîtes LLM SF ─────────────────────────────────────────────────────────
    for i, cy in enumerate(_T_SF_CY):
        mid = 4 + i
        ta, tb = _llm_teams(bracket, mid)
        for slot, pidx, yy in [(0,ta,_tb1y(cy)),(1,tb,_tb2y(cy))]:
            draw_box(_T_SF_X, yy, pidx, mid, slot, is_llm=True)

    # ── Boîte LLM Final ───────────────────────────────────────────────────────
    ta, tb = _llm_teams(bracket, 6)
    for slot, pidx, yy in [(0,ta,_tb1y(_T_LF_CY)),(1,tb,_tb2y(_T_LF_CY))]:
        draw_box(_T_LF_X, yy, pidx, 6, slot, is_llm=True)

    # ── Boîtes RL (section bas) ───────────────────────────────────────────────
    if inc:
        # Play-in (mid=0) : seed4 vs seed5 à x=_T_QF_X, cy=_T_RF_CY
        ta, tb = _rl_teams(bracket, 0)
        for slot, pidx, yy in [(0,ta,_tb1y(_T_RF_CY)),(1,tb,_tb2y(_T_RF_CY))]:
            draw_box(_T_QF_X, yy, pidx, 0, slot, is_llm=False)
        # SF1 (mid=1) : seed1 vs play-in winner à x=_T_SF_X, cy=_T_RL_CY[0]
        ta, tb = _rl_teams(bracket, 1)
        for slot, pidx, yy in [(0,ta,_tb1y(_T_RL_CY[0])),(1,tb,_tb2y(_T_RL_CY[0]))]:
            draw_box(_T_SF_X, yy, pidx, 1, slot, is_llm=False)
        # SF2 (mid=2) : seed2 vs seed3 à x=_T_SF_X, cy=_T_RL_CY[1]
        ta, tb = _rl_teams(bracket, 2)
        for slot, pidx, yy in [(0,ta,_tb1y(_T_RL_CY[1])),(1,tb,_tb2y(_T_RL_CY[1]))]:
            draw_box(_T_SF_X, yy, pidx, 2, slot, is_llm=False)
        # RL Final (mid=3) à x=_T_LF_X, cy=_T_RF_CY
        ta, tb = _rl_teams(bracket, 3)
        for slot, pidx, yy in [(0,ta,_tb1y(_T_RF_CY)),(1,tb,_tb2y(_T_RF_CY))]:
            draw_box(_T_LF_X, yy, pidx, 3, slot, is_llm=False)
    else:
        for cy in [_T_RF_CY] + _T_RL_CY:
            for yy in [_tb1y(cy), _tb2y(cy)]:
                draw_box(_T_SF_X, yy, None, 0, 0)
        for yy in [_tb1y(_T_RF_CY), _tb2y(_T_RF_CY)]:
            draw_box(_T_LF_X, yy, None, 0, 0)

    # ── Grand Finale ──────────────────────────────────────────────────────────
    gf_llm = lw[6]
    gf_rl  = rw[3] if inc else None
    gf_pm  = (player_match == ('gf', 0))

    for gf_cy, pidx in [((_T_GF_LLM_CY, gf_llm)), ((_T_GF_RL_CY, gf_rl))]:
        cy, p_idx = gf_cy if isinstance(gf_cy, tuple) else (gf_cy, pidx)
        pass

    # GF slot LLM
    if gf_llm is not None:
        p = parts[gf_llm]
        won = (bracket['gf_w'] == gf_llm)
        lost = (bracket['gf_w'] is not None and not won)
        ispl = p['is_player']
        bg  = (42,35,10) if won else ((25,24,36) if lost else ((18,35,65) if ispl else C_MENU_BG))
        bdr = C_MENU_BORDER if (won or (gf_pm and blink)) else ((48,43,60) if lost else ((80,150,220) if ispl else (80,75,95)))
        col_t = (230,190,55) if won else ((60,55,72) if lost else ((110,180,240) if ispl else (160,155,138)))
        yy = _tb1y(_T_GF_LLM_CY)
        pygame.draw.rect(screen, bg,  (_T_GF_X, yy, _T_BW, _T_BH))
        pygame.draw.rect(screen, bdr, (_T_GF_X, yy, _T_BW, _T_BH), 2)
        lbl = f_small.render(p['name'], True, col_t)
        screen.blit(lbl, (_T_GF_X+9, yy+_T_BH//2-lbl.get_height()//2))
    else:
        yy = _tb1y(_T_GF_LLM_CY)
        pygame.draw.rect(screen, C_MENU_BG, (_T_GF_X, yy, _T_BW, _T_BH))
        pygame.draw.rect(screen, (50,45,62), (_T_GF_X, yy, _T_BW, _T_BH), 1)
        q = f_tiny.render("???", True, (75,68,90))
        screen.blit(q, (_T_GF_X+_T_BW//2-q.get_width()//2, yy+_T_BH//2-q.get_height()//2))

    if inc:
        if gf_rl is not None:
            p = parts[gf_rl]
            won = (bracket['gf_w'] == gf_rl)
            lost = (bracket['gf_w'] is not None and not won)
            bg  = (42,35,10) if won else ((25,24,36) if lost else (15,42,32))
            bdr = (55,170,110) if (won or (gf_pm and blink)) else ((48,43,60) if lost else (28,72,50))
            col_t = (130,255,180) if won else ((60,55,72) if lost else (90,210,150))
            yy = _tb1y(_T_GF_RL_CY)
            pygame.draw.rect(screen, bg,  (_T_GF_X, yy, _T_BW, _T_BH))
            pygame.draw.rect(screen, bdr, (_T_GF_X, yy, _T_BW, _T_BH), 2)
            lbl = f_small.render(p['name'], True, col_t)
            screen.blit(lbl, (_T_GF_X+9, yy+_T_BH//2-lbl.get_height()//2))
        else:
            yy = _tb1y(_T_GF_RL_CY)
            pygame.draw.rect(screen, (15,42,32), (_T_GF_X, yy, _T_BW, _T_BH))
            pygame.draw.rect(screen, (28,72,50), (_T_GF_X, yy, _T_BW, _T_BH), 1)
            q = f_tiny.render("???", True, (60,120,80))
            screen.blit(q, (_T_GF_X+_T_BW//2-q.get_width()//2, yy+_T_BH//2-q.get_height()//2))

    # ── Intermédiaire : vainqueur GF (avant Zenom) ────────────────────────────
    gf_champ_idx = bracket['gf_w'] if inc else lw[6]
    gf_champ_name = parts[gf_champ_idx]['name'] if gf_champ_idx is not None else None
    cy_top = _T_CH_CY - _T_CH_H // 2
    pygame.draw.rect(screen, (38,30,8) if gf_champ_name else C_MENU_BG,
                     (_T_CH_X, cy_top, _T_CH_W, _T_CH_H))
    cbdr = C_MENU_BORDER if gf_champ_name else (55,48,20)
    pygame.draw.rect(screen, cbdr, (_T_CH_X, cy_top, _T_CH_W, _T_CH_H), 2)
    cl2 = f_tiny.render("FINALISTE", True, cbdr)
    screen.blit(cl2, (_T_CH_X+_T_CH_W//2-cl2.get_width()//2, cy_top+8))
    cn = f_menu.render(gf_champ_name or "???", True,
                       (255,225,80) if gf_champ_name else (75,68,90))
    if cn.get_width() > _T_CH_W - 12:
        sc = (_T_CH_W-12)/cn.get_width()
        cn = pygame.transform.smoothscale(cn,(int(cn.get_width()*sc),int(cn.get_height()*sc)))
    screen.blit(cn, (_T_CH_X+_T_CH_W//2-cn.get_width()//2, cy_top+32))

    # ── Connecteur Finaliste → Zenom ──────────────────────────────────────────
    zenom_idx = next((i for i,p in enumerate(parts) if p.get('is_boss')), None)

    # ── Zenom — boss final ─────────────────────────────────────────────────────
    bw       = bracket['boss_w']
    zn_yy    = _tb1y(_T_ZN_CY)
    pi_local = bracket['player_idx']
    gf_pm    = (player_match == ('boss', 0))
    if bw is None:
        zn_bg  = (42, 8, 8);    zn_bdr = (180,40,40) if not (gf_pm and blink) else (255,80,60)
        zn_col = (220,80,60)
    elif bw == pi_local:
        zn_bg  = (28,26,38);    zn_bdr = (48,43,60);  zn_col = (60,55,72)
    else:
        zn_bg  = (42, 8, 8);    zn_bdr = (220,50,50); zn_col = (255,100,80)
    pygame.draw.rect(screen, zn_bg,  (_T_ZN_X, zn_yy, _T_ZN_W, _T_BH))
    pygame.draw.rect(screen, zn_bdr, (_T_ZN_X, zn_yy, _T_ZN_W, _T_BH), 2)
    zn_lbl = f_small.render("ZENOM", True, zn_col)
    screen.blit(zn_lbl, (_T_ZN_X + _T_ZN_W//2 - zn_lbl.get_width()//2,
                          zn_yy + _T_BH//2 - zn_lbl.get_height()//2))
    zn_hdr = f_tiny.render("BOSS FINAL", True, zn_bdr)
    screen.blit(zn_hdr, (_T_ZN_X + _T_ZN_W//2 - zn_hdr.get_width()//2, zn_yy - 18))

    # ── Champion Absolu (après Zenom) ─────────────────────────────────────────
    ult_x = _T_ZN_X + _T_ZN_W + 30
    if bw == pi_local:
        ult_lbl = f_menu.render("CHAMPION", True, (255,225,80))
        screen.blit(ult_lbl, (ult_x, _T_ZN_CY - ult_lbl.get_height()//2))
        ult_sub = f_tiny.render("ABSOLU", True, (255,190,50))
        screen.blit(ult_sub, (ult_x, _T_ZN_CY + ult_lbl.get_height()//2 - 4))

    # ── Labels rounds LLM (au-dessus du bracket LLM) ──────────────────────────
    for lbl, cx in [("QUARTS", _T_QF_X+_T_BW//2), ("DEMIS", _T_SF_X+_T_BW//2),
                    ("FINALE", _T_LF_X+_T_BW//2), ("GF", _T_GF_X+_T_BW//2)]:
        s = f_tiny.render(lbl, True, (170,155,195))
        screen.blit(s, (cx-s.get_width()//2, 210))

    # CONF. LLM — en haut à gauche, juste au-dessus du premier QF
    s = f_tiny.render("CONF. LLM", True, (210,175,60))
    screen.blit(s, (_T_QF_X, 222))

    if inc:
        # Labels rounds RL (juste sous le séparateur, même colonnes)
        rl_lbl_y = _T_SEP_Y + 8
        for lbl, cx in [("PLAY-IN", _T_QF_X+_T_BW//2),
                         ("DEMIS",   _T_SF_X+_T_BW//2),
                         ("FINALE",  _T_LF_X+_T_BW//2)]:
            s = f_tiny.render(lbl, True, (90,210,145))
            screen.blit(s, (cx-s.get_width()//2, rl_lbl_y))

        # CONF. RL — en bas à gauche, juste au-dessus du play-in
        playin_top = _tb1y(_T_RF_CY) - 18
        s = f_tiny.render("CONF. RL", True, (90,215,150))
        screen.blit(s, (_T_QF_X, playin_top))

    # ── Séparateur ────────────────────────────────────────────────────────────
    pygame.draw.line(screen, (55,50,68), (0, _T_SEP_Y), (SCREEN_W, _T_SEP_Y), 1)

    # ── UI bas ────────────────────────────────────────────────────────────────
    if phase == 'pre' and player_match is not None:
        conf, mid = player_match
        if conf == 'llm':
            ta, tb = _llm_teams(bracket, mid)
            opp = parts[tb if ta == pi else ta]['name']
        elif conf == 'gf':
            opp = parts[rw[2]]['name']
        else:  # boss
            opp = "ZENOM"
        msg = f_small.render(f"PROCHAIN ADVERSAIRE : {opp}", True,
                             (255,80,60) if conf == 'boss' else C_SEL)
        screen.blit(msg, (SCREEN_W//2-msg.get_width()//2, 990))
        hint = f_tiny.render("ENTREE pour lancer le match", True, C_HINT)
        screen.blit(hint, (SCREEN_W//2-hint.get_width()//2, 1030))
    elif phase == 'post':
        col_r = (230,190,55) if last_res=='win' else (200,60,50)
        msg = f_menu.render("VICTOIRE !" if last_res=='win' else "DEFAITE", True, col_r)
        screen.blit(msg, (SCREEN_W//2-msg.get_width()//2, 990))
        hint = f_tiny.render("ENTREE pour continuer", True, C_HINT)
        screen.blit(hint, (SCREEN_W//2-hint.get_width()//2, 1030))
    elif phase in ('champion', 'eliminated'):
        col_r = (255,225,80) if phase=='champion' else (180,60,50)
        txt   = "CHAMPION ABSOLU !" if phase=='champion' else "ELIMINE"
        msg = f_menu.render(txt, True, col_r)
        screen.blit(msg, (SCREEN_W//2-msg.get_width()//2, 990))
        hint = f_tiny.render("ENTREE pour retourner au menu", True, C_HINT)
        screen.blit(hint, (SCREEN_W//2-hint.get_width()//2, 1030))


def _reload_fonts():
    try:
        ft=pygame.font.Font(FONT_PATH,42); fm=pygame.font.Font(FONT_PATH,15)
        fs=pygame.font.Font(FONT_PATH,11); fti=pygame.font.Font(FONT_PATH,9)
    except Exception:
        ft=pygame.font.SysFont(None,64); fm=pygame.font.SysFont(None,28)
        fs=pygame.font.SysFont(None,22); fti=pygame.font.SysFont(None,18)
    return ft, fm, fs, fti


def run_tournament_loop(player_fac_idx, player_champ_letter, bag_size=11):
    global _bg_surface
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.SCALED | pygame.RESIZABLE)
    pygame.display.set_caption("DDM - Tournoi")
    clock  = pygame.time.Clock()
    fonts  = _reload_fonts()
    _bg_surface = None

    factions = load_factions()
    bracket  = _generate_tournament(factions, player_fac_idx, player_champ_letter, include_rl=True)
    phase    = 'pre'
    last_res = None
    t0       = time.time()

    while True:
        t = time.time() - t0
        player_match = _find_player_match(bracket)

        if player_match is None and phase not in ('champion', 'eliminated', 'post'):
            pi = bracket['player_idx']
            if bracket['boss_w'] == pi:
                phase = 'champion'    # a battu Zenom → champion absolu
            elif bracket['boss_w'] is not None:
                phase = 'eliminated'  # Zenom l'a emporté
            else:
                phase = 'eliminated'  # éliminé avant le boss

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); return
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    if phase == 'pre' and player_match is not None:
                        conf, mid = player_match
                        pi = bracket['player_idx']

                        if conf == 'llm':
                            ta, tb = _llm_teams(bracket, mid)
                            is_a   = (ta == pi)
                            opp    = bracket['parts'][tb if is_a else ta]
                        elif conf == 'gf':
                            rl_fin = bracket['rl_w'][3]
                            opp    = bracket['parts'][rl_fin]
                            is_a   = True
                        else:  # boss
                            zenom_idx = next(i for i,p in enumerate(bracket['parts']) if p.get('is_boss'))
                            opp    = bracket['parts'][zenom_idx]
                            is_a   = True

                        screen.fill((12,10,22))
                        _m = fonts[2].render("LANCEMENT DU MATCH...", True, C_TITLE)
                        screen.blit(_m, ((SCREEN_W-_m.get_width())//2, SCREEN_H//2-15))
                        pygame.display.flip(); time.sleep(0.4)
                        pygame.quit()

                        p_fac = factions[player_fac_idx]['id']
                        if is_a:
                            result = _run_match_blocking(p_fac, player_champ_letter,
                                                         opp['faction_id'], opp['champ'],
                                                         bag_size, opp['ai_profile'])
                            player_won = (result == 'A')
                        else:
                            result = _run_match_blocking(opp['faction_id'], opp['champ'],
                                                         p_fac, player_champ_letter,
                                                         bag_size, opp['ai_profile'])
                            player_won = (result == 'B')

                        if conf == 'llm':
                            w_idx = pi if player_won else (tb if is_a else ta)
                            bracket['llm_w'][mid] = w_idx
                            _resolve_round_ai(bracket, player_match)
                        elif conf == 'gf':
                            bracket['gf_w'] = pi if player_won else bracket['rl_w'][2]
                        else:  # boss
                            zenom_idx = next(i for i,p in enumerate(bracket['parts']) if p.get('is_boss'))
                            bracket['boss_w'] = pi if player_won else zenom_idx

                        last_res = 'win' if player_won else 'loss'
                        if last_res == 'loss':
                            _finalize_bracket(bracket)

                        pygame.init()
                        screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.SCALED | pygame.RESIZABLE)
                        pygame.display.set_caption("DDM - Tournoi")
                        clock  = pygame.time.Clock()
                        fonts  = _reload_fonts()
                        _bg_surface = None
                        phase = 'post'; t0 = time.time()

                    elif phase == 'post':
                        phase = 'eliminated' if last_res == 'loss' else 'pre'
                    elif phase in ('champion', 'eliminated'):
                        pygame.quit(); return

        draw_background(screen)
        draw_banner(screen, fonts[0], t)
        title = fonts[1].render("MODE TOURNOI", True, C_TITLE)
        screen.blit(title, (SCREEN_W//2-title.get_width()//2, 88))
        _draw_tourn_bracket(screen, fonts, bracket, player_match, phase, last_res, t)
        pygame.display.flip()
        clock.tick(FPS)


def _placeholder(screen, fonts, clock, msg):
    f_title, f_menu, f_small, f_tiny = fonts
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN):
                return
        screen.fill((15,12,25))
        t = f_menu.render(msg, True, C_TITLE)
        screen.blit(t, ((SCREEN_W-t.get_width())//2, (SCREEN_H-t.get_height())//2))
        h = f_small.render("ESC pour revenir", True, C_UNSEL)
        screen.blit(h, ((SCREEN_W-h.get_width())//2, SCREEN_H//2+40))
        pygame.display.flip()
        clock.tick(FPS)


if __name__ == "__main__":
    main()
