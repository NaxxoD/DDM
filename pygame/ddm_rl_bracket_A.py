"""
Option A — Play-in JIN vs JIO (curriculum clash), 3 autres en SF directement
python ddm_rl_bracket_A.py   |   clic = avancer   ESC = quitter
"""
import pygame, sys

import os
_DDM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(_DDM_ROOT, "assets", "PressStart2P-Regular.ttf")
W, H = 1280, 720
FPS  = 60

C_BG   = (18, 14, 32)
C_BOX  = (15, 42, 32)
C_WIN  = (20, 60, 44)
C_DIM  = (22, 22, 32)
C_BDR  = (55, 170, 110)
C_DIM_BDR = (28, 72, 50)
C_TXT  = (90, 210, 150)
C_WIN_TXT = (130, 255, 180)
C_DIM_TXT = (45, 55, 45)
C_LINE = (35, 80, 58)
C_LINE_W = (70, 180, 120)
C_TITLE = (200, 160, 50)
C_LBL  = (80, 72, 95)

BW, BH, GAP = 200, 42, 8

# ── Layout ────────────────────────────────────────────────────────────────────
# Col X
X_PI  = 80    # play-in
X_SF  = 340   # SF
X_FIN = 600   # RL Final
X_CH  = 870   # Champion

# Play-in Y (JIN vs JIO)
PI_CY = 440   # centre play-in

# SF Y
SF1_CY = 240  # SF1 : CROSS vs play-in winner
SF2_CY = 560  # SF2 : JAEHA vs NEOSIA

# Final Y
FIN_CY = (SF1_CY + SF2_CY) // 2  # 400

# Bracket structure
# winners[0] = play-in (JIN=0 / JIO=1)
# winners[1] = SF1 (CROSS=2 / play-in winner)
# winners[2] = SF2 (JAEHA=3 / NEOSIA=4)
# winners[3] = Final

AGENTS = ["JIN", "JIO", "CROSS", "JAEHA", "NEOSIA"]

def t1y(cy): return cy - GAP//2 - BH
def t2y(cy): return cy + GAP//2

def get_teams(winners, mid):
    if mid == 0: return 0, 1          # play-in: JIN vs JIO
    if mid == 1: return 2, winners[0] # SF1: CROSS vs play-in W
    if mid == 2: return 3, 4          # SF2: JAEHA vs NEOSIA
    if mid == 3: return winners[1], winners[2]  # Final

def load_font(s):
    try: return pygame.font.Font(FONT_PATH, s)
    except: return pygame.font.SysFont("consolas", s)

def draw_box(surf, fs, ft, x, y, label, winner=False, dim=False, hover=False):
    bg  = C_WIN if winner else (C_DIM if dim else (C_BOX))
    bdr = C_BDR if (winner or hover) else (C_DIM_BDR if dim else C_BDR)
    col = C_WIN_TXT if winner else (C_DIM_TXT if dim else C_TXT)
    pygame.draw.rect(surf, bg,  (x, y, BW, BH))
    pygame.draw.rect(surf, bdr, (x, y, BW, BH), 2)
    t = fs.render(label, True, col)
    if t.get_width() > BW-12:
        sc = (BW-12)/t.get_width()
        t = pygame.transform.smoothscale(t,(int(t.get_width()*sc),int(t.get_height()*sc)))
    surf.blit(t, (x+8, y+BH//2-t.get_height()//2))

def draw_conn(surf, x1, cy1, x2, cy2, col):
    mx = (x1+BW+x2)//2
    pygame.draw.line(surf, col, (x1+BW, cy1), (mx, cy1), 2)
    pygame.draw.line(surf, col, (mx, cy1), (mx, cy2), 2)
    pygame.draw.line(surf, col, (mx, cy2), (x2, cy2), 2)

def draw_pair(surf, x_src, cy_a, cy_b, x_dst, cy_dst, col):
    mx = (x_src+BW+x_dst)//2
    pygame.draw.line(surf, col, (x_src+BW, cy_a), (mx, cy_a), 2)
    pygame.draw.line(surf, col, (x_src+BW, cy_b), (mx, cy_b), 2)
    pygame.draw.line(surf, col, (mx, cy_a), (mx, cy_b), 2)
    pygame.draw.line(surf, col, (mx, cy_dst), (x_dst, cy_dst), 2)

def main():
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Option A — Play-in JIN vs JIO")
    clock = pygame.time.Clock()
    fs = load_font(13); ft = load_font(10); fb = load_font(20)

    winners = [None, None, None, None]  # 4 matchs

    def clickable_boxes():
        boxes = []
        # Play-in
        boxes.append((pygame.Rect(X_PI,t1y(PI_CY),BW,BH), 0, 0))
        boxes.append((pygame.Rect(X_PI,t2y(PI_CY),BW,BH), 0, 1))
        # SF1 (si play-in joué)
        if winners[0] is not None:
            boxes.append((pygame.Rect(X_SF,t1y(SF1_CY),BW,BH), 1, 0))
            boxes.append((pygame.Rect(X_SF,t2y(SF1_CY),BW,BH), 1, 1))
        # SF2
        boxes.append((pygame.Rect(X_SF,t1y(SF2_CY),BW,BH), 2, 0))
        boxes.append((pygame.Rect(X_SF,t2y(SF2_CY),BW,BH), 2, 1))
        # Final
        if winners[1] is not None and winners[2] is not None:
            boxes.append((pygame.Rect(X_FIN,t1y(FIN_CY),BW,BH), 3, 0))
            boxes.append((pygame.Rect(X_FIN,t2y(FIN_CY),BW,BH), 3, 1))
        return boxes

    while True:
        mx, my = pygame.mouse.get_pos()
        boxes = clickable_boxes()
        hover_mid, hover_slot = None, None
        for r, mid, slot in boxes:
            if r.collidepoint(mx, my): hover_mid, hover_slot = mid, slot; break

        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type==pygame.KEYDOWN and e.key==pygame.K_ESCAPE):
                pygame.quit(); sys.exit()
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for r, mid, slot in boxes:
                    if r.collidepoint(mx, my):
                        ta, tb = get_teams(winners, mid)
                        if ta is not None and tb is not None:
                            winners[mid] = (ta, tb)[slot]
                            if mid < 2: winners[3] = None
                        break

        screen.fill(C_BG)

        # Titre
        t = fb.render("OPTION A  —  PLAY-IN JIN vs JIO", True, C_TITLE)
        screen.blit(t, (W//2-t.get_width()//2, 20))
        sub = ft.render("JIN et JIO partagent le meme curriculum  —  play-in fixe  |  CROSS / JAEHA / NEOSIA en SF directement", True, C_LBL)
        screen.blit(sub, (W//2-sub.get_width()//2, 55))

        # Labels colonnes
        for lbl, cx in [("PLAY-IN", X_PI+BW//2), ("DEMIS", X_SF+BW//2),
                         ("FINALE RL", X_FIN+BW//2), ("CHAMPION", X_CH+BW//2)]:
            l = ft.render(lbl, True, C_LBL)
            screen.blit(l, (cx-l.get_width()//2, 90))

        # Connecteurs
        cl = lambda done: C_LINE_W if done else C_LINE
        # Play-in → SF1 bottom slot
        if winners[0] is not None:
            draw_conn(screen, X_PI, PI_CY, X_SF, SF1_CY, cl(True))
        else:
            draw_conn(screen, X_PI, PI_CY, X_SF, SF1_CY, C_LINE)
        # SF1 pair
        draw_pair(screen, X_SF, SF1_CY, SF2_CY, X_FIN, FIN_CY, cl(winners[1] and winners[2]))
        # Final → Champion
        if winners[3] is not None:
            pygame.draw.line(screen, C_LINE_W, (X_FIN+BW, FIN_CY), (X_CH, FIN_CY), 2)

        # Play-in
        ta, tb = get_teams(winners, 0)
        w = winners[0]
        draw_box(screen, fs, ft, X_PI, t1y(PI_CY), AGENTS[ta],
                 winner=(w==ta), dim=(w is not None and w!=ta),
                 hover=(hover_mid==0 and hover_slot==0))
        draw_box(screen, fs, ft, X_PI, t2y(PI_CY), AGENTS[tb],
                 winner=(w==tb), dim=(w is not None and w!=tb),
                 hover=(hover_mid==0 and hover_slot==1))
        pi_lbl = ft.render("PLAY-IN", True, (55,170,110))
        screen.blit(pi_lbl, (X_PI, t1y(PI_CY)-18))

        # SF1
        ta, tb = get_teams(winners, 1)
        w1 = winners[1]
        if ta is not None and tb is not None:
            draw_box(screen, fs, ft, X_SF, t1y(SF1_CY), AGENTS[ta],
                     winner=(w1==ta), dim=(w1 is not None and w1!=ta),
                     hover=(hover_mid==1 and hover_slot==0))
            draw_box(screen, fs, ft, X_SF, t2y(SF1_CY), AGENTS[tb] if tb is not None else "???",
                     winner=(w1==tb), dim=(w1 is not None and w1!=tb) if tb is not None else False,
                     hover=(hover_mid==1 and hover_slot==1))
        else:
            draw_box(screen, fs, ft, X_SF, t1y(SF1_CY), AGENTS[2], hover=(hover_mid==1 and hover_slot==0))
            draw_box(screen, fs, ft, X_SF, t2y(SF1_CY), "???", dim=True)

        # SF2
        ta, tb = get_teams(winners, 2)
        w2 = winners[2]
        draw_box(screen, fs, ft, X_SF, t1y(SF2_CY), AGENTS[ta],
                 winner=(w2==ta), dim=(w2 is not None and w2!=ta),
                 hover=(hover_mid==2 and hover_slot==0))
        draw_box(screen, fs, ft, X_SF, t2y(SF2_CY), AGENTS[tb],
                 winner=(w2==tb), dim=(w2 is not None and w2!=tb),
                 hover=(hover_mid==2 and hover_slot==1))

        # Final
        if winners[1] is not None and winners[2] is not None:
            ta, tb = get_teams(winners, 3)
            wf = winners[3]
            draw_box(screen, fs, ft, X_FIN, t1y(FIN_CY), AGENTS[ta],
                     winner=(wf==ta), dim=(wf is not None and wf!=ta),
                     hover=(hover_mid==3 and hover_slot==0))
            draw_box(screen, fs, ft, X_FIN, t2y(FIN_CY), AGENTS[tb],
                     winner=(wf==tb), dim=(wf is not None and wf!=tb),
                     hover=(hover_mid==3 and hover_slot==1))
        else:
            for yy in [t1y(FIN_CY), t2y(FIN_CY)]:
                draw_box(screen, fs, ft, X_FIN, yy, "???", dim=True)

        # Champion
        if winners[3] is not None:
            t = fs.render(AGENTS[winners[3]], True, (255,225,80))
            screen.blit(t, (X_CH, FIN_CY-t.get_height()//2))
            sub2 = ft.render("RL CHAMPION", True, (200,165,45))
            screen.blit(sub2, (X_CH, FIN_CY+t.get_height()//2+4))

        hint = ft.render("CLIC pour qualifier  |  ESC quitter", True, C_LBL)
        screen.blit(hint, (W//2-hint.get_width()//2, H-30))
        pygame.display.flip(); clock.tick(FPS)

if __name__ == "__main__": main()
