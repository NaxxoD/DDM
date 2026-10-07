"""
Option B — Knockout structuré par affinités
R1 : JIN vs JIO (curriculum), CROSS vs NEOSIA (curriculum inversé vs nouveau)
SF : JAEHA (bye) vs R1W1,  R1W2 → Final directement
Final : SF winner vs R1W2
python ddm_rl_bracket_B.py
"""
import pygame, sys

import os
_DDM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(_DDM_ROOT, "assets", "PressStart2P-Regular.ttf")
W, H = 1280, 720
FPS  = 60

C_BG  = (18, 14, 32); C_BOX = (15, 42, 32); C_WIN = (20, 60, 44); C_DIM = (22, 22, 32)
C_BDR = (55, 170, 110); C_DIM_BDR = (28, 72, 50)
C_TXT = (90, 210, 150); C_WIN_TXT = (130, 255, 180); C_DIM_TXT = (45, 55, 45)
C_LINE = (35, 80, 58); C_LINE_W = (70, 180, 120)
C_TITLE = (200, 160, 50); C_LBL = (80, 72, 95)
C_JAEHA = (80, 140, 200)   # couleur spéciale pour le bye

BW, BH, GAP = 200, 42, 8

# Agents : 0=JIN 1=JIO 2=CROSS 3=NEOSIA 4=JAEHA
AGENTS = ["JIN", "JIO", "CROSS", "NEOSIA", "JAEHA"]

# Structure :
# mid 0 : JIN(0) vs JIO(1)          → W0
# mid 1 : CROSS(2) vs NEOSIA(3)     → W1
# mid 2 : JAEHA(4) vs W0 (SF)       → W2 (SF)
# mid 3 : Final : W2 vs W1

X_R1  = 80   # Round 1
X_SF  = 390  # Semi-finale (JAEHA + W0)
X_FIN = 700  # Finale
X_CH  = 960  # Champion

R1_CY_TOP = 250   # JIN vs JIO
R1_CY_BOT = 500   # CROSS vs NEOSIA
SF_CY     = 310   # JAEHA vs W0  (dans la zone haute)
FIN_CY    = (SF_CY + R1_CY_BOT) // 2  # ~405

def t1y(cy): return cy - GAP//2 - BH
def t2y(cy): return cy + GAP//2

def get_teams(winners, mid):
    if mid == 0: return 0, 1            # JIN vs JIO
    if mid == 1: return 2, 3            # CROSS vs NEOSIA
    if mid == 2: return 4, winners[0]   # JAEHA vs W0
    if mid == 3: return winners[2], winners[1]  # Final: SF winner vs R1W1

def load_font(s):
    try: return pygame.font.Font(FONT_PATH, s)
    except: return pygame.font.SysFont("consolas", s)

def draw_box(surf, fs, x, y, label, winner=False, dim=False, hover=False, bye=False):
    bg  = C_WIN if winner else (C_DIM if dim else C_BOX)
    bdr = (C_JAEHA if bye else C_BDR) if not dim else C_DIM_BDR
    col = C_WIN_TXT if winner else (C_DIM_TXT if dim else (C_JAEHA if bye else C_TXT))
    pygame.draw.rect(surf, bg,  (x, y, BW, BH))
    pygame.draw.rect(surf, bdr, (x, y, BW, BH), 2 if not bye else 3)
    t = fs.render(label, True, col)
    if t.get_width() > BW-12:
        sc = (BW-12)/t.get_width()
        t = pygame.transform.smoothscale(t,(int(t.get_width()*sc),int(t.get_height()*sc)))
    surf.blit(t, (x+8, y+BH//2-t.get_height()//2))

def ln(surf, a, b, col): pygame.draw.line(surf, col, a, b, 2)

def draw_pair(surf, x_src, cy_a, cy_b, x_dst, cy_dst, col):
    mx = (x_src+BW+x_dst)//2
    ln(surf,(x_src+BW,cy_a),(mx,cy_a),col); ln(surf,(x_src+BW,cy_b),(mx,cy_b),col)
    ln(surf,(mx,cy_a),(mx,cy_b),col);        ln(surf,(mx,cy_dst),(x_dst,cy_dst),col)

def main():
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Option B — Knockout structuré")
    clock = pygame.time.Clock()
    fs = load_font(13); ft = load_font(10); fb = load_font(18)

    winners = [None, None, None, None]

    def clickable_boxes():
        boxes = []
        boxes.append((pygame.Rect(X_R1,t1y(R1_CY_TOP),BW,BH), 0, 0))
        boxes.append((pygame.Rect(X_R1,t2y(R1_CY_TOP),BW,BH), 0, 1))
        boxes.append((pygame.Rect(X_R1,t1y(R1_CY_BOT),BW,BH), 1, 0))
        boxes.append((pygame.Rect(X_R1,t2y(R1_CY_BOT),BW,BH), 1, 1))
        if winners[0] is not None:
            boxes.append((pygame.Rect(X_SF,t1y(SF_CY),BW,BH), 2, 0))
            boxes.append((pygame.Rect(X_SF,t2y(SF_CY),BW,BH), 2, 1))
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
            if e.type == pygame.MOUSEBUTTONDOWN and e.button==1:
                for r, mid, slot in boxes:
                    if r.collidepoint(mx, my):
                        ta, tb = get_teams(winners, mid)
                        if ta is not None and tb is not None:
                            winners[mid] = (ta, tb)[slot]
                            if mid == 0: winners[2] = None; winners[3] = None
                            if mid == 1: winners[3] = None
                            if mid == 2: winners[3] = None
                        break

        screen.fill(C_BG)
        t = fb.render("OPTION B  —  KNOCKOUT STRUCTURE PAR AFFINITES", True, C_TITLE)
        screen.blit(t, (W//2-t.get_width()//2, 18))
        sub = ft.render("R1: JIN/JIO (curriculum) + CROSS/NEOSIA (inversé/nouveau)  |  JAEHA bye en SF  |  R1W2 monte direct en Finale", True, C_LBL)
        screen.blit(sub, (W//2-sub.get_width()//2, 50))

        for lbl, cx in [("ROUND 1", X_R1+BW//2), ("SF", X_SF+BW//2),
                         ("FINALE", X_FIN+BW//2), ("CHAMPION", X_CH+BW//2)]:
            l = ft.render(lbl, True, C_LBL)
            screen.blit(l, (cx-l.get_width()//2, 88))

        cl = lambda done: C_LINE_W if done else C_LINE

        # Connecteur R1 top → SF
        draw_pair(screen, X_R1, R1_CY_TOP, R1_CY_TOP, X_SF, SF_CY, cl(winners[0] is not None))

        # JAEHA → SF (horizontal depuis la gauche)
        jaeha_y = t1y(SF_CY)
        bye_col = C_JAEHA
        ln(screen, (X_SF-60, jaeha_y+BH//2), (X_SF, jaeha_y+BH//2), bye_col)

        # R1 bottom winner → Final directement
        if winners[1] is not None:
            mx2 = (X_R1+BW + X_FIN)//2 + 20
            ln(screen,(X_R1+BW,R1_CY_BOT),(mx2,R1_CY_BOT), C_LINE_W)
            ln(screen,(mx2,R1_CY_BOT),(mx2,t2y(FIN_CY)+BH//2), C_LINE_W)
            ln(screen,(mx2,t2y(FIN_CY)+BH//2),(X_FIN,t2y(FIN_CY)+BH//2), C_LINE_W)

        # SF → Final
        if winners[2] is not None:
            ln(screen,(X_SF+BW,SF_CY),(X_FIN,t1y(FIN_CY)+BH//2), cl(True))

        # Final → Champion
        if winners[3] is not None:
            ln(screen,(X_FIN+BW,FIN_CY),(X_CH,FIN_CY), C_LINE_W)

        # ── R1 top : JIN vs JIO ────────────────────────────────────────────────
        clash_lbl = ft.render("CURRICULUM CLASH", True, (120,90,180))
        screen.blit(clash_lbl, (X_R1, t1y(R1_CY_TOP)-18))
        for mid_id, cy in [(0, R1_CY_TOP), (1, R1_CY_BOT)]:
            ta, tb = get_teams(winners, mid_id)
            w = winners[mid_id]
            for slot, agent, yy in [(0, ta, t1y(cy)), (1, tb, t2y(cy))]:
                draw_box(screen, fs, X_R1, yy, AGENTS[agent],
                         winner=(w==agent), dim=(w is not None and w!=agent),
                         hover=(hover_mid==mid_id and hover_slot==slot))

        clash2 = ft.render("CURRICULUM INV. vs NOUVEAU", True, (100,80,160))
        screen.blit(clash2, (X_R1, t1y(R1_CY_BOT)-18))

        # ── JAEHA (bye affiché) ───────────────────────────────────────────────
        bye_lbl = ft.render("BYE  —  GENERALISTE", True, C_JAEHA)
        screen.blit(bye_lbl, (X_SF-75, t1y(SF_CY)-18))
        draw_box(screen, fs, X_SF-65, t1y(SF_CY), "JAEHA", bye=True)

        # ── SF : JAEHA vs W0 ─────────────────────────────────────────────────
        if winners[0] is not None:
            ta, tb = get_teams(winners, 2)
            w2 = winners[2]
            tb_label = AGENTS[tb] if tb is not None else "???"
            draw_box(screen, fs, X_SF, t1y(SF_CY), "JAEHA",
                     winner=(w2==4), dim=(w2 is not None and w2!=4),
                     hover=(hover_mid==2 and hover_slot==0), bye=(w2 is None))
            draw_box(screen, fs, X_SF, t2y(SF_CY), tb_label,
                     winner=(w2==tb), dim=(w2 is not None and w2!=tb) if tb is not None else False,
                     hover=(hover_mid==2 and hover_slot==1))
        else:
            draw_box(screen, fs, X_SF, t1y(SF_CY), "JAEHA", bye=True)
            draw_box(screen, fs, X_SF, t2y(SF_CY), "???", dim=True)

        # ── Finale ────────────────────────────────────────────────────────────
        if winners[1] is not None and winners[2] is not None:
            ta, tb = get_teams(winners, 3)
            wf = winners[3]
            for slot, ag, yy in [(0,ta,t1y(FIN_CY)),(1,tb,t2y(FIN_CY))]:
                lbl = AGENTS[ag] if ag is not None else "???"
                draw_box(screen, fs, X_FIN, yy, lbl,
                         winner=(wf==ag), dim=(wf is not None and wf!=ag) if ag is not None else False,
                         hover=(hover_mid==3 and hover_slot==slot))
        else:
            for yy in [t1y(FIN_CY), t2y(FIN_CY)]:
                draw_box(screen, fs, X_FIN, yy, "???", dim=True)

        if winners[3] is not None:
            t2 = fs.render(AGENTS[winners[3]], True, (255,225,80))
            screen.blit(t2, (X_CH, FIN_CY-t2.get_height()//2))
            sub2 = ft.render("RL CHAMPION", True, (200,165,45))
            screen.blit(sub2, (X_CH, FIN_CY+t2.get_height()//2+4))

        hint = ft.render("CLIC pour qualifier  |  ESC quitter", True, C_LBL)
        screen.blit(hint, (W//2-hint.get_width()//2, H-30))
        pygame.display.flip(); clock.tick(FPS)

if __name__ == "__main__": main()
