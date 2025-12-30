from flask import Flask, render_template
from flask_caching import Cache
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
from datetime import datetime
import locale

# Versuch, deutsche Locale für Datumsformate zu setzen (optional)
try:
    locale.setlocale(locale.LC_TIME, 'de_DE.UTF-8')
except:
    pass

app = Flask(__name__)

cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 180})

# Deine Teams-Konfiguration (unverändert übernommen)
TEAMS = {
    "mC-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=424095", None, None],
    "wC1-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=424246", None, ["II", "2"]], 
    "wC2-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=424246", ["II", "2"], None],
    "mD-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=424301", None, None],
    "wD1-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=425685", None, ["II", "2"]], 
    "wD2-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=425685", ["II", "2"], None], 
    "mE1-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=424179", None, None],
    "mE2-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/teamPortrait?teamtable=2118365&pageState=vorrunde&championship=AD+25%2F26&group=423969", None, None],
    "wE-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=424213", None, None]
}

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

def scrape_games(url, filter_include=None, filter_exclude=None):
    games = []
    league_table = []
    
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        response = session.get(url, timeout=10)
        if response.status_code != 200: return [], []
        soup = BeautifulSoup(response.text, 'html.parser')
        tables = soup.find_all('table', {'class': 'result-set'})
        
        def check_team_match(name):
            name_lower = name.lower()
            if "birkesdorf" not in name_lower and "btv" not in name_lower: return False
            if filter_include:
                if isinstance(filter_include, list):
                    if not any(i.lower() in name_lower for i in filter_include): return False
                elif filter_include.lower() not in name_lower: return False
            if filter_exclude:
                if isinstance(filter_exclude, list):
                    if any(e.lower() in name_lower for e in filter_exclude): return False
                elif filter_exclude.lower() in name_lower: return False
            return True

        for table in tables:
            headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
            header_text = "".join(headers)
            rows = table.find_all('tr')

            # --- TABELLE (bleibt gleich) ---
            if "rang" in header_text and "punkte" in header_text:
                is_long = "tore" in header_text or "diff" in header_text
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 6:
                        try:
                            r_txt = cols[0].get_text(strip=True)
                            off = 1 if not r_txt.isdigit() and len(cols) > 1 and cols[1].get_text(strip=True).isdigit() else 0
                            rang = cols[off].get_text(strip=True)
                            if not rang.isdigit(): continue
                            mannschaft = cols[off+2].get_text(strip=True) if len(cols[off+1].get_text(strip=True)) < 3 else cols[off+1].get_text(strip=True)
                            if is_long:
                                p, d, t, n, u, s, sp = cols[-1].text, cols[-2].text, cols[-3].text, cols[-4].text, cols[-5].text, cols[-6].text, cols[-7].text
                            else:
                                p, n, u, s, sp = cols[-1].text, cols[-2].text, cols[-3].text, cols[-4].text, cols[-5].text
                                d, t = "-", "-"
                            league_table.append({'rang': rang, 'mannschaft': mannschaft, 'spiele': sp, 's': s, 'u': u, 'n': n, 'tore': t, 'diff': d, 'punkte': p, 'is_own': check_team_match(mannschaft)})
                        except: continue
                continue 

            # --- SPIELPLAN ---
            current_date = "Unbekannt"
            for row in rows:
                cols = row.find_all('td')
                if not cols: continue
                row_texts = [c.get_text(strip=True) for c in cols]
                
                # Datum finden
                date_match = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4})', "".join(row_texts[:4]))
                if date_match: current_date = date_match.group(1)

                # Zeitanker finden
                t_idx = -1
                for i, txt in enumerate(row_texts[:6]):
                    if re.search(r'\d{1,2}:\d{2}', txt):
                        t_idx = i
                        break
                if t_idx == -1: continue

                # NEU: Unterscheidung zwischen "Wir spielen" und "Andere spielen"
                
                # 1. Prüfen, ob wir (BTV) beteiligt sind
                potential_indices = [i for i, txt in enumerate(row_texts) if check_team_match(txt)]
                is_btv_game = len(potential_indices) > 0
                
                heim, gast, tore = "-", "-", "-"
                we_home = False
                
                if is_btv_game:
                    # -- Logik für BTV-Spiele (wie vorher) --
                    my_idx = potential_indices[0]
                    
                    # Ergebnis suchen
                    score_idx = -1
                    for i in range(my_idx, len(row_texts)):
                        if re.search(r'\d+:\d+', row_texts[i]):
                            score_idx = i
                            break
                    
                    if score_idx != -1: # Vorbei
                        tore = row_texts[score_idx]
                        if score_idx == my_idx + 1:
                            gast, heim = row_texts[my_idx], row_texts[my_idx-1]
                            we_home = False
                        else:
                            heim, gast = row_texts[my_idx], row_texts[my_idx+1]
                            we_home = True
                    else: # Zukunft
                        tore = "-"
                        left_n = row_texts[my_idx-1] if my_idx > 0 else ""
                        right_n = row_texts[my_idx+1] if my_idx+1 < len(row_texts) else ""
                        if len(right_n) > 3 and not any(char.isdigit() for char in right_n[:2]):
                            heim, gast, we_home = row_texts[my_idx], right_n, True
                        else:
                            heim, gast, we_home = left_n, row_texts[my_idx], False
                            
                else:
                    # -- Logik für Sonstige Spiele (Fremdspiele) --
                    # Annahme Standard-Layout: Zeit(t_idx) | Halle | Heim | Gast | Tore
                    # Meistens: Heim = t_idx + 2, Gast = t_idx + 3
                    try:
                        if len(row_texts) > t_idx + 3:
                            heim = row_texts[t_idx + 2]
                            gast = row_texts[t_idx + 3]
                            
                            # Ergebnis suchen (rechts von Gast)
                            for k in range(t_idx + 4, len(row_texts)):
                                if re.search(r'\d+:\d+', row_texts[k]):
                                    tore = row_texts[k]
                                    break
                    except:
                        continue # Wenn Struktur ganz anders, überspringen

                # PDF suchen
                pdf = None
                for a in row.find_all('a', href=True):
                    if any(x in a['href'].lower() for x in ['pdf', 'download', 'meeting', 'nudokument']):
                        pdf = urljoin(url, a['href']); break

                games.append({
                    'datum': current_date, 
                    'zeit': row_texts[t_idx], 
                    'heim': heim, 
                    'gast': gast, 
                    'tore': tore, 
                    'pdf': pdf, 
                    'we_are_home': we_home,
                    'is_btv_game': is_btv_game  # NEUES FELD ZUM FILTERN
                })
                
    except Exception as e:
        print(f"Fehler bei {url}: {e}"); return [], []
    return games, league_table

@app.route('/')
@cache.cached(timeout=180)
def index():
    res = []; today = datetime.now().date()
    for team, conf in TEAMS.items():
        g, _ = scrape_games(conf[0], conf[1], conf[2])
        
        # WICHTIG: Für das Dashboard nur UNSERE Spiele verwenden
        our_games = [x for x in g if x['is_btv_game']]
        
        played = [i for i in our_games if ":" in i['tore']]
        last = played[-1] if played else None
        
        # Nächstes Spiel finden
        nxt = None
        for i in our_games:
            if ":" not in i['tore'] and "abge" not in i['tore'].lower():
                try:
                    # Prüfen ob Spiel in Zukunft/Heute liegt
                    gd = datetime.strptime(i['datum'], "%d.%m.%Y").date()
                    if gd >= today:
                        nxt = i
                        break
                except: continue

        status = None
        if last and ":" in last['tore']:
            try:
                h, g_s = map(int, last['tore'].split(':'))
                if h == g_s: status = 'draw'
                else: status = 'win' if (h > g_s if last['we_are_home'] else g_s > h) else 'loss'
            except: pass
        res.append({'team': team, 'game': last, 'next_game': nxt, 'status': status})
    
    res.sort(key=lambda x: x['team'])
    # Sortiere nach Datum des letzten Spiels (optional)
    res.sort(key=lambda x: datetime.strptime(x['game']['datum'], "%d.%m.%Y") if x['game'] else datetime.min, reverse=True)
    return render_template('index.html', latest_results=res)

@app.route('/team/<team_name>')
@cache.cached(timeout=180)
def team_detail(team_name):
    c = TEAMS.get(team_name)
    if not c: return "Team nicht gefunden", 404
    
    g, t = scrape_games(c[0], c[1], c[2])
    
    # HIER WIRD AUFGETEILT: BTV-Spiele vs. Rest
    btv_games = [x for x in g if x['is_btv_game']]
    other_games = [x for x in g if not x['is_btv_game']]
    
    return render_template('team.html', 
                           team_name=team_name, 
                           games=btv_games, 
                           other_games=other_games, 
                           league_table=t)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
