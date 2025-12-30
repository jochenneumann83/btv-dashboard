from flask import Flask, render_template, redirect, url_for
from flask_caching import Cache
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
from datetime import datetime
import locale

# Versuch, deutsche Locale für Datumsformate zu setzen
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
    name_lower = name.lower()
    
    # Basis-Check: Ist es überhaupt Birkesdorf?
    if "birkesdorf" not in name_lower and "btv" not in name_lower:
        return False
    
    # Ausschluss-Filter (z.B. keine "II")
    if filter_exclude:
        # Falls Liste
        if isinstance(filter_exclude, list):
            if any(e.lower() in name_lower for e in filter_exclude): return False
        # Falls String
        elif filter_exclude.lower() in name_lower: return False
            
    # Einschluss-Filter (z.B. muss "II" haben)
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
        
        # Alle Tabellen holen
        tables = soup.find_all('table', {'class': 'result-set'})
        
        for table in tables:
            # Überschriften analysieren, um Spalten-Index zu finden
            # Wir machen alles klein ("heim", "gast"), um sicher zu gehen
            headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
            
            # --- TABELLE (Rangliste) ---
            # Erkennungsmerkmal: Enthält "rang" und "punkte"
            if any("rang" in h for h in headers) and any("pkt" in h or "punkte" in h for h in headers):
                # Indizes finden (nicht starr, sondern dynamisch)
                try:
                    idx_rang = next(i for i, h in enumerate(headers) if "rang" in h or "rg." in h)
                    idx_team = next(i for i, h in enumerate(headers) if "mannschaft" in h or "team" in h)
                    idx_pkt = next(i for i, h in enumerate(headers) if "pkt" in h or "punkte" in h)
                    
                    # Optional: Tore / Diff
                    idx_tore = next((i for i, h in enumerate(headers) if "tore" in h), -1)
                    idx_diff = next((i for i, h in enumerate(headers) if "diff" in h), -1)
                    
                    # Zeilen durchgehen
                    rows = table.find_all('tr')[1:] # Header überspringen
                    for row in rows:
                        cols = row.find_all('td')
                        if len(cols) > max(idx_rang, idx_team, idx_pkt):
                            team_name = cols[idx_team].get_text(strip=True)
                            
                            # Daten sammeln
                            entry = {
                                'rang': cols[idx_rang].get_text(strip=True),
                                'mannschaft': team_name,
                                'punkte': cols[idx_pkt].get_text(strip=True),
                                'is_own': check_team_match(team_name, filter_include, filter_exclude),
                                # Defaults falls Spalten fehlen
                                'spiele': '', 's': '', 'u': '', 'n': '', 
                                'tore': cols[idx_tore].get_text(strip=True) if idx_tore != -1 else '',
                                'diff': cols[idx_diff].get_text(strip=True) if idx_diff != -1 else ''
                            }
                            
                            # Versuche Statistik (Spiele/S/U/N) zu füllen, falls möglich
                            # Meistens zwischen Team und Tore
                            # Einfache Heuristik: Wenn idx_team=2 und idx_tore=7, sind dazwischen die Stats
                            if idx_tore != -1 and idx_tore > idx_team + 4:
                                entry['spiele'] = cols[idx_team+1].get_text(strip=True)
                                entry['s'] = cols[idx_team+2].get_text(strip=True)
                                entry['u'] = cols[idx_team+3].get_text(strip=True)
                                entry['n'] = cols[idx_team+4].get_text(strip=True)
                                
                            league_table.append(entry)
                except StopIteration:
                    continue # Tabelle passt nicht zur Struktur

            # --- SPIELPLAN ---
            # Erkennungsmerkmal: Enthält "datum", "heim", "gast"
            elif any("datum" in h for h in headers) and any("heim" in h for h in headers):
                try:
                    # Spalten-Indizes ermitteln
                    idx_date = next(i for i, h in enumerate(headers) if "datum" in h or "tag" in h)
                    idx_time = next(i for i, h in enumerate(headers) if "zeit" in h or "uhr" in h)
                    idx_heim = next(i for i, h in enumerate(headers) if "heim" in h)
                    idx_gast = next(i for i, h in enumerate(headers) if "gast" in h)
                    idx_tore = next(i for i, h in enumerate(headers) if "tore" in h or "erg" in h)
                    
                    rows = table.find_all('tr')[1:]
                    current_date = "Unbekannt"
                    
                    for row in rows:
                        cols = row.find_all('td')
                        # Check ob Zeile genug Spalten hat
                        required_len = max(idx_date, idx_time, idx_heim, idx_gast, idx_tore)
                        if len(cols) <= required_len:
                            continue
                            
                        # Datum cachen (steht oft nur in der ersten Zeile des Tages)
                        date_text = cols[idx_date].get_text(strip=True)
                        if date_text and "." in date_text:
                            current_date = date_text
                        elif not date_text and current_date == "Unbekannt":
                            continue # Leere Zeile am Anfang überspringen
                            
                        zeit = cols[idx_time].get_text(strip=True)
                        heim = cols[idx_heim].get_text(strip=True)
                        gast = cols[idx_gast].get_text(strip=True)
                        tore = cols[idx_tore].get_text(strip=True)
                        
                        # Bereinigung: "ausgewertet" oder komische Zeichen entfernen
                        tore = tore.split(' ')[0] # Nimmt oft das Hauptergebnis, falls Halbzeit dabei steht
                        if "ausgewertet" in tore: tore = "?"
                        
                        # Prüfen: Ist es ein BTV Spiel?
                        # Wir checken BEIDE Teams
                        home_is_btv = check_team_match(heim, filter_include, filter_exclude)
                        guest_is_btv = check_team_match(gast, filter_include, filter_exclude)
                        
                        is_btv_game = home_is_btv or guest_is_btv
                        we_are_home = home_is_btv # True, wenn Heim == Birkesdorf
                        
                        # PDF Bericht suchen
                        pdf = None
                        for a in row.find_all('a', href=True):
                            href = a['href'].lower()
                            if 'pdf' in href or 'meeting' in href:
                                pdf = urljoin(url, a['href'])
                                break
                        
                        # Nur hinzufügen, wenn gültige Zeit (filtert oft Header-Wiederholungen)
                        if ":" in zeit:
                            games.append({
                                'datum': current_date,
                                'zeit': zeit,
                                'heim': heim,
                                'gast': gast,
                                'tore': tore,
                                'pdf': pdf,
                                'we_are_home': we_are_home,
                                'is_btv_game': is_btv_game
                            })
                            
                except StopIteration:
                    continue # Tabelle hat nicht die erwarteten Spalten

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
        
        # Nur BTV Spiele für das Dashboard
        our_games = [x for x in g if x['is_btv_game']]
        
        # Letztes Spiel
        played = [i for i in our_games if ":" in i['tore'] and i['tore'] != "?"]
        last = played[-1] if played else None
        
        # Nächstes Spiel
        nxt = None
        for i in our_games:
            # Kriterien: Kein Ergebnis, nicht "abgesagt"
            if ":" not in i['tore'] and "abge" not in i['tore'].lower():
                try:
                    gd = datetime.strptime(i['datum'], "%d.%m.%Y").date()
                    if gd >= today:
                        nxt = i
                        break
                except:
                    continue

        # Status (Sieg/Niederlage)
        status = None
        if last:
            try:
                tore_clean = last['tore'].replace(" ", "").strip()
                if ":" in tore_clean:
                    h_str, g_str = tore_clean.split(':')
                    h, g_s = int(h_str), int(g_str)
                    
                    if h == g_s: 
                        status = 'draw'
                    else:
                        if last['we_are_home']:
                            status = 'win' if h > g_s else 'loss'
                        else:
                            status = 'win' if g_s > h else 'loss'
            except:
                pass
                
        res.append({'team': team, 'game': last, 'next_game': nxt, 'status': status})
    
    # Sortierung
    res.sort(key=lambda x: x['team'])
    
    return render_template('index.html', latest_results=res)

@app.route('/team/<team_name>')
@cache.cached(timeout=180)
def team_detail(team_name):
    if team_name not in TEAMS:
        return redirect(url_for('index'))
        
    conf = TEAMS[team_name]
    
    games, league_table = scrape_games(conf[0], conf[1], conf[2])
    
    # Split
    btv_games = [x for x in games if x['is_btv_game']]
    other_games = [x for x in games if not x['is_btv_game']]
    
    return render_template(
        'team.html', 
        team_name=team_name, 
        games=btv_games, 
        other_games=other_games, 
        league_table=league_table
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
