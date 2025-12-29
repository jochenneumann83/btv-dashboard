from flask import Flask, render_template
from flask_caching import Cache
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
from datetime import datetime

app = Flask(__name__)

# --- KONFIGURATION CACHE (3 Minuten) ---
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 180})

# --- TEAM KONFIGURATION ---
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

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

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
        
        def check_team_match(name):
            name_lower = name.lower()
            if "birkesdorf" not in name_lower and "btv" not in name_lower: return False
            if filter_include:
                if isinstance(filter_include, list):
                    match_any = False
                    for item in filter_include:
                        if item.lower() in name_lower: match_any = True
                    if not match_any: return False
                else:
                    if filter_include.lower() not in name_lower: return False
            if filter_exclude:
                if isinstance(filter_exclude, list):
                    for item in filter_exclude:
                        if item.lower() in name_lower: return False
                else:
                    if filter_exclude.lower() in name_lower: return False
            return True

        for table in tables:
            headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
            header_text = "".join(headers)
            rows = table.find_all('tr')

            # --- A: TABELLE ---
            if "rang" in header_text and "punkte" in header_text:
                is_long_format = "tore" in header_text or "diff" in header_text
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 6:
                        try:
                            rang = cols[0].get_text(strip=True)
                            col_offset = 0
                            if not rang.isdigit():
                                if len(cols) > 1 and cols[1].get_text(strip=True).isdigit():
                                    rang = cols[1].get_text(strip=True)
                                    col_offset = 1
                            if not rang.isdigit(): continue

                            possible_team_col = col_offset + 1
                            mannschaft = "Unbekannt"
                            if len(cols) > possible_team_col + 1:
                                text_a = cols[possible_team_col].get_text(strip=True)
                                text_b = cols[possible_team_col + 1].get_text(strip=True)
                                if len(text_b) > len(text_a) and len(text_b) > 3:
                                    mannschaft = text_b
                                else:
                                    mannschaft = text_a
                            else:
                                mannschaft = cols[possible_team_col].get_text(strip=True)

                            if is_long_format:
                                punkte = cols[-1].get_text(strip=True)
                                diff = cols[-2].get_text(strip=True)
                                tore_val = cols[-3].get_text(strip=True)
                                n_val = cols[-4].get_text(strip=True)
                                u_val = cols[-5].get_text(strip=True)
                                s_val = cols[-6].get_text(strip=True)
                                spiele = cols[-7].get_text(strip=True)
                            else:
                                punkte = cols[-1].get_text(strip=True)
                                n_val = cols[-2].get_text(strip=True)
                                u_val = cols[-3].get_text(strip=True)
                                s_val = cols[-4].get_text(strip=True)
                                spiele = cols[-5].get_text(strip=True)
                                diff = "-"
                                tore_val = "-"

                            is_own = check_team_match(mannschaft)
                            league_table.append({
                                'rang': rang, 'mannschaft': mannschaft, 'spiele': spiele,
                                's': s_val, 'u': u_val, 'n': n_val, 'tore': tore_val,
                                'diff': diff, 'punkte': punkte, 'is_own': is_own
                            })
                        except Exception: continue
                continue 

            # --- B: SPIELPLAN ---
            current_date = "Unbekannt"
            for row in rows:
                cols = row.find_all('td')
                if not cols: continue

                time_index = -1
                row_text_list = [c.get_text(strip=True) for c in cols]
                
                # Datum Parsing
                if len(cols) > 2 and "." in row_text_list[1]:
                     if re.search(r'\d{1,2}\.\d{1,2}\.', row_text_list[1]):
                        raw_date = row_text_list[1]
                        match = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4})', raw_date)
                        if match: current_date = match.group(1)
                        else: current_date = raw_date
                
                for i, txt in enumerate(row_text_list):
                    if i > 5: break 
                    if re.search(r'\d{1,2}:\d{2}', txt):
                        time_index = i
                        break
                
                if time_index == -1: continue
                zeit = row_text_list[time_index]
                
                my_team_idx = -1
                for i in range(time_index + 1, len(cols)):
                    txt = row_text_list[i]
                    if check_team_match(txt):
                        my_team_idx = i
                        break
                
                if my_team_idx == -1: continue 

                heim = "???"
                gast = "???"
                tore = "-"
                
                # --- LOGIK FÜR ERGEBNIS & HEIM/GAST ---
                has_next = (my_team_idx + 1 < len(cols))
                next_val = row_text_list[my_team_idx + 1] if has_next else ""
                
                # Ist das nächste Feld ein Ergebnis (z.B. "24:22")?
                is_score = re.search(r'\d+:\d+', next_val) or "abges" in next_val.lower()
                
                if is_score:
                    # Fall 1: Spiel VORBEI (Es gibt ein Ergebnis)
                    # Aufbau: [Gegner] [ICH] [Ergebnis]  <- Ich bin Gast
                    # Oder:   [ICH] [Gegner] [Ergebnis]  <- Ich bin Heim
                    # Wir prüfen, was links steht.
                    
                    # Da my_team_idx unsere Position ist:
                    # Wenn next_val das Ergebnis ist, ist rechts vom Gegner das Ergebnis.
                    # Das bedeutet: [Pos X] [Pos X+1] [Pos X+2 = Ergebnis]
                    
                    # Moment, einfacher:
                    # nuLiga Standard: Heim | Gast | Tore
                    # Wenn ich an Pos X bin und Pos X+1 ist das Ergebnis -> Ich bin GAST (X-1 war Heim)
                    # Wenn ich an Pos X bin und Pos X+1 ist Gegner und Pos X+2 ist Ergebnis -> Ich bin HEIM
                    
                    if re.search(r'\d+:\d+', next_val) or "abges" in next_val.lower():
                        # Wenn direkt neben mir das Ergebnis steht, war ich Gast
                        gast = row_text_list[my_team_idx]
                        heim = row_text_list[my_team_idx - 1]
                        tore = next_val
                    else:
                        # Fallback (Sollte durch Logik oben abgedeckt sein, aber sicher ist sicher)
                        heim = row_text_list[my_team_idx]
                        gast = next_val
                        if my_team_idx + 2 < len(cols):
                            tore = row_text_list[my_team_idx + 2]
                
                else:
                    # Fall 2: ZUKUNFT (Kein Ergebnis)
                    # Aufbau: Heim | Gast
                    # Problem: Rechts ist oft leer oder "-" oder "v".
                    
                    # Wir schauen uns die Nachbarn an:
                    # Nachbar RECHTS (my_team_idx + 1)
                    right_val = row_text_list[my_team_idx + 1] if my_team_idx + 1 < len(cols) else ""
                    # Nachbar LINKS (my_team_idx - 1)
                    left_val = row_text_list[my_team_idx - 1] if my_team_idx > 0 else ""
                    
                    # Ist Rechts ein Teamname? (Länger als 2, keine Uhrzeit, keine reine Zahl für Halle)
                    right_is_team = len(right_val) > 2 and not re.search(r'\d{1,2}:\d{2}', right_val) and not right_val.isdigit()
                    
                    # Ist Links ein Teamname? (Länger als 2, keine Uhrzeit, keine reine Zahl für Halle)
                    left_is_team = len(left_val) > 2 and not re.search(r'\d{1,2}:\d{2}', left_val) and not left_val.isdigit()

                    if right_is_team:
                        # Rechts steht wer -> Ich bin HEIM
                        heim = row_text_list[my_team_idx]
                        gast = right_val
                    elif left_is_team:
                        # Links steht wer -> Ich bin GAST
                        heim = left_val
                        gast = row_text_list[my_team_idx]
                    else:
                        # Fallback (Passiert selten): Wir nehmen an wir sind Heim
                        heim = row_text_list[my_team_idx]
                        gast = right_val if right_val else "???"

                # PDF Link
                pdf_link = None
                for link in row.find_all('a', href=True):
                    href = link['href'].lower()
                    is_report = False
                    if 'download' in href or 'pdf' in href or 'meeting' in href or 'nudokument' in href: is_report = True
                    img = link.find('img')
                    if img:
                        if 'pdf' in img.get('alt','').lower() or 'pdf' in img.get('src','').lower(): is_report = True
                    if is_report:
                        pdf_link = urljoin(url, link['href'])
                        break 
                
                we_are_home = check_team_match(heim)

                games.append({
                    'datum': current_date, 'zeit': zeit, 'heim': heim, 'gast': gast,
                    'tore': tore, 'pdf': pdf_link, 'we_are_home': we_are_home
                })
                
    except Exception as e:
        print(f"Scrape Fehler: {e}")
        return [], []
    
    return games, league_table

@app.route('/')
@cache.cached(timeout=180)
def index():
    latest_results = []
    today = datetime.now()
    
    for team_name, config in TEAMS.items():
        url, include, exclude = config
        games, _ = scrape_games(url, filter_include=include, filter_exclude=exclude)
        
        # 1. Letztes Spiel
        played_games = [g for g in games if ":" in g.get('tore', '')]
        last_game = played_games[-1] if played_games else None
        
        # 2. Nächstes Spiel
        next_game = None
        for g in games:
            if ":" in g.get('tore', '') or "abges" in g.get('tore', '').lower():
                continue
            try:
                g_date_str = g.get('datum', '')
                if not g_date_str: continue
                g_date = datetime.strptime(g_date_str, "%d.%m.%Y")
                if g_date.date() >= today.date():
                    next_game = g
                    break
            except Exception:
                continue
        
        # 3. Ampel Status
        traffic_light = None
        if last_game and ":" in last_game['tore']:
            try:
                tore_str = last_game['tore'].strip()
                t_heim, t_gast = map(int, tore_str.split(':'))
                we_home = last_game['we_are_home']
                if t_heim == t_gast: traffic_light = 'draw'
                elif we_home: traffic_light = 'win' if t_heim > t_gast else 'loss'
                else: traffic_light = 'win' if t_gast > t_heim else 'loss'
            except: pass

        latest_results.append({
            'team': team_name,
            'game': last_game,
            'next_game': next_game,
            'status': traffic_light
        })

    # SORTIERUNG: Erst Name, dann Datum (Neuestes oben)
    def get_last_game_date(item):
        if item['game'] and item['game'].get('datum'):
            try: return datetime.strptime(item['game']['datum'], "%d.%m.%Y")
            except: return datetime.min 
        return datetime.min
    
    latest_results.sort(key=lambda x: x['team'])
    latest_results.sort(key=get_last_game_date, reverse=True)

    return render_template('index.html', latest_results=latest_results)

@app.route('/team/<team_name>')
@cache.cached(timeout=180)
def team_detail(team_name):
    if team_name not in TEAMS: return "Team nicht gefunden", 404
    url, include, exclude = TEAMS[team_name]
    games, league_table = scrape_games(url, filter_include=include, filter_exclude=exclude)
    return render_template('team.html', team_name=team_name, games=games, league_table=league_table)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
