from flask import Flask, render_template
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

app = Flask(__name__)

# Konfiguration der Teams, URLs und Filter
# Format: "TeamName": ["URL", "Include-Filter", "Exclude-Filter"]
# "Include": Dieser Begriff MUSS im Namen vorkommen (z.B. "II").
# "Exclude": Dieser Begriff darf NICHT vorkommen (z.B. "II" bei der Ersten).
# "Birkesdorf" oder "BTV" wird automatisch immer vorausgesetzt.

TEAMS = {
    "mC-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=424095", None, None],
    
    # wC1: Darf kein "II" haben
    "wC1-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=424246", None, "II"], 
    # wC2: Muss "II" haben
    "wC2-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=424246", "II", None],
    
    "mD-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=424301", None, None],
    
    # wD1: Darf kein "II" haben (somit wird die wD2 ausgeblendet, außer es ist ein Derby)
    "wD1-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=425685", None, "II"], 
    
    # wD2: Muss "II" haben (findet "TV Birkesdorf II")
    "wD2-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=425685", "II", None], 
    
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
        response = session.get(url, timeout=15)
        
        if response.status_code != 200:
            return [], []

        soup = BeautifulSoup(response.text, 'html.parser')
        tables = soup.find_all('table', {'class': 'result-set'})
        
        # --- TEAM CHECK FUNKTION ---
        def check_team_match(name):
            name_lower = name.lower()
            
            # 1. Ist es überhaupt unser Verein?
            if "birkesdorf" not in name_lower and "btv" not in name_lower:
                return False
            
            # 2. Include Check (Muss enthalten sein, z.B. "II")
            if filter_include:
                # Wir unterstützen String oder Liste
                if isinstance(filter_include, list):
                    match_any = False
                    for item in filter_include:
                        if item.lower() in name_lower: match_any = True
                    if not match_any: return False
                else:
                    if filter_include.lower() not in name_lower: return False
            
            # 3. Exclude Check (Darf NICHT enthalten sein)
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

            # --- A: LIGA TABELLE ---
            if "rang" in header_text and "punkte" in header_text:
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 8:
                        try:
                            # Rang
                            rang = cols[0].get_text(strip=True)
                            col_offset = 0
                            if not rang.isdigit():
                                if len(cols) > 1 and cols[1].get_text(strip=True).isdigit():
                                    rang = cols[1].get_text(strip=True)
                                    col_offset = 1
                            if not rang.isdigit(): continue

                            # Mannschaft
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

                            # Werte
                            punkte = cols[-1].get_text(strip=True)
                            diff = cols[-2].get_text(strip=True)
                            tore_val = cols[-3].get_text(strip=True)
                            n_val = cols[-4].get_text(strip=True)
                            u_val = cols[-5].get_text(strip=True)
                            s_val = cols[-6].get_text(strip=True)
                            spiele = cols[-7].get_text(strip=True)
                            
                            is_own = check_team_match(mannschaft)

                            league_table.append({
                                'rang': rang,
                                'mannschaft': mannschaft,
                                'spiele': spiele,
                                's': s_val,
                                'u': u_val,
                                'n': n_val,
                                'tore': tore_val,
                                'diff': diff,
                                'punkte': punkte,
                                'is_own': is_own
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
                
                if len(cols) > 2 and re.match(r'^\d{2}:\d{2}$', row_text_list[2]):
                    time_index = 2
                    potential_date = row_text_list[1]
                    if "." in potential_date: current_date = potential_date
                elif len(cols) > 0 and re.match(r'^\d{2}:\d{2}$', row_text_list[0]):
                    time_index = 0
                
                if time_index == -1: continue

                try:
                    if len(cols) <= time_index + 5: continue
                    zeit = row_text_list[time_index]
                    heim = row_text_list[time_index + 3]
                    gast = row_text_list[time_index + 4]
                    tore = row_text_list[time_index + 5]
                    
                    match_heim = check_team_match(heim)
                    match_gast = check_team_match(gast)
                    
                    if not match_heim and not match_gast: continue

                    pdf_link = None
                    for link in row.find_all('a', href=True):
                        href = link['href'].lower()
                        is_report = False
                        if 'download' in href or 'pdf' in href or 'meeting' in href or 'nudokument' in href:
                            is_report = True
                        img = link.find('img')
                        if img:
                            if 'pdf' in img.get('alt','').lower() or 'pdf' in img.get('src','').lower(): is_report = True
                        
                        if is_report:
                            pdf_link = urljoin(url, link['href'])
                            break 

                    games.append({
                        'datum': current_date,
                        'zeit': zeit,
                        'heim': heim,
                        'gast': gast,
                        'tore': tore,
                        'pdf': pdf_link
                    })
                except Exception: continue
                
    except Exception as e:
        print(f"Scrape Fehler: {e}")
        return [], []
    
    return games, league_table

@app.route('/')
def index():
    latest_results = []
    
    for team_name, config in TEAMS.items():
        url, include, exclude = config
        
        games, _ = scrape_games(url, filter_include=include, filter_exclude=exclude)
        
        played_games = [g for g in games if ":" in g.get('tore', '')]
        last_game = played_games[-1] if played_games else (games[0] if games else None)
            
        latest_results.append({
            'team': team_name,
            'game': last_game
        })

    return render_template('index.html', latest_results=latest_results)

@app.route('/team/<team_name>')
def team_detail(team_name):
    if team_name not in TEAMS:
        return "Team nicht gefunden", 404
    
    url, include, exclude = TEAMS[team_name]
    
    games, league_table = scrape_games(url, filter_include=include, filter_exclude=exclude)
    
    return render_template('team.html', team_name=team_name, games=games, league_table=league_table)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
