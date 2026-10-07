"""
ddm_encyclopedia.py — Encyclopédie des factions DDM
← → (ou flèches) pour naviguer entre les 8 factions
Clic sur une fiche  → panneau détail en bas
ESC / clic vide      → fermer le détail
"""
import pygame, sys, os, json, re, unicodedata

_DDM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH    = os.path.join(_DDM_ROOT, "assets", "PressStart2P-Regular.ttf")
FACTIONS_JSON= os.path.join(_DDM_ROOT, "data", "Data_8_Factions.json")
SPRITES_ROOT = os.path.join(_DDM_ROOT, "assets", "sprites")
MISSING_PNG  = os.path.join(SPRITES_ROOT, "_ui", "missing.png")

SCREEN_W, SCREEN_H = 1920, 1080
FPS = 60

# ── Palette ───────────────────────────────────────────────────────────────────
C_BG         = (14, 12, 26)
C_HDR_BG     = (20, 16, 38)
C_CHAMP_BG   = (22, 20, 44)
C_CHAMP_BDR  = (120, 100, 160)
C_UNIT_BG    = (20, 24, 50)
C_UNIT_BDR   = (55, 50, 75)
C_UNIT_HOV   = (28, 32, 65)
C_UNIT_SEL   = (35, 30, 68)
C_UNIT_BDR_S = (200, 160, 50)
C_DET_BG     = (16, 14, 32)
C_DET_BDR    = (200, 160, 50)
C_TITLE      = (200, 160, 50)
C_TXT        = (210, 200, 180)
C_TXT_DIM    = (110, 100, 130)
C_LBL        = (130, 120, 150)
C_ATK        = (220, 80,  60)
C_DEF        = (60,  140, 220)
C_HP         = (80,  200, 100)
C_NAV        = (170, 150, 200)
C_SEP        = (45,  40,  62)
C_LV = {1: (160,160,175), 2: (100,200,120), 3:(80,140,255), 4:(220,90,80), 5:(60,40,40)}
C_LV_BG = {1:(22,24,30), 2:(18,30,20), 3:(18,22,38), 4:(30,18,18), 5:(20,14,14)}

# ── Layout ────────────────────────────────────────────────────────────────────
HDR_H    = 92    # faction nom + nav
CHAMP_H  = 208   # strip champions
SEP1_Y   = HDR_H + CHAMP_H          # 300
UNIT_H   = 555   # zone unités
DET_Y    = SEP1_Y + UNIT_H          # 855
DET_H    = SCREEN_H - DET_Y         # 225

COL_W    = SCREEN_W // 5            # 384 par colonne niveau
CARD_W   = 340
CARD_H   = 155
SPR_SZ   = 100                      # sprite dans fiche unité
CH_W     = 338
CH_H     = 195
CH_SPR   = 88

_spr_cache = {}

# ── Sprite helpers (copiés du renderer) ──────────────────────────────────────
def slugify(t):
    t = t.lower().strip()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")

def fac_slug(s):
    if not s: return ""
    part = s.split("–")[0].split("-")[0].strip().lower()
    part = unicodedata.normalize("NFD", part)
    part = "".join(c for c in part if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", part).strip("_")

def _ph(w, h):
    s = pygame.Surface((w, h)); s.fill((40, 20, 60)); return s

def load_spr(faction, niveau, nom, lettre, tw, th):
    if not faction or not nom: return _ph(tw, th)
    slug = slugify(nom)
    fn = (f"{faction}_champion_{lettre.lower()}_{slug}.png"
          if lettre else f"{faction}_lv{niveau}_{slug}.png")
    key = f"{fn}_{tw}_{th}"
    if key in _spr_cache: return _spr_cache[key]
    path = os.path.join(SPRITES_ROOT, faction, fn)
    if not os.path.isfile(path):
        path = MISSING_PNG
    try:
        src = pygame.image.load(path).convert()
        sw, sh = src.get_size()
        r = min((tw * .88) / sw, (th * .88) / sh)
        s = pygame.transform.scale(src, (max(1, int(sw*r)), max(1, int(sh*r))))
    except:
        s = _ph(tw, th)
    _spr_cache[key] = s; return s

def find_champ_sprite(faction_str, nom):
    slug = slugify(nom); fac = fac_slug(faction_str)
    fac_dir = os.path.join(SPRITES_ROOT, fac)
    if not os.path.isdir(fac_dir): return MISSING_PNG
    for fname in os.listdir(fac_dir):
        if "champion" in fname and slug in fname:
            return os.path.join(fac_dir, fname)
    return MISSING_PNG

def load_champ_spr(faction_str, nom, tw, th):
    key = f"champ_{slugify(nom)}_{tw}_{th}"
    if key in _spr_cache: return _spr_cache[key]
    path = find_champ_sprite(faction_str, nom)
    try:
        src = pygame.image.load(path).convert()
        sw, sh = src.get_size()
        r = min((tw * .88) / sw, (th * .88) / sh)
        s = pygame.transform.scale(src, (max(1, int(sw*r)), max(1, int(sh*r))))
    except:
        s = _ph(tw, th)
    _spr_cache[key] = s; return s

# ── Font helper ───────────────────────────────────────────────────────────────
def load_font(sz):
    try: return pygame.font.Font(FONT_PATH, sz)
    except: return pygame.font.SysFont("consolas", sz)

# ── Texte avec retour à la ligne ──────────────────────────────────────────────
def draw_wrapped(surf, font, text, x, y, max_w, color, line_h=None):
    if line_h is None: line_h = font.get_height() + 3
    words = text.split()
    line = ""
    cy = y
    for w in words:
        test = line + (" " if line else "") + w
        if font.size(test)[0] <= max_w:
            line = test
        else:
            if line:
                s = font.render(line, True, color)
                surf.blit(s, (x, cy)); cy += line_h
            line = w
    if line:
        s = font.render(line, True, color)
        surf.blit(s, (x, cy))
    return cy + line_h

# ── Dessin fiche unité ────────────────────────────────────────────────────────
def draw_unit_card(surf, fonts, x, y, unit, fac_nom, selected, hover):
    fs, ft = fonts
    lv = unit.get("niveau", 1)
    bg  = C_UNIT_SEL if selected else (C_UNIT_HOV if hover else C_LV_BG.get(lv, C_UNIT_BG))
    bdr = C_UNIT_BDR_S if selected else (C_LV.get(lv, C_UNIT_BDR) if hover else C_UNIT_BDR)
    pygame.draw.rect(surf, bg,  (x, y, CARD_W, CARD_H))
    pygame.draw.rect(surf, bdr, (x, y, CARD_W, CARD_H), 2)

    # Sprite
    spr = load_spr(fac_slug(fac_nom), lv, unit["nom"], "", SPR_SZ, SPR_SZ)
    sx  = x + 8; sy = y + (CARD_H - spr.get_height()) // 2
    surf.blit(spr, (sx, sy))

    # Infos
    tx = x + SPR_SZ + 16
    nom = unit["nom"]
    if len(nom) > 18: nom = nom[:17] + "."
    n = fs.render(nom, True, C_TXT)
    if n.get_width() > CARD_W - SPR_SZ - 24:
        sc = (CARD_W - SPR_SZ - 24) / n.get_width()
        n = pygame.transform.smoothscale(n, (int(n.get_width()*sc), int(n.get_height()*sc)))
    surf.blit(n, (tx, y + 12))

    stats = unit.get("stats", {})
    for i, (key, col) in enumerate([("ATK", C_ATK), ("DEF", C_DEF), ("HP", C_HP)]):
        val = stats.get(key, "?")
        lbl = ft.render(f"{key}", True, C_LBL)
        val_s = fs.render(str(val), True, col)
        vy = y + 50 + i * 32
        surf.blit(lbl, (tx, vy))
        surf.blit(val_s, (tx + 44, vy - 2))

    return pygame.Rect(x, y, CARD_W, CARD_H)

# ── Dessin fiche champion ─────────────────────────────────────────────────────
def draw_champ_card(surf, fonts, x, y, champ, fac_nom, selected, hover):
    fs, ft = fonts
    bg  = C_UNIT_SEL if selected else ((32, 28, 58) if hover else C_CHAMP_BG)
    bdr = C_UNIT_BDR_S if selected else ((180, 140, 220) if hover else C_CHAMP_BDR)
    pygame.draw.rect(surf, bg,  (x, y, CH_W, CH_H))
    pygame.draw.rect(surf, bdr, (x, y, CH_W, CH_H), 2)

    # Badge lettre
    badge = fs.render(champ.get("lettre", "?"), True, bdr)
    surf.blit(badge, (x + 8, y + 8))

    # Sprite
    spr = load_champ_spr(fac_nom, champ["nom"], CH_SPR, CH_SPR)
    surf.blit(spr, (x + CH_W - spr.get_width() - 8,
                    y + CH_H // 2 - spr.get_height() // 2))

    # Nom
    nom = champ["nom"]
    n = ft.render(nom, True, C_TXT)
    if n.get_width() > CH_W - CH_SPR - 30:
        sc = (CH_W - CH_SPR - 30) / n.get_width()
        n = pygame.transform.smoothscale(n, (int(n.get_width()*sc), int(n.get_height()*sc)))
    surf.blit(n, (x + 8, y + 30))

    # Rôle
    role = champ.get("role", "")[:35]
    r = ft.render(role, True, C_TXT_DIM)
    if r.get_width() > CH_W - CH_SPR - 30:
        sc = (CH_W - CH_SPR - 30) / r.get_width()
        r = pygame.transform.smoothscale(r, (int(r.get_width()*sc), int(r.get_height()*sc)))
    surf.blit(r, (x + 8, y + 52))

    # Stats
    stats = champ.get("stats", {})
    for i, (key, col) in enumerate([("ATK", C_ATK), ("DEF", C_DEF), ("HP", C_HP)]):
        s = ft.render(f"{key} {stats.get(key,'?')}", True, col)
        surf.blit(s, (x + 8 + i * 90, y + CH_H - 28))

    return pygame.Rect(x, y, CH_W, CH_H)

# ── Panneau détail ────────────────────────────────────────────────────────────
def draw_detail(surf, fonts, item, fac_nom, is_champ):
    f_title, fs, ft = fonts
    pygame.draw.rect(surf, C_DET_BG,  (0, DET_Y, SCREEN_W, DET_H))
    pygame.draw.rect(surf, C_DET_BDR, (0, DET_Y, SCREEN_W, DET_H), 2)
    pygame.draw.line(surf, C_DET_BDR, (0, DET_Y), (SCREEN_W, DET_Y), 2)

    # Grand sprite
    if is_champ:
        spr = load_champ_spr(fac_nom, item["nom"], 130, 130)
    else:
        spr = load_spr(fac_slug(fac_nom), item.get("niveau", 1), item["nom"], "", 130, 130)
    surf.blit(spr, (20, DET_Y + DET_H // 2 - spr.get_height() // 2))

    tx = 170
    # Nom
    nom_s = fs.render(item["nom"], True, C_TITLE)
    surf.blit(nom_s, (tx, DET_Y + 10))

    # Stats
    stats = item.get("stats", {})
    for i, (key, col) in enumerate([("ATK", C_ATK), ("DEF", C_DEF), ("HP", C_HP)]):
        lbl = ft.render(key, True, C_LBL)
        val = fs.render(str(stats.get(key, "?")), True, col)
        sx2 = tx + i * 140
        surf.blit(lbl, (sx2, DET_Y + 42))
        surf.blit(val, (sx2 + 40, DET_Y + 38))

    if is_champ:
        role_s = ft.render(item.get("role", ""), True, C_TXT_DIM)
        surf.blit(role_s, (tx, DET_Y + 68))

    # Capacité
    cap_label = ft.render("Capacité :", True, C_LBL)
    surf.blit(cap_label, (tx, DET_Y + 92))
    cap_text = item.get("action_speciale", "—")
    draw_wrapped(surf, ft, cap_text, tx, DET_Y + 112, SCREEN_W - tx - 20, C_TXT, line_h=18)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("DDM — Encyclopédie")
    clock = pygame.time.Clock()

    f_title = load_font(36)
    f_small = load_font(17)
    f_tiny  = load_font(13)
    fonts_card   = (f_small, f_tiny)
    fonts_detail = (f_title, f_small, f_tiny)

    with open(FACTIONS_JSON, encoding="utf-8") as f:
        data = json.load(f)
    factions = data["factions"]

    fac_idx  = 0
    selected = None   # (type 'unit'|'champ', item_dict)

    def current():
        return factions[fac_idx]

    running = True
    while running:
        fac      = current()
        fac_nom  = fac["nom"]
        fac_s    = fac_slug(fac_nom)
        champions= fac.get("champions", [])
        monstres = fac.get("monstres", [])
        by_level = {lv: [] for lv in range(1, 6)}
        for m in monstres:
            lv = m.get("niveau", 1)
            if 1 <= lv <= 5:
                by_level[lv].append(m)

        mx, my = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if selected: selected = None
                    else: running = False
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    fac_idx = (fac_idx - 1) % len(factions)
                    selected = None
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    fac_idx = (fac_idx + 1) % len(factions)
                    selected = None
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                clicked_something = False
                # Champions
                n_ch = len(champions)
                total_ch_w = min(n_ch, 5) * (CH_W + 12)
                ch_start_x = (SCREEN_W - total_ch_w) // 2
                for i, ch in enumerate(champions[:5]):
                    cx = ch_start_x + i * (CH_W + 12)
                    cy = HDR_H + 8
                    r = pygame.Rect(cx, cy, CH_W, CH_H)
                    if r.collidepoint(mx, my):
                        selected = ("champ", ch) if selected != ("champ", ch) else None
                        clicked_something = True; break
                if not clicked_something:
                    # Unités
                    for lv in range(1, 6):
                        col_x   = (lv - 1) * COL_W + (COL_W - CARD_W) // 2
                        units   = by_level[lv]
                        for j, unit in enumerate(units):
                            uy = SEP1_Y + 38 + j * (CARD_H + 8)
                            if uy + CARD_H > DET_Y - 4: break
                            r = pygame.Rect(col_x, uy, CARD_W, CARD_H)
                            if r.collidepoint(mx, my):
                                selected = ("unit", unit) if selected != ("unit", unit) else None
                                clicked_something = True; break
                if not clicked_something and my < DET_Y:
                    selected = None
                # Nav arrows
                if pygame.Rect(20, HDR_H//2-20, 50, 40).collidepoint(mx, my):
                    fac_idx = (fac_idx-1) % len(factions); selected = None
                if pygame.Rect(SCREEN_W-270, HDR_H//2-20, 50, 40).collidepoint(mx, my):
                    fac_idx = (fac_idx+1) % len(factions); selected = None
                # Bouton RETOUR
                if pygame.Rect(SCREEN_W-200, HDR_H//2-22, 185, 44).collidepoint(mx, my):
                    running = False

        # ── Dessin ────────────────────────────────────────────────────────────
        screen.fill(C_BG)

        # Header faction
        pygame.draw.rect(screen, C_HDR_BG, (0, 0, SCREEN_W, HDR_H))
        nom_court = fac_nom.split("–")[0].strip()
        t = f_title.render(nom_court.upper(), True, C_TITLE)
        screen.blit(t, (SCREEN_W//2 - t.get_width()//2, HDR_H//2 - t.get_height()//2))
        # nav index
        idx_t = f_tiny.render(f"{fac_idx+1} / {len(factions)}", True, C_LBL)
        screen.blit(idx_t, (SCREEN_W//2 - idx_t.get_width()//2, HDR_H - 18))
        # Flèches nav (◄ gauche, ► décalé pour laisser place au bouton)
        for txt, rx in [("◄", 20), ("►", SCREEN_W-270)]:
            ar = pygame.Rect(rx, HDR_H//2-20, 50, 40)
            hov_ar = ar.collidepoint(mx, my)
            pygame.draw.rect(screen, (35,30,55) if hov_ar else (25,22,42), ar)
            pygame.draw.rect(screen, C_NAV, ar, 1)
            a = f_small.render(txt, True, C_NAV)
            screen.blit(a, (rx + 25 - a.get_width()//2, HDR_H//2 - a.get_height()//2))

        # Bouton RETOUR
        btn_r = pygame.Rect(SCREEN_W-200, HDR_H//2-22, 185, 44)
        hov_btn = btn_r.collidepoint(mx, my)
        pygame.draw.rect(screen, (45,20,20) if hov_btn else (30,14,14), btn_r)
        pygame.draw.rect(screen, (200,70,50) if hov_btn else (140,50,35), btn_r, 2)
        rb = f_small.render("◄ MENU", True, (220,100,80) if hov_btn else (170,70,55))
        screen.blit(rb, (btn_r.centerx - rb.get_width()//2,
                         btn_r.centery - rb.get_height()//2))

        # Zone champions
        pygame.draw.rect(screen, C_CHAMP_BG, (0, HDR_H, SCREEN_W, CHAMP_H))
        n_ch = len(champions)
        total_ch_w = min(n_ch, 5) * (CH_W + 12) - 12
        ch_start_x = (SCREEN_W - total_ch_w) // 2
        for i, ch in enumerate(champions[:5]):
            cx = ch_start_x + i * (CH_W + 12)
            cy = HDR_H + 8
            sel = (selected == ("champ", ch))
            hov = pygame.Rect(cx, cy, CH_W, CH_H).collidepoint(mx, my)
            draw_champ_card(screen, fonts_card, cx, cy, ch, fac_nom, sel, hov)

        # Séparateur
        pygame.draw.line(screen, C_SEP, (0, SEP1_Y), (SCREEN_W, SEP1_Y), 1)

        # Labels niveaux
        for lv in range(1, 6):
            cx = (lv-1)*COL_W + COL_W//2
            col_bdr = C_LV.get(lv, C_LBL)
            lbl = f_small.render(f"NIVEAU {lv}", True, col_bdr)
            screen.blit(lbl, (cx - lbl.get_width()//2, SEP1_Y + 10))
            # Séparateur vertical entre colonnes
            if lv < 5:
                pygame.draw.line(screen, (35,32,52),
                                 (lv*COL_W, SEP1_Y+1), (lv*COL_W, DET_Y-1), 1)

        # Fiches unités
        for lv in range(1, 6):
            col_x = (lv-1)*COL_W + (COL_W-CARD_W)//2
            for j, unit in enumerate(by_level[lv]):
                uy = SEP1_Y + 38 + j*(CARD_H+8)
                if uy + CARD_H > DET_Y - 4: break
                sel = (selected == ("unit", unit))
                hov = pygame.Rect(col_x, uy, CARD_W, CARD_H).collidepoint(mx, my)
                draw_unit_card(screen, fonts_card, col_x, uy, unit, fac_nom, sel, hov)

        # Panneau détail
        if selected:
            kind, item = selected
            draw_detail(screen, fonts_detail, item, fac_nom, kind == "champ")

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
