from flask import Flask, render_template, redirect, url_for
from flask_caching import Cache
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
from datetime import datetime
import locale

# Versuche deutsche Datumsformatierung
try:
    locale.setlocale(locale.LC_TIME, 'de_DE.UTF-8')
except:
    pass

app = Flask(__name__)

# Cache Konfiguration (3 Minuten)
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 180})

# Deine Teams-Konfiguration
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

def check_team_match(name, filter_include=None, filter_exclude=None):
    """Prüft, ob ein Teamname 'unser' Team ist (Birkesdorf + Filter)"""
    if not name: return False
    name_lower = name.lower()
    
    # Basis: Muss Birkesdorf oder BTV enthalten
    if "birkesdorf" not in name_lower and "btv" not in name_lower:
        return False
    
    # Ausschluss (z.B. keine 'II' für die erste Mannschaft)
    if filter_exclude:
        if isinstance(filter_exclude, list):
            if any(e.lower() in name_lower for e in filter_exclude): return False
        elif filter_exclude.lower() in name_lower: return False
            
    # Einschluss (z.B. muss 'II' enthalten)
    if filter_include:
        if isinstance(filter_include, list):
            if not any(i.lower() in name_lower for i in filter_include): return False
        elif filter_include.lower() not in name_lower: return False
            
    return True

def scrape_games(url, filter_include=None, filter_exclude=None):
    games = []
    league_table = []
    
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        response = session.get(url, timeout=10)
        
        if response.status_code != 200:
            return [], []
            
        soup = BeautifulSoup(response.text, 'html.parser')
        tables = soup.find_all('table', {'class': 'result-set'})
        
        for table in tables:
            # Wir holen uns alle Header-Texte in Kleinbuchstaben
            headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
            
            # --- TABELLE (Rangliste) ---
            if any("rang" in h for h in headers) and any("pkt" in h or "punkte" in h for h in headers):
                rows = table.find_all('tr')[1:] # Header überspringen
                for row in rows:
                    cols = row.find_all('td')
                    # Wir suchen die Spalte mit dem Teamnamen (meist index 2)
                    if len(cols) > 2:
                        # Einfache Heuristik: Rang ist meist Col 1, Team Col 2 oder 3
                        # Wir nehmen an: 2. Spalte mit Text ist Team
                        try:
                            # Standard nuLiga: Rang | (Bild) | Team | ...
                            idx_team = 2
                            if not cols[1].get_text(strip=True): # Falls Spalte 2 leer/Bild ist
                                idx_team = 2
                            else:
                                idx_team = 2 # Oft ist Spalte 1 Rang, Spalte 2 Bild/Leer, Spalte 3 Team
                            
                            # Fallback: Suche erste Spalte mit langem Text
                            for i, c in enumerate(cols):
                                if len(c.get_text(strip=True)) > 5 and i > 0:
                                    idx_team = i
                                    break
                            
                            t_name = cols[idx_team].get_text(strip=True)
                            
                            league_table.append({
                                'rang': cols[0].get_text(strip=True),
                                'mannschaft': t_name,
                                'spiele': cols[-7].get_text(strip=True) if len(cols)>8 else '',
                                's': cols[-6].get_text(strip=True) if len(cols)>8 else '',
                                'u': cols[-5].get_text(strip=True) if len(cols)>8 else '',
                                'n': cols[-4].get_text(strip=True) if len(cols)>8 else '',
                                'tore': cols[-3].get_text(strip=True) if len(cols)>8 else '',
                                'diff': cols[-2].get_text(strip=True) if len(cols)>8 else '',
                                'punkte': cols[-1].get_text(strip=True),
                                'is_own': check_team_match(t_name, filter_include, filter_exclude)
                            })
                        except: continue

            # --- SPIELPLAN ---
            elif any("datum" in h for h in headers):
                rows = table.find_all('tr')[1:]
                
                # Versuch, Spalten anhand der Header zu finden (sicherer als festes Zählen)
                idx_datum = -1
                idx_zeit = -1
                idx_heim = -1
                idx_gast = -1
                idx_tore = -1
                
                for i, h in enumerate(headers):
                    if "datum" in h or "tag" in h: idx_datum = i
                    elif "zeit" in h or "uhr" in h: idx_zeit = i
                    elif "heim" in h: idx_heim = i
                    elif "gast" in h: idx_gast = i
                    elif "tore" in h or "erg" in h: idx_tore = i
                
                # Fallback, falls Header komisch benannt sind (passiert bei nuLiga manchmal)
                if idx_heim == -1: idx_heim = 4 # Standardannahme
                if idx_gast == -1: idx_gast = 5
                if idx_tore == -1: idx_tore = 6
                
                current_date = "Unbekannt"
                
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 5: continue
                    
                    # Datum merken
                    if idx_datum != -1 and cols[idx_datum].get_text(strip=True):
                         d_txt = cols[idx_datum].get_text(strip=True)
                         if "." in d_txt: current_date = d_txt
                    
                    # Werte auslesen
                    try:
                        heim = cols[idx_heim].get_text(strip=True)
                        gast = cols[idx_gast].get_text(strip=True)
                        zeit = cols[idx_zeit].get_text(strip=True) if idx_zeit != -1 else ""
                        
                        # Tore oder "-"
                        tore = "-"
                        if idx_tore != -1 and len(cols) > idx_tore:
                            tore = cols[idx_tore].get_text(strip=True).split(' ')[0] # "20:20 (10:10)" -> "20:20"
                            if "ausgewertet" in tore: tore = "?"
                        
                        if ":" not in zeit: continue # Zeile ohne Zeit ist meist keine Spielzeile
                        
                        # PDF Link suchen
                        pdf = None
                        for a in row.find_all('a', href=True):
                             if 'pdf' in a['href'].lower() or 'meeting' in a['href'].lower():
                                 pdf = urljoin(url, a['href']); break
                        
                        # Check: Sind wir Heim oder Gast?
                        is_home = check_team_match(heim, filter_include, filter_exclude)
                        is_guest = check_team_match(gast, filter_include, filter_exclude)
                        
                        games.append({
                            'datum': current_date,
                            'zeit': zeit,
                            'heim': heim,
                            'gast': gast,
                            'tore': tore,
                            'pdf': pdf,
                            'we_are_home': is_home,     # True wenn wir Heim sind
                            'is_btv_game': is_home or is_guest # True wenn wir beteiligt sind
                        })
                    except: continue

    except Exception as e:
        print(f"Fehler bei {url}: {e}")
        return [], []
        
    return games, league_table

@app.route('/')
@cache.cached(timeout=180)
def index():
    res = []
    today = datetime.now().date()
    
    for team, conf in TEAMS.items():
        g, _ = scrape_games(conf[0], conf[1], conf[2])
        
        # Wichtig: Für Dashboard nur UNSERE Spiele filtern
        our_games = [x for x in g if x['is_btv_game']]
        
        played = [i for i in our_games if ":" in i['tore'] and i['tore'] != "?"]
        last = played[-1] if played else None
        
        nxt = None
        for i in our_games:
            if ":" not in i['tore'] and "abge" not in i['tore'].lower():
                try:
                    gd = datetime.strptime(i['datum'], "%d.%m.%Y").date()
                    if gd >= today: nxt = i; break
                except: continue

        status = None
        if last:
            try:
                t_clean = last['tore'].replace(" ", "").strip()
                if ":" in t_clean:
                    h, g_s = map(int, t_clean.split(':'))
                    if h == g_s: status = 'draw'
                    else:
                        if last['we_are_home']: status = 'win' if h > g_s else 'loss'
                        else: status = 'win' if g_s > h else 'loss'
            except: pass
            
        res.append({'team': team, 'game': last, 'next_game': nxt, 'status': status})
    
    res.sort(key=lambda x: x['team'])
    return render_template('index.html', latest_results=res)

@app.route('/team/<team_name>')
@cache.cached(timeout=180)
def team_detail(team_name):
    if team_name not in TEAMS: return redirect(url_for('index'))
    conf = TEAMS[team_name]
    
    games, league_table = scrape_games(conf[0], conf[1], conf[2])
    
    # HIER TEILEN WIR AUF: BTV Spiele vs. Sonstige
    btv_games = [x for x in games if x['is_btv_game']]
    other_games = [x for x in games if not x['is_btv_game']]
    
    return render_template('team.html', 
                           team_name=team_name, 
                           games=btv_games, 
                           other_games=other_games, 
                           league_table=league_table)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
