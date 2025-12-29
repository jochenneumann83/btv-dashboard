from flask import Flask, render_template
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

app = Flask(__name__)

# Konfiguration der Teams, URLs und Filter
TEAMS = {
    "mC-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=424095", None, None],
    "wC1-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=424246", "Birkesdorf", "II"], 
    "wC2-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=424246", "Birkesdorf II", None],
    "mD-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=424301", None, None],
    "wD1-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=425685", None, None],
    "wD2-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=425685", None, None],
    "mE1-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=424179", None, None],
    "mE2-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/teamPortrait?teamtable=2118365&pageState=vorrunde&championship=AD+25%2F26&group=423969", None, None],
    "wE-Jugend": ["https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=424213", None, None]
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

def scrape_games(url, filter_include=None, filter_exclude=None):
    games = []
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        response = session.get(url, timeout=15)
        
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        tables = soup.find_all('table', {'class': 'result-set'})
        
        for table in tables:
            rows = table.find_all('tr')
            current_date = "Unbekannt"

            for row in rows:
                cols = row.find_all('td')
                if not cols:
                    continue

                # --- ANKER SUCHEN (Uhrzeit) ---
                time_index = -1
                row_text_list = [c.get_text(strip=True) for c in cols]
                
                if len(cols) > 2 and re.match(r'^\d{2}:\d{2}$', row_text_list[2]):
                    time_index = 2
                    potential_date = row_text_list[1]
                    if "." in potential_date:
                        current_date = potential_date
                elif len(cols) > 0 and re.match(r'^\d{2}:\d{2}$', row_text_list[0]):
                    time_index = 0
                
                if time_index == -1:
                    continue

                try:
                    if len(cols) <= time_index + 5:
                        continue
                        
                    zeit = row_text_list[time_index]
                    heim = row_text_list[time_index + 3]
                    gast = row_text_list[time_index + 4]
                    tore = row_text_list[time_index + 5]
                    
                    # --- TEAM CHECK ---
                    def check_team_match(name):
                        name_lower = name.lower()
                        if filter_include:
                            if filter_include.lower() not in name_lower: return False
                        else:
                            if "birkesdorf" not in name_lower and "btv" not in name_lower: return False
                        
                        if filter_exclude:
                            if filter_exclude.lower() in name_lower: return False
                        return True

                    match_heim = check_team_match(heim)
                    match_gast = check_team_match(gast)
                    
                    if not match_heim and not match_gast:
                        continue

                    # --- PDF / BERICHT LINK SUCHEN ---
                    pdf_link = None
                    for link in row.find_all('a', href=True):
                        href = link['href']
                        href_lower = href.lower()
                        
                        is_report_link = False
                        
                        # 1. URL Keywords (JETZT ERWEITERT um 'nudokument')
                        if 'download' in href_lower or 'pdf' in href_lower or 'meeting' in href_lower or 'nudokument' in href_lower:
                            is_report_link = True
                        
                        # 2. Bild Check
                        img = link.find('img')
                        if img:
                            alt_text = img.get('alt', '').lower()
                            src_text = img.get('src', '').lower()
                            if 'pdf' in alt_text or 'bericht' in alt_text or 'pdf' in src_text:
                                is_report_link = True

                        if is_report_link:
                            pdf_link = urljoin(url, href)
                            break 

                    games.append({
                        'datum': current_date,
                        'zeit': zeit,
                        'heim': heim,
                        'gast': gast,
                        'tore': tore,
                        'pdf': pdf_link
                    })
                    
                except Exception as e:
                    continue
                
    except Exception as e:
        print(f"Scrape Fehler: {e}")
        return []
    
    return games

@app.route('/')
def index():
    latest_results = []
    
    for team_name, config in TEAMS.items():
        url = config[0]
        include = config[1]
        exclude = config[2]
        
        games = scrape_games(url, filter_include=include, filter_exclude=exclude)
        
        played_games = [g for g in games if ":" in g.get('tore', '')]
        
        last_game = None
        if played_games:
            last_game = played_games[-1]
        elif games:
            last_game = games[0]
            
        latest_results.append({
            'team': team_name,
            'game': last_game
        })

    return render_template('index.html', latest_results=latest_results)

@app.route('/team/<team_name>')
def team_detail(team_name):
    if team_name not in TEAMS:
        return "Team nicht gefunden", 404
    
    config = TEAMS[team_name]
    url = config[0]
    include = config[1]
    exclude = config[2]
    
    games = scrape_games(url, filter_include=include, filter_exclude=exclude)
    
    return render_template('team.html', team_name=team_name, games=games)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
