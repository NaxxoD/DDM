# =============================================================================
# ddm_post_game.py — Bilan de partie DDM
#
# Lancé automatiquement par le renderer 5s après game over.
# Screen 1 : recap (factions, tours, unités, QG HP)
# Screen 2 : détails (répartition dés, invocations par niveau)
# =============================================================================

import pygame, sys, os, json, pathlib, re, subprocess
from collections import Counter

# =============================================================================
# CHEMINS
# =============================================================================
_DDM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT_PATH = pathlib.Path(os.path.join(_DDM_ROOT, "engine", "snapshots", "latest.json"))
LOG_DIR       = pathlib.Path(os.path.join(_DDM_ROOT, "logs", "log_data", "log"))
FONT_PATH     = os.path.join(_DDM_ROOT, "assets", "PressStart2P-Regular.ttf")
MENU_PATH     = pathlib.Path(__file__).parent / "ddm_menu.py"

# =============================================================================
# CONSTANTES
# =============================================================================
SCREEN_W, SCREEN_H = 1920, 1080
FPS = 60

C_BG      = (18, 14, 32)
C_GOLD    = (200, 160, 50)
C_DIM     = (100, 95, 115)
C_TEXT    = (210, 200, 220)
C_P1      = (80, 140, 220)
C_P2      = (220, 80, 80)
C_BTN_BG  = (28, 26, 48)
C_BTN_SEL = (230, 190, 55)
C_BAR_BG  = (38, 34, 54)

ALL_FACES    = ["ATK", "DEF", "MOVE", "CAP", "STAR"]
LEVEL_NAMES  = {1: "L1  BLANC", 2: "L2  VERT", 3: "L3  BLEU", 4: "L4  ROUGE", 5: "L5  NOIR"}
LEVEL_COLORS = {1: (180, 180, 180), 2: (80, 200, 80), 3: (80, 140, 220), 4: (220, 80, 80), 5: (160, 120, 200)}

# =============================================================================
# LOG PARSING
# =============================================================================
_ROLL_RE   = re.compile(r"^ROLL\s+([AB]):\s+\S+\(\d+\)\s+->\s+([A-Z]+)")
_INVOKE_RE = re.compile(r"^INVOKE_RESULT\s+player=([AB])\s+level=(\d+)\s+success=(\d+)")


def find_latest_log():
    if not LOG_DIR.is_dir():
        return None
    logs = sorted(LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    return logs[0] if logs else None


def parse_log(log_path):
    player_faces     = {"A": Counter(), "B": Counter()}
    invoc_by_level   = {"A": Counter(), "B": Counter()}
    if not log_path or not log_path.exists():
        return player_faces, invoc_by_level
    with log_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            m = _ROLL_RE.match(line)
            if m:
                player, face = m.group(1), m.group(2)
                player_faces[player][face] += 1
                continue
            m2 = _INVOKE_RE.match(line)
            if m2:
                player, level, success = m2.group(1), int(m2.group(2)), int(m2.group(3))
                if success:
                    invoc_by_level[player][level] += 1

    return player_faces, invoc_by_level


# =============================================================================
# SNAPSHOT
# =============================================================================
def load_snap():
    try:
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_recap(snap):
    pa = snap.get("joueur_A") or {}
    pb = snap.get("joueur_B") or {}
    return {
        "winner":    snap.get("winner", "?"),
        "tours":     snap.get("tour", 0),
        "faction_a": pa.get("faction", "?"),
        "faction_b": pb.get("faction", "?"),
        "qg_a":      (pa.get("qg") or {}).get("hp", 0),
        "qg_b":      (pb.get("qg") or {}).get("hp", 0),
        "units_a":   len(pa.get("unites", [])),
        "units_b":   len(pb.get("unites", [])),
    }


# =============================================================================
# HELPERS VISUELS
# =============================================================================
def draw_btn(surf, font, text, rect, hovered):
    col = C_BTN_SEL if hovered else C_GOLD
    pygame.draw.rect(surf, C_BTN_BG, rect, border_radius=4)
    pygame.draw.rect(surf, col, rect, 2, border_radius=4)
    lbl = font.render(text, True, col)
    surf.blit(lbl, (rect.centerx - lbl.get_width() // 2,
                    rect.centery - lbl.get_height() // 2))


def draw_bar(surf, x, y, value, max_val, w, h, color):
    pygame.draw.rect(surf, C_BAR_BG, (x, y, w, h))
    if max_val > 0 and value > 0:
        filled = max(2, int(value / max_val * w))
        pygame.draw.rect(surf, color, (x, y, filled, h))


def draw_separator(surf, y):
    pygame.draw.line(surf, C_DIM, (SCREEN_W // 5, y), (4 * SCREEN_W // 5, y), 1)


# =============================================================================
# SCREEN 1 — RECAP
# =============================================================================
def draw_recap(surf, fonts, recap, mx, my, btn_details, btn_menu):
    f_big, f_med, f_small, f_tiny = fonts
    surf.fill(C_BG)

    winner = recap["winner"]
    if winner == "A":
        label, col = "VICTOIRE  JOUEUR  A", C_P1
    elif winner == "B":
        label, col = "VICTOIRE  JOUEUR  B", C_P2
    else:
        label, col = "MATCH  NUL", C_TEXT

    # Bannière
    lbl = f_big.render(label, True, col)
    surf.blit(lbl, ((SCREEN_W - lbl.get_width()) // 2, 110))

    draw_separator(surf, 210)

    # Factions
    fa = f_med.render(recap["faction_a"].upper(), True, C_P1)
    vs = f_med.render("VS", True, C_DIM)
    fb = f_med.render(recap["faction_b"].upper(), True, C_P2)
    cy = 255
    surf.blit(fa, (SCREEN_W // 2 - fa.get_width() - 70, cy))
    surf.blit(vs, (SCREEN_W // 2 - vs.get_width() // 2, cy))
    surf.blit(fb, (SCREEN_W // 2 + 70, cy))

    draw_separator(surf, 320)

    # Stats tableau
    rows = [
        ("TOURS JOUÉS",            str(recap["tours"]),   C_TEXT),
        ("UNITÉS SURVIVANTES  A",  str(recap["units_a"]), C_P1),
        ("UNITÉS SURVIVANTES  B",  str(recap["units_b"]), C_P2),
        ("QG  A",                  f"{recap['qg_a']} HP", C_P1),
        ("QG  B",                  f"{recap['qg_b']} HP", C_P2),
    ]
    lx = SCREEN_W // 2 - 320
    rx = SCREEN_W // 2 + 80
    sy = 360
    for row_label, val, vcol in rows:
        l = f_small.render(row_label, True, C_DIM)
        v = f_small.render(val, True, vcol)
        surf.blit(l, (lx, sy))
        surf.blit(v, (rx, sy))
        sy += 62

    # Boutons
    draw_btn(surf, f_small, "DÉTAILS  DE  LA  PARTIE", btn_details,
             btn_details.collidepoint(mx, my))
    draw_btn(surf, f_small, "MENU  PRINCIPAL", btn_menu,
             btn_menu.collidepoint(mx, my))


# =============================================================================
# SCREEN 2 — DÉTAILS
# =============================================================================
def draw_details(surf, fonts, player_faces, invoc_by_level, mx, my, btn_recap, btn_menu):
    f_big, f_med, f_small, f_tiny = fonts
    surf.fill(C_BG)

    t = f_med.render("STATS  DE  PARTIE", True, C_GOLD)
    surf.blit(t, ((SCREEN_W - t.get_width()) // 2, 55))
    draw_separator(surf, 105)

    # ── Répartition des faces ──
    h = f_small.render("RÉPARTITION  DES  FACES", True, C_DIM)
    surf.blit(h, (200, 130))

    COL_A = 340
    COL_B = SCREEN_W // 2 + 160
    BAR_W = 280
    BAR_H = 20

    ha = f_small.render("JOUEUR  A", True, C_P1)
    hb = f_small.render("JOUEUR  B", True, C_P2)
    surf.blit(ha, (COL_A, 165))
    surf.blit(hb, (COL_B, 165))

    total_a = sum(player_faces["A"].values()) or 1
    total_b = sum(player_faces["B"].values()) or 1
    fy = 200

    for face in ALL_FACES:
        pct_a = player_faces["A"].get(face, 0) / total_a * 100
        pct_b = player_faces["B"].get(face, 0) / total_b * 100

        fl = f_tiny.render(face, True, C_TEXT)
        surf.blit(fl, (COL_A - 90, fy + 3))

        draw_bar(surf, COL_A, fy, pct_a, 100, BAR_W, BAR_H, C_P1)
        pa_lbl = f_tiny.render(f"{pct_a:.0f}%", True, C_DIM)
        surf.blit(pa_lbl, (COL_A + BAR_W + 8, fy + 3))

        draw_bar(surf, COL_B, fy, pct_b, 100, BAR_W, BAR_H, C_P2)
        pb_lbl = f_tiny.render(f"{pct_b:.0f}%", True, C_DIM)
        surf.blit(pb_lbl, (COL_B + BAR_W + 8, fy + 3))

        fy += 42

    # ── Invocations ──
    draw_separator(surf, fy + 15)
    h2 = f_small.render("INVOCATIONS  PAR  NIVEAU", True, C_DIM)
    surf.blit(h2, (200, fy + 30))

    max_invoc = max(
        max(invoc_by_level["A"].values(), default=0),
        max(invoc_by_level["B"].values(), default=0),
        1
    )
    iy = fy + 70

    for level in range(1, 6):
        cnt_a = invoc_by_level["A"].get(level, 0)
        cnt_b = invoc_by_level["B"].get(level, 0)
        lcolor = LEVEL_COLORS.get(level, C_TEXT)

        ll = f_tiny.render(LEVEL_NAMES[level], True, lcolor)
        surf.blit(ll, (COL_A - 180, iy + 3))

        draw_bar(surf, COL_A, iy, cnt_a, max_invoc, BAR_W, BAR_H, C_P1)
        va = f_tiny.render(f"A : {cnt_a}", True, C_P1)
        surf.blit(va, (COL_A + BAR_W + 8, iy + 3))

        draw_bar(surf, COL_B, iy, cnt_b, max_invoc, BAR_W, BAR_H, C_P2)
        vb = f_tiny.render(f"B : {cnt_b}", True, C_P2)
        surf.blit(vb, (COL_B + BAR_W + 8, iy + 3))

        iy += 42

    # Boutons
    draw_btn(surf, f_small, "←  RECAP", btn_recap, btn_recap.collidepoint(mx, my))
    draw_btn(surf, f_small, "MENU  PRINCIPAL", btn_menu, btn_menu.collidepoint(mx, my))


# =============================================================================
# MAIN
# =============================================================================
def launch_menu():
    subprocess.Popen([sys.executable, str(MENU_PATH)], env=os.environ.copy())


def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("DDM — Bilan de partie")
    clock = pygame.time.Clock()

    try:
        f_big   = pygame.font.Font(FONT_PATH, 36)
        f_med   = pygame.font.Font(FONT_PATH, 20)
        f_small = pygame.font.Font(FONT_PATH, 14)
        f_tiny  = pygame.font.Font(FONT_PATH, 9)
    except Exception:
        f_big   = pygame.font.SysFont(None, 64)
        f_med   = pygame.font.SysFont(None, 36)
        f_small = pygame.font.SysFont(None, 28)
        f_tiny  = pygame.font.SysFont(None, 18)
    fonts = (f_big, f_med, f_small, f_tiny)

    snap                     = load_snap()
    recap                    = get_recap(snap)
    log_path                 = find_latest_log()
    player_faces, invoc_lvl  = parse_log(log_path)

    BTN_W = 360
    BTN_H = 50
    BY    = SCREEN_H - 90

    btn_details = pygame.Rect(SCREEN_W // 2 - BTN_W - 20, BY, BTN_W, BTN_H)
    btn_recap   = pygame.Rect(SCREEN_W // 2 - BTN_W - 20, BY, BTN_W, BTN_H)
    btn_menu_1  = pygame.Rect(SCREEN_W // 2 + 20,         BY, BTN_W, BTN_H)
    btn_menu_2  = pygame.Rect(SCREEN_W // 2 + 20,         BY, BTN_W, BTN_H)

    screen_id = 0  # 0 = recap, 1 = details
    running   = True

    while running:
        mx, my = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_RIGHT and screen_id == 0:
                    screen_id = 1
                elif event.key == pygame.K_LEFT and screen_id == 1:
                    screen_id = 0

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if screen_id == 0:
                    if btn_details.collidepoint(mx, my):
                        screen_id = 1
                    elif btn_menu_1.collidepoint(mx, my):
                        launch_menu()
                        running = False
                else:
                    if btn_recap.collidepoint(mx, my):
                        screen_id = 0
                    elif btn_menu_2.collidepoint(mx, my):
                        launch_menu()
                        running = False

        if screen_id == 0:
            draw_recap(screen, fonts, recap, mx, my, btn_details, btn_menu_1)
        else:
            draw_details(screen, fonts, player_faces, invoc_lvl, mx, my, btn_recap, btn_menu_2)

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
