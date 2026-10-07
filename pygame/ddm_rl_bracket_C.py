"""
Option C — Phase de groupes (round-robin) puis Final
5 agents se rencontrent tous : 10 matchs auto-résolus par tier
Le classement détermine qui va en finale
Clic sur un match = forcer le vainqueur  |  R = auto-résoudre tout  |  ESC = quitter
"""
import pygame, sys, random

import os
_DDM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(_DDM_ROOT, "assets", "PressStart2P-Regular.ttf")
W, H = 1280, 720
FPS  = 60

C_BG    = (18, 14, 32); C_TITLE = (200, 160, 50); C_LBL = (80, 72, 95)
C_BOX   = (15, 42, 32); C_WIN   = (20, 60, 44);   C_DIM = (22, 22, 32)
C_BDR   = (55, 170, 110); C_DIM_BDR = (28, 72, 50); C_BDR_HOV = (90, 200, 150)
C_TXT   = (90, 210, 150); C_WIN_TXT = (130, 255, 180); C_DIM_TXT = (45, 55, 45)
C_FIN_BDR = (200, 160, 50); C_FIN_TXT = (230, 190, 55)
C_LINE  = (35, 80, 58); C_LINE_W = (70, 180, 120)

AGENTS = ["JIN", "JIO", "CROSS", "JAEHA", "NEOSIA"]
TIER   = {"JIN":4,"JIO":4,"CROSS":4,"JAEHA":4,"NEOSIA":4}

# Tous les matchs de groupe : 10 paires
MATCHES = [(i,j) for i in range(5) for j in range(i+1,5)]
# [(0,1),(0,2),(0,3),(0,4),(1,2),(1,3),(1,4),(2,3),(2,4),(3,4)]

def load_font(s):
    try: return pygame.font.Font(FONT_PATH, s)
    except: return pygame.font.SysFont("consolas", s)

def wins_losses(results):
    w = [0]*5; l = [0]*5
    for (a,b), winner in results.items():
        if winner == a: w[a]+=1; l[b]+=1
        elif winner == b: w[b]+=1; l[a]+=1
    return w, l

def ranking(results):
    w, l = wins_losses(results)
    order = sorted(range(5), key=lambda i: (-w[i], l[i]))
    return order, w, l

def auto_resolve(results):
    for a, b in MATCHES:
        if (a,b) not in results:
            wa = TIER.get(AGENTS[a],1); wb = TIER.get(AGENTS[b],1)
            results[(a,b)] = a if random.random()<wa/(wa+wb) else b

def main():
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Option C — Phase de groupes")
    clock = pygame.time.Clock()
    fs = load_font(12); ft = load_font(10); fb = load_font(18); fm = load_font(14)

    results = {}    # {(a,b): winner_idx}
    fin_winner = None

    # Layout grille
    # Colonnes = agents (0..4), lignes = adversaires
    # Tableau croisé + classement à droite + finale en bas
    CELL = 48; MARGIN_X = 120; MARGIN_Y = 130
    AGENT_COL_W = 110

    def cell_rect(row, col):
        # row = agent A index dans MATCHES, col = match index
        pass

    # Layout alternatif : liste de matchs en 2 colonnes + classement + finale
    COL1_X = 60; COL2_X = 420; CLASS_X = 780; FIN_X = 1030
    ROW_H = 48; START_Y = 130

    def match_rect(idx):
        col = idx % 2; row = idx // 2
        x = COL1_X if col == 0 else COL2_X
        y = START_Y + row * ROW_H
        return x, y

    def clickable():
        boxes = []
        for i, (a,b) in enumerate(MATCHES):
            x, y = match_rect(i)
            if (a,b) not in results:
                boxes.append((pygame.Rect(x,        y+4, AGENT_COL_W, ROW_H-8), (a,b), a))
                boxes.append((pygame.Rect(x+AGENT_COL_W+30, y+4, AGENT_COL_W, ROW_H-8), (a,b), b))
        # Finale
        if len(results)==10:
            order, w, l = ranking(results)
            f1, f2 = order[0], order[1]
            if fin_winner is None:
                boxes.append((pygame.Rect(FIN_X, START_Y+50, 160, 40), 'fin', f1))
                boxes.append((pygame.Rect(FIN_X, START_Y+100, 160, 40), 'fin', f2))
        return boxes

    while True:
        mx, my = pygame.mouse.get_pos()
        boxes = clickable()
        hover_match, hover_agent = None, None
        for r, match, agent in boxes:
            if r.collidepoint(mx, my): hover_match, hover_agent = match, agent; break

        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type==pygame.KEYDOWN and e.key==pygame.K_ESCAPE):
                pygame.quit(); sys.exit()
            if e.type == pygame.KEYDOWN and e.key == pygame.K_r:
                auto_resolve(results)
            if e.type == pygame.MOUSEBUTTONDOWN and e.button==1:
                for r, match, agent in boxes:
                    if r.collidepoint(mx, my):
                        if match == 'fin':
                            fin_winner = agent
                        else:
                            results[match] = agent
                        break

        screen.fill(C_BG)
        t = fb.render("OPTION C  —  PHASE DE GROUPES (ROUND-ROBIN)", True, C_TITLE)
        screen.blit(t, (W//2-t.get_width()//2, 18))
        sub = ft.render("10 matchs  —  top 2 au classement vont en Finale  |  R = auto-résoudre  |  clic = forcer vainqueur", True, C_LBL)
        screen.blit(sub, (W//2-sub.get_width()//2, 50))

        # Headers
        for lbl, x in [("MATCHS DE GROUPE", COL1_X), ("", COL2_X),
                        ("CLASSEMENT", CLASS_X), ("FINALE", FIN_X)]:
            if lbl:
                l = ft.render(lbl, True, C_LBL)
                screen.blit(l, (x, 105))

        # ── Matchs ────────────────────────────────────────────────────────────
        for i, (a, b) in enumerate(MATCHES):
            x, y = match_rect(i)
            done = (a,b) in results
            w_idx = results.get((a,b))

            for agent, ax in [(a, x), (b, x+AGENT_COL_W+30)]:
                won  = done and w_idx == agent
                lost = done and w_idx != agent
                hov  = (hover_match==(a,b) and hover_agent==agent)
                bg   = C_WIN if won else (C_DIM if lost else C_BOX)
                bdr  = C_BDR if (won or hov) else (C_DIM_BDR if lost else C_DIM_BDR)
                col_t= C_WIN_TXT if won else (C_DIM_TXT if lost else C_TXT)
                pygame.draw.rect(screen, bg,   (ax, y+4, AGENT_COL_W, ROW_H-8))
                pygame.draw.rect(screen, bdr,  (ax, y+4, AGENT_COL_W, ROW_H-8), 2)
                name = fs.render(AGENTS[agent], True, col_t)
                screen.blit(name, (ax+6, y+4+(ROW_H-8)//2-name.get_height()//2))

            # "vs" entre les deux
            vs = ft.render("vs", True, C_LBL)
            screen.blit(vs, (x+AGENT_COL_W+6, y+(ROW_H)//2-vs.get_height()//2))

        # ── Classement ────────────────────────────────────────────────────────
        order, w_arr, l_arr = ranking(results)
        for rank, agent in enumerate(order):
            y = START_Y + rank * 60
            is_top2 = rank < 2 and len(results) == 10
            bg  = (38,30,8) if is_top2 else C_BOX
            bdr = C_FIN_BDR if is_top2 else C_BDR
            pygame.draw.rect(screen, bg,  (CLASS_X, y, 200, 50))
            pygame.draw.rect(screen, bdr, (CLASS_X, y, 200, 50), 2)
            rank_t = ft.render(f"#{rank+1}", True, bdr)
            screen.blit(rank_t, (CLASS_X+6, y+4))
            name_t = fs.render(AGENTS[agent], True, C_FIN_TXT if is_top2 else C_TXT)
            screen.blit(name_t, (CLASS_X+35, y+6))
            score_t = ft.render(f"{w_arr[agent]}W {l_arr[agent]}L", True, C_LBL)
            screen.blit(score_t, (CLASS_X+35, y+28))
            if is_top2:
                adv = ft.render("→ FINALE", True, C_FIN_BDR)
                screen.blit(adv, (CLASS_X+115, y+18))

        # ── Finale ────────────────────────────────────────────────────────────
        if len(results) == 10:
            order2, _, _ = ranking(results)
            f1, f2 = order2[0], order2[1]
            pygame.draw.rect(screen, C_BOX, (FIN_X-10, START_Y+20, 230, 160))
            pygame.draw.rect(screen, C_FIN_BDR, (FIN_X-10, START_Y+20, 230, 160), 2)
            for rank_f, agent in enumerate([f1, f2]):
                yf = START_Y + 50 + rank_f*50
                won  = fin_winner == agent
                lost = fin_winner is not None and fin_winner != agent
                hov  = (hover_match=='fin' and hover_agent==agent)
                bg   = C_WIN if won else (C_DIM if lost else C_BOX)
                bdr  = C_FIN_BDR if (won or hov) else (C_DIM_BDR if lost else C_BDR)
                col_t= C_WIN_TXT if won else (C_DIM_TXT if lost else C_TXT)
                pygame.draw.rect(screen, bg,  (FIN_X, yf, 160, 40))
                pygame.draw.rect(screen, bdr, (FIN_X, yf, 160, 40), 2)
                name = fs.render(AGENTS[agent], True, col_t)
                screen.blit(name, (FIN_X+8, yf+40//2-name.get_height()//2))

            if fin_winner is not None:
                champ = fm.render(AGENTS[fin_winner], True, (255,225,80))
                screen.blit(champ, (FIN_X, START_Y+200))
                sub2 = ft.render("RL CHAMPION", True, (200,165,45))
                screen.blit(sub2, (FIN_X, START_Y+230))

        prog = ft.render(f"Matchs joués : {len(results)}/10", True, C_LBL)
        screen.blit(prog, (COL1_X, H-30))
        hint = ft.render("CLIC = forcer vainqueur   R = auto-résoudre   ESC = quitter", True, C_LBL)
        screen.blit(hint, (W//2-hint.get_width()//2, H-30))
        pygame.display.flip(); clock.tick(FPS)

if __name__ == "__main__": main()
