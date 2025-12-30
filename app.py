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

# Konfiguration der Mannschaften
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
    """Prüft, ob ein Teamname unseren Kriterien entspricht (Birkesdorf + Filter)"""
    if not name: return False
    name_lower = name.lower()
    
    # Basis: Muss Birkesdorf oder BTV enthalten
    if "birkesdorf" not in name_lower and "btv" not in name_lower:
        return False
    
    # Ausschluss (z.B. keine "II" für die erste Mannschaft)
    if filter_exclude:
        if isinstance(filter_exclude, list):
            if any(e.lower() in name_lower for e in filter_exclude): return False
        elif filter_exclude.lower() in name_lower: return False
            
    # Einschluss (z.B. muss "II" haben)
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
            headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
            
            # --- TABELLE (Rangliste) ---
            if any("rang" in h for h in headers) and any("pkt" in h or "punkte" in h for h in headers):
                rows = table.find_all('tr')[1:]
                for row in rows:
                    cols = row.find_all('td')
                    # Wir suchen eine Spalte mit einem Teamnamen (meist index 2 oder 3)
                    if len(cols) > 2:
                        # Fallback Logik: Finde die Spalte, die wie ein Team aussieht
                        idx_team = 2
                        for i, c in enumerate(cols):
                            txt = c.get_text(strip=True)
                            # Teamname ist länger als 5 Zeichen und keine Zahl
                            if len(txt) > 5 and not txt.replace('.','').isdigit() and i > 0:
                                idx_team = i
                                break
                        
                        try:
                            t_name = cols[idx_team].get_text(strip=True)
                            league_table.append({
                                'rang': cols[0].get_text(strip=True),
                                'team': t_name, # WICHTIG: Hier 'team' statt 'mannschaft' für Kompatibilität mit template
                                'spiele': cols[-7].get_text(strip=True) if len(cols)>8 else '',
                                's': cols[-6].get_text(strip=True) if len(cols)>8 else '',
                                'u': cols[-5].get_text(strip=True) if len(cols)>8 else '',
                                'n': cols[-4].get_text(strip=True) if len(cols)>8 else '',
                                'tore': cols[-3].get_text(strip=True) if len(cols)>8 else '',
                                'diff': cols[-2].get_text(strip=True) if len(cols)>8 else '',
                                'punkte': cols[-1].get_text(strip=True),
                                'is_us': check_team_match(t_name, filter_include, filter_exclude)
                            })
                        except: continue

            # --- SPIELPLAN ---
            elif any("datum" in h for h in headers):
                rows = table.find_all('tr')[1:]
                current_date = "Unbekannt"
                
                # Datum-Spalte finden
                idx_datum = 0 # Standard
                for i, h in enumerate(headers):
                    if "datum" in h or "tag" in h: idx_datum = i; break

                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 5: continue
                    
                    # Datum aktualisieren
                    if len(cols) > idx_datum:
                        d_txt = cols[idx_datum].get_text(strip=True)
                        if "." in d_txt and len(d_txt) > 5: 
                            current_date = d_txt
                    
                    # --- INTELLIGENTE TEAM-SUCHE (Der Fix für "Lamm") ---
                    # 1. Wir suchen, in welcher Spalte "Birkesdorf" steht
                    my_index = -1
                    for i, col in enumerate(cols):
                        if check_team_match(col.get_text(strip=True), filter_include, filter_exclude):
                            my_index = i
                            break
                    
                    # Wenn wir uns nicht finden, ist es kein Spiel von uns -> überspringen
                    if my_index == -1:
                        continue

                    # 2. Nachbarn prüfen: Wo steht der Gegner?
                    # Standard nuLiga: Heim(Links) - Gast(Rechts)
                    
                    heim = "?"
                    gast = "?"
                    we_are_home = False
                    
                    # Text links von uns holen
                    left_text = cols[my_index - 1].get_text(strip=True) if my_index > 0 else ""
                    
                    # Prüfen: Ist der Text links ein Teamname?
                    # Kriterien: Länger als 2 Zeichen, keine Uhrzeit (doppelpunkt), keine reine Zahl
                    is_left_team = len(left_text) > 3 and ":" not in left_text and not left_text.isdigit()
                    
                    if is_left_team:
                        # Wenn links ein Team steht, sind wir GAST (Rechts)
                        heim = left_text
                        gast = cols[my_index].get_text(strip=True)
                        we_are_home = False
                    else:
                        # Wenn links nichts Sinnvolles steht (z.B. Uhrzeit oder leer), sind wir HEIM (Links)
                        heim = cols[my_index].get_text(strip=True)
                        # Gegner steht rechts
                        if my_index + 1 < len(cols):
                            gast = cols[my_index + 1].get_text(strip=True)
                        else:
                            gast = "?"
                        we_are_home = True

                    # Restliche Daten holen (Zeit/Tore)
                    # Wir suchen einfach nach einer Uhrzeit (Format 00:00) in der ganzen Zeile
                    zeit = ""
                    for col in cols:
                        txt = col.get_text(strip=True)
                        if re.match(r'^\d{1,2}:\d{2}$', txt):
                            zeit = txt
                            break
                    
                    if not zeit: continue # Ohne Zeit ist es oft kein echtes Spiel

                    # Tore suchen (Format Zahl:Zahl)
                    tore = "-"
                    for col in cols:
                        txt = col.get_text(strip=True)
                        if re.search(r'\d+:\d+', txt) and "Tag" not in txt: # "Tag" Filter für Header
                             tore = txt.split(' ')[0] # Halbzeit entfernen
                             if "ausgewertet" in tore: tore = "?"
                             break
                    
                    # PDF Link
                    pdf = None
                    for a in row.find_all('a', href=True):
                         if 'pdf' in a['href'].lower() or 'meeting' in a['href'].lower():
                             pdf = urljoin(url, a['href']); break

                    games.append({
                        'datum': current_date,
                        'zeit': zeit,
                        'heim': heim,
                        'gast': gast,
                        'tore': tore,
                        'pdf': pdf,
                        'we_are_home': we_are_home
                    })

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
        
        played = [i for i in g if ":" in i['tore'] and i['tore'] != "?"]
        last = played[-1] if played else None
        
        nxt = None
        for i in g:
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
    if team_name not in TEAMS:
        return redirect(url_for('index'))
    
    conf = TEAMS[team_name]
    games, league_table = scrape_games(conf[0], conf[1], conf[2])
    
    # Original Logik: Keine Aufteilung BTV/Sonstige, sondern nur unsere Spiele
    # (Da scrape_games jetzt filtert, sind 'games' automatisch nur unsere)
    
    return render_template('team.html', team_name=team_name, games=games, league_table=league_table)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
