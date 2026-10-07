"""
ddm_bracket.py — Bracket DDM : Upper (LLM) + Lower (RL) + Grand Finale
python ddm_bracket.py   |   Clic = qualifier   R = nouveau tirage   ESC = quitter
"""
import pygame, sys, random

import os
_DDM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(_DDM_ROOT, "assets", "PressStart2P-Regular.ttf")
SCREEN_W, SCREEN_H = 1920, 1080
FPS = 60

# ── Palette ───────────────────────────────────────────────────────────────────
C_BG          = (18, 14, 32)
C_SEP         = (55, 50, 68)
C_TITLE       = (200, 160, 50)
C_LBL         = (80, 72, 95)
C_HINT        = (100, 92, 115)

# LLM — or/gold
C_UB_BOX      = (22, 26, 58)
C_UB_WIN      = (42, 35, 10)
C_UB_HOV      = (30, 34, 72)
C_UB_BDR      = (200, 160, 50)
C_UB_BDR_DIM  = (55, 48, 20)
C_UB_TXT      = (200, 190, 165)
C_UB_TXT_WIN  = (230, 190, 55)
C_UB_TXT_DIM  = (75, 68, 90)
C_SEED        = (100, 92, 115)
C_LINE_UB     = (65, 58, 82)
C_LINE_UB_W   = (150, 120, 35)

# RL — vert
C_RL_BOX      = (15, 42, 32)
C_RL_WIN      = (20, 60, 44)
C_RL_HOV      = (18, 52, 40)
C_RL_BDR      = (55, 170, 110)
C_RL_BDR_DIM  = (28, 72, 50)
C_RL_TXT      = (90, 210, 150)
C_RL_TXT_WIN  = (130, 255, 180)
C_LINE_LB     = (35, 80, 58)
C_LINE_LB_W   = (70, 180, 120)

# GF — violet
C_GF_BOX      = (28, 20, 48)
C_GF_HOV      = (38, 28, 60)
C_GF_BDR      = (175, 88, 220)
C_GF_BDR_DIM  = (80, 40, 110)
C_GF_TXT      = (210, 140, 255)
C_GF_TXT_WIN  = (235, 180, 255)
C_LINE_GF     = (120, 58, 160)
C_LINE_GF_W   = (180, 100, 220)

# Champion
C_CHAMP_BG    = (38, 30, 8)
C_CHAMP_BDR   = (220, 185, 65)
C_CHAMP_TXT   = (255, 225, 80)

# ── Layout ────────────────────────────────────────────────────────────────────
BOX_W, BOX_H, GAP = 200, 40, 8

# Colonnes X
QF_X, SF_X, UBF_X = 80, 335, 590
LBQ_X, LBF_X      = 80, 335
GF_X               = 1480

SEPARATOR_Y = 518

# Centres Y des matchups (cy = milieu entre les deux équipes)
UB_QF_CY  = [158, 252, 362, 456]
UB_SF_CY  = [(UB_QF_CY[0]+UB_QF_CY[1])//2, (UB_QF_CY[2]+UB_QF_CY[3])//2]
UB_UBF_CY = (UB_SF_CY[0] + UB_SF_CY[1]) // 2

LB_CY  = [648, 832]
LBF_CY = (LB_CY[0] + LB_CY[1]) // 2

# GF : les deux finalistes straddlent le séparateur
GF_UB_Y  = SEPARATOR_Y - GAP - BOX_H   # 470  ← finaliste UB (haut)
GF_LB_Y  = SEPARATOR_Y + GAP           # 526  ← finaliste LB (bas)
GF_UB_CY = GF_UB_Y + BOX_H // 2       # 490
GF_LB_CY = GF_LB_Y + BOX_H // 2       # 546

# Champion (à droite du GF, centré sur le séparateur)
CHAMP_W, CHAMP_H = 190, 96
CHAMP_X  = GF_X + BOX_W + 25           # 1705
CHAMP_Y  = SEPARATOR_Y - CHAMP_H // 2  # 470

# Données
LLM_NAMES = ["GREEDY", "HAIKU", "GEMINI", "CHATGPT",
             "MISTRAL", "GROK",  "SONNET", "OPUS"]
RL_NAMES  = ["JIN", "JIO", "CROSS", "JAEHA"]


# ── Utilitaires ───────────────────────────────────────────────────────────────
def t1y(cy): return cy - GAP // 2 - BOX_H   # top de l'équipe 1
def t2y(cy): return cy + GAP // 2            # top de l'équipe 2

def load_font(size):
    try:    return pygame.font.Font(FONT_PATH, size)
    except: return pygame.font.SysFont("consolas", size)


def draw_box(surf, fs, ft, x, y, label, seed=None,
             winner=False, hover=False, tbd=False, style="llm"):
    if style == "rl":
        bg  = C_RL_WIN  if winner else (C_RL_HOV  if hover else C_RL_BOX)
        bdr = C_RL_BDR  if (winner or hover) else C_RL_BDR_DIM
        col = C_RL_TXT_WIN if winner else C_RL_TXT
        dim = C_RL_TXT
    elif style == "gf":
        bg  = C_GF_HOV  if hover  else C_GF_BOX
        bdr = C_GF_BDR  if (winner or hover) else C_GF_BDR_DIM
        col = C_GF_TXT_WIN if winner else C_GF_TXT
        dim = C_GF_TXT
    else:  # llm
        bg  = C_UB_WIN  if winner else (C_UB_HOV  if hover else C_UB_BOX)
        bdr = C_UB_BDR  if (winner or hover) else C_UB_BDR_DIM
        col = C_UB_TXT_WIN if winner else C_UB_TXT
        dim = C_UB_TXT_DIM

    pygame.draw.rect(surf, bg,  (x, y, BOX_W, BOX_H))
    pygame.draw.rect(surf, bdr, (x, y, BOX_W, BOX_H), 2)

    if tbd:
        q = ft.render("???", True, dim)
        surf.blit(q, (x + BOX_W//2 - q.get_width()//2,
                      y + BOX_H//2 - q.get_height()//2))
        return

    tx = x + 10
    if seed is not None:
        s = ft.render(str(seed), True, C_SEED)
        surf.blit(s, (x + 8, y + BOX_H//2 - s.get_height()//2))
        tx = x + 26

    txt = fs.render(label, True, col)
    mw = BOX_W - (tx - x) - 8
    if txt.get_width() > mw:
        sc = mw / txt.get_width()
        txt = pygame.transform.smoothscale(
            txt, (int(txt.get_width()*sc), int(txt.get_height()*sc)))
    surf.blit(txt, (tx, y + BOX_H//2 - txt.get_height()//2))


def draw_pair_conn(surf, x_src, cy_a, cy_b, x_dst, cy_dst, col):
    """Deux matchups → un suivant (connecteur bracket classique)."""
    mid = (x_src + BOX_W + x_dst) // 2
    pygame.draw.line(surf, col, (x_src + BOX_W, cy_a), (mid, cy_a), 2)
    pygame.draw.line(surf, col, (x_src + BOX_W, cy_b), (mid, cy_b), 2)
    pygame.draw.line(surf, col, (mid, cy_a), (mid, cy_b), 2)
    pygame.draw.line(surf, col, (mid, cy_dst), (x_dst, cy_dst), 2)


def draw_single_conn(surf, x_src, cy_src, x_dst, cy_dst, col):
    """Un matchup → destination à y différent (connecteur en L)."""
    mid = (x_src + BOX_W + x_dst) // 2
    pygame.draw.line(surf, col, (x_src + BOX_W, cy_src), (mid, cy_src), 2)
    pygame.draw.line(surf, col, (mid, cy_src), (mid, cy_dst), 2)
    pygame.draw.line(surf, col, (mid, cy_dst), (x_dst, cy_dst), 2)


def section_label(surf, f, x, y, text, col):
    lbl = f.render(text, True, col)
    surf.blit(lbl, (x, y))


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("DDM — Bracket Playoff")
    clock = pygame.time.Clock()

    f_title = load_font(26)
    f_sec   = load_font(12)
    f_small = load_font(13)
    f_tiny  = load_font(10)
    f_champ = load_font(18)

    # ── État ──────────────────────────────────────────────────────────────────
    def new_draw():
        return random.sample(LLM_NAMES, len(LLM_NAMES)), list(RL_NAMES)

    ub_seeds, lb_seeds = new_draw()
    ub_w = [None] * 7   # 0-3: QF, 4-5: SF, 6: UBF
    lb_w = [None] * 3   # 0-1: LBQ, 2: LBF
    gf_w = [None]       # liste pour mutation dans closure

    # ── Accesseurs équipes ────────────────────────────────────────────────────
    def ub_teams(mid):
        pairs = [(0,7),(3,4),(2,5),(1,6)]
        if mid < 4:
            a, b = pairs[mid]
            return ub_seeds[a], ub_seeds[b]
        if mid == 4: return ub_w[0], ub_w[1]
        if mid == 5: return ub_w[2], ub_w[3]
        if mid == 6: return ub_w[4], ub_w[5]

    def lb_teams(mid):
        if mid == 0: return lb_seeds[0], lb_seeds[3]
        if mid == 1: return lb_seeds[1], lb_seeds[2]
        if mid == 2: return lb_w[0], lb_w[1]

    def gf_teams():
        return ub_w[6], lb_w[2]

    # ── Boîtes cliquables ────────────────────────────────────────────────────
    def build_boxes():
        boxes = []
        # UB QF (toujours visibles)
        for mid, cy in enumerate(UB_QF_CY):
            boxes.append((pygame.Rect(QF_X, t1y(cy), BOX_W, BOX_H), 'ub', mid, 0))
            boxes.append((pygame.Rect(QF_X, t2y(cy), BOX_W, BOX_H), 'ub', mid, 1))
        # UB SF
        for i, cy in enumerate(UB_SF_CY):
            mid = 4 + i
            if None not in ub_teams(mid):
                boxes.append((pygame.Rect(SF_X, t1y(cy), BOX_W, BOX_H), 'ub', mid, 0))
                boxes.append((pygame.Rect(SF_X, t2y(cy), BOX_W, BOX_H), 'ub', mid, 1))
        # UB UBF
        if None not in ub_teams(6):
            cy = UB_UBF_CY
            boxes.append((pygame.Rect(UBF_X, t1y(cy), BOX_W, BOX_H), 'ub', 6, 0))
            boxes.append((pygame.Rect(UBF_X, t2y(cy), BOX_W, BOX_H), 'ub', 6, 1))
        # LB QF
        for mid, cy in enumerate(LB_CY):
            boxes.append((pygame.Rect(LBQ_X, t1y(cy), BOX_W, BOX_H), 'lb', mid, 0))
            boxes.append((pygame.Rect(LBQ_X, t2y(cy), BOX_W, BOX_H), 'lb', mid, 1))
        # LB F
        if None not in lb_teams(2):
            boxes.append((pygame.Rect(LBF_X, t1y(LBF_CY), BOX_W, BOX_H), 'lb', 2, 0))
            boxes.append((pygame.Rect(LBF_X, t2y(LBF_CY), BOX_W, BOX_H), 'lb', 2, 1))
        # GF
        if None not in gf_teams():
            boxes.append((pygame.Rect(GF_X, GF_UB_Y, BOX_W, BOX_H), 'gf', 0, 0))
            boxes.append((pygame.Rect(GF_X, GF_LB_Y, BOX_W, BOX_H), 'gf', 0, 1))
        return boxes

    # ── Clic ──────────────────────────────────────────────────────────────────
    def on_click(bracket, mid, slot):
        nonlocal ub_seeds, lb_seeds
        if bracket == 'ub':
            ta, tb = ub_teams(mid)
            if ta is None or tb is None: return
            ub_w[mid] = (ta, tb)[slot]
            if mid <= 1:
                ub_w[4] = None; ub_w[6] = None; gf_w[0] = None
            elif mid <= 3:
                ub_w[5] = None; ub_w[6] = None; gf_w[0] = None
            elif mid <= 5:
                ub_w[6] = None; gf_w[0] = None
            elif mid == 6:
                gf_w[0] = None
        elif bracket == 'lb':
            ta, tb = lb_teams(mid)
            if ta is None or tb is None: return
            lb_w[mid] = (ta, tb)[slot]
            if mid <= 1:
                lb_w[2] = None; gf_w[0] = None
            elif mid == 2:
                gf_w[0] = None
        elif bracket == 'gf':
            ta, tb = gf_teams()
            if ta is None or tb is None: return
            gf_w[0] = (ta, tb)[slot]

    def reset():
        nonlocal ub_seeds, lb_seeds
        ub_seeds, lb_seeds = new_draw()
        for i in range(7): ub_w[i] = None
        for i in range(3): lb_w[i] = None
        gf_w[0] = None

    # ── Boucle principale ─────────────────────────────────────────────────────
    running = True
    while running:
        mx, my = pygame.mouse.get_pos()
        boxes = build_boxes()

        hover_key = None
        for rect, br, mid, slot in boxes:
            if rect.collidepoint(mx, my):
                hover_key = (br, mid, slot)
                break

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: running = False
                elif event.key == pygame.K_r:    reset()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for rect, br, mid, slot in boxes:
                    if rect.collidepoint(mx, my):
                        on_click(br, mid, slot)
                        break

        # ── Dessin ────────────────────────────────────────────────────────────
        screen.fill(C_BG)

        # Ligne séparatrice
        pygame.draw.line(screen, C_SEP, (0, SEPARATOR_Y), (SCREEN_W, SEPARATOR_Y), 1)

        # Labels sections
        section_label(screen, f_sec, QF_X, 88,  "UPPER BRACKET — PROFILS LLM", (180, 145, 45))
        section_label(screen, f_sec, QF_X, 560, "LOWER BRACKET — AGENTS RL",    (55, 165, 105))
        section_label(screen, f_sec, GF_X, 430, "GRAND FINALE",                  (170, 90, 210))

        # Labels rounds UB
        for lbl, cx in [("QUARTS", QF_X+BOX_W//2), ("DEMIS", SF_X+BOX_W//2), ("FINALE", UBF_X+BOX_W//2)]:
            t = f_tiny.render(lbl, True, C_LBL)
            screen.blit(t, (cx - t.get_width()//2, 108))

        # Labels rounds LB
        for lbl, cx in [("DEMIS", LBQ_X+BOX_W//2), ("FINALE", LBF_X+BOX_W//2)]:
            t = f_tiny.render(lbl, True, C_LBL)
            screen.blit(t, (cx - t.get_width()//2, 580))

        # ── Connecteurs UB ────────────────────────────────────────────────────
        c_ub  = lambda won: C_LINE_UB_W if won else C_LINE_UB
        # QF → SF
        draw_pair_conn(screen, QF_X, UB_QF_CY[0], UB_QF_CY[1], SF_X, UB_SF_CY[0],
                       c_ub(ub_w[0] and ub_w[1]))
        draw_pair_conn(screen, QF_X, UB_QF_CY[2], UB_QF_CY[3], SF_X, UB_SF_CY[1],
                       c_ub(ub_w[2] and ub_w[3]))
        # SF → UBF
        draw_pair_conn(screen, SF_X, UB_SF_CY[0], UB_SF_CY[1], UBF_X, UB_UBF_CY,
                       c_ub(ub_w[4] and ub_w[5]))
        # UBF → GF slot UB
        if ub_w[6]:
            draw_single_conn(screen, UBF_X, UB_UBF_CY, GF_X, GF_UB_CY,
                             C_LINE_GF_W if gf_w[0] else C_LINE_GF)

        # ── Connecteurs LB ────────────────────────────────────────────────────
        c_lb  = lambda won: C_LINE_LB_W if won else C_LINE_LB
        draw_pair_conn(screen, LBQ_X, LB_CY[0], LB_CY[1], LBF_X, LBF_CY,
                       c_lb(lb_w[0] and lb_w[1]))
        if lb_w[2]:
            draw_single_conn(screen, LBF_X, LBF_CY, GF_X, GF_LB_CY,
                             C_LINE_GF_W if gf_w[0] else C_LINE_GF)

        # Champion → ligne vers champ box
        if gf_w[0]:
            pygame.draw.line(screen, C_LINE_GF_W,
                             (GF_X + BOX_W, SEPARATOR_Y),
                             (CHAMP_X, SEPARATOR_Y), 2)

        # ── UB QF boxes ───────────────────────────────────────────────────────
        for mid, cy in enumerate(UB_QF_CY):
            a, b = ub_teams(mid)
            seed_a = UB_QF_CY.index(cy) * 2 + 1 if mid < 2 else None
            for slot, name, yy in [(0, a, t1y(cy)), (1, b, t2y(cy))]:
                hov = hover_key == ('ub', mid, slot)
                draw_box(screen, f_small, f_tiny, QF_X, yy, name,
                         winner=(ub_w[mid] == name),
                         hover=hov, style="llm")

        # ── UB SF boxes ───────────────────────────────────────────────────────
        for i, cy in enumerate(UB_SF_CY):
            mid = 4 + i
            ta, tb = ub_teams(mid)
            if ta is None or tb is None:
                draw_box(screen, f_small, f_tiny, SF_X, t1y(cy), "", tbd=True, style="llm")
                draw_box(screen, f_small, f_tiny, SF_X, t2y(cy), "", tbd=True, style="llm")
            else:
                for slot, name, yy in [(0, ta, t1y(cy)), (1, tb, t2y(cy))]:
                    draw_box(screen, f_small, f_tiny, SF_X, yy, name,
                             winner=(ub_w[mid] == name),
                             hover=(hover_key == ('ub', mid, slot)), style="llm")

        # ── UB UBF boxes ──────────────────────────────────────────────────────
        cy = UB_UBF_CY
        ta, tb = ub_teams(6)
        if ta is None or tb is None:
            draw_box(screen, f_small, f_tiny, UBF_X, t1y(cy), "", tbd=True, style="llm")
            draw_box(screen, f_small, f_tiny, UBF_X, t2y(cy), "", tbd=True, style="llm")
        else:
            for slot, name, yy in [(0, ta, t1y(cy)), (1, tb, t2y(cy))]:
                draw_box(screen, f_small, f_tiny, UBF_X, yy, name,
                         winner=(ub_w[6] == name),
                         hover=(hover_key == ('ub', 6, slot)), style="llm")

        # ── LB QF boxes ───────────────────────────────────────────────────────
        for mid, cy in enumerate(LB_CY):
            ta, tb = lb_teams(mid)
            for slot, name, yy in [(0, ta, t1y(cy)), (1, tb, t2y(cy))]:
                draw_box(screen, f_small, f_tiny, LBQ_X, yy, name,
                         winner=(lb_w[mid] == name),
                         hover=(hover_key == ('lb', mid, slot)), style="rl")

        # ── LB Final boxes ────────────────────────────────────────────────────
        ta, tb = lb_teams(2)
        if ta is None or tb is None:
            draw_box(screen, f_small, f_tiny, LBF_X, t1y(LBF_CY), "", tbd=True, style="rl")
            draw_box(screen, f_small, f_tiny, LBF_X, t2y(LBF_CY), "", tbd=True, style="rl")
        else:
            for slot, name, yy in [(0, ta, t1y(LBF_CY)), (1, tb, t2y(LBF_CY))]:
                draw_box(screen, f_small, f_tiny, LBF_X, yy, name,
                         winner=(lb_w[2] == name),
                         hover=(hover_key == ('lb', 2, slot)), style="rl")

        # ── Grand Finale boxes ────────────────────────────────────────────────
        ub_fin, lb_fin = gf_teams()
        if ub_fin is None:
            draw_box(screen, f_small, f_tiny, GF_X, GF_UB_Y, "", tbd=True, style="gf")
        else:
            draw_box(screen, f_small, f_tiny, GF_X, GF_UB_Y, ub_fin,
                     winner=(gf_w[0] == ub_fin),
                     hover=(hover_key == ('gf', 0, 0)), style="gf")

        if lb_fin is None:
            draw_box(screen, f_small, f_tiny, GF_X, GF_LB_Y, "", tbd=True, style="gf")
        else:
            draw_box(screen, f_small, f_tiny, GF_X, GF_LB_Y, lb_fin,
                     winner=(gf_w[0] == lb_fin),
                     hover=(hover_key == ('gf', 0, 1)), style="gf")

        # "VS" entre les deux slots GF
        vs = f_tiny.render("VS", True, C_GF_BDR_DIM)
        screen.blit(vs, (GF_X + BOX_W//2 - vs.get_width()//2, SEPARATOR_Y - vs.get_height()//2))

        # ── Champion box ──────────────────────────────────────────────────────
        champ = gf_w[0]
        pygame.draw.rect(screen, C_CHAMP_BG if champ else C_GF_BOX,
                         (CHAMP_X, CHAMP_Y, CHAMP_W, CHAMP_H))
        bdr = C_CHAMP_BDR if champ else C_GF_BDR_DIM
        pygame.draw.rect(screen, bdr, (CHAMP_X, CHAMP_Y, CHAMP_W, CHAMP_H), 2)
        if champ:
            pygame.draw.rect(screen, bdr, (CHAMP_X+3, CHAMP_Y+3, CHAMP_W-6, CHAMP_H-6), 1)
        lbl_c = f_tiny.render("CHAMPION", True, bdr)
        screen.blit(lbl_c, (CHAMP_X + CHAMP_W//2 - lbl_c.get_width()//2, CHAMP_Y + 10))
        name_surf = f_champ.render(champ if champ else "???", True,
                                   C_CHAMP_TXT if champ else C_GF_BDR_DIM)
        if name_surf.get_width() > CHAMP_W - 12:
            sc = (CHAMP_W - 12) / name_surf.get_width()
            name_surf = pygame.transform.smoothscale(
                name_surf, (int(name_surf.get_width()*sc), int(name_surf.get_height()*sc)))
        screen.blit(name_surf, (CHAMP_X + CHAMP_W//2 - name_surf.get_width()//2,
                                CHAMP_Y + 38))

        # ── Titre + hint ──────────────────────────────────────────────────────
        title = f_title.render("DDM PLAYOFF BRACKET", True, C_TITLE)
        screen.blit(title, (SCREEN_W//2 - title.get_width()//2, 22))
        hint = f_tiny.render("CLIC = qualifier   R = nouveau tirage   ESC = quitter",
                             True, C_HINT)
        screen.blit(hint, (SCREEN_W//2 - hint.get_width()//2, 58))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
