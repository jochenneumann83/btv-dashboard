from flask import Flask, render_template
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

app = Flask(__name__)

# Konfiguration der Teams und URLs
TEAMS = {
    "mC-Jugend": "https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=424095",
    "wC1-Jugend": "https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=424246",
    "wC2-Jugend": "https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=424246",
    "mD-Jugend": "https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=424301",
    "wD1-Jugend": "https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=425685",
    "wD2-Jugend": "https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=425685",
    "mE1-Jugend": "https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=424179",
    "mE2-Jugend": "https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/teamPortrait?teamtable=2118365&pageState=vorrunde&championship=AD+25%2F26&group=423969",
    "wE-Jugend": "https://hnr-handball.liga.nu/cgi-bin/WebObjects/nuLigaHBDE.woa/wa/groupPage?championship=AD+25%2F26&group=424213"
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

def scrape_games(url):
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

                # --- STRATEGIE: ANKER SUCHEN ---
                # Wir suchen die Spalte mit der Uhrzeit (Format HH:MM).
                # Von dort aus navigieren wir relativ zu den anderen Spalten.
                
                time_index = -1
                row_text_list = [c.get_text(strip=True) for c in cols]
                
                # Versuch 1: Ist Spalte 2 eine Uhrzeit? (Volle Zeile: Tag, Datum, Zeit...)
                if len(cols) > 2 and re.match(r'^\d{2}:\d{2}$', row_text_list[2]):
                    time_index = 2
                    # Wenn Zeit an Pos 2 ist, MUSS Datum an Pos 1 sein
                    potential_date = row_text_list[1]
                    if "." in potential_date:
                        current_date = potential_date
                
                # Versuch 2: Ist Spalte 0 eine Uhrzeit? (Kurze Zeile: Zeit, Halle...)
                elif len(cols) > 0 and re.match(r'^\d{2}:\d{2}$', row_text_list[0]):
                    time_index = 0
                    # Datum bleibt das alte (current_date)
                
                # Kein Anker gefunden? Dann ist es keine Spielzeile (z.B. Tabelle oder Header)
                if time_index == -1:
                    continue

                # --- DATEN RELATIV ZUM ANKER LESEN ---
                # Struktur nuLiga ist immer: [ZEIT] [HALLE] [NR] [HEIM] [GAST] [TORE]
                # Das heißt:
                # Heim = Zeit + 3
                # Gast = Zeit + 4
                # Tore = Zeit + 5
                
                try:
                    # Wir brauchen genug Spalten nach der Zeit
                    if len(cols) <= time_index + 5:
                        continue
                        
                    zeit = row_text_list[time_index]
                    heim = row_text_list[time_index + 3]
                    gast = row_text_list[time_index + 4]
                    tore = row_text_list[time_index + 5]
                    
                    # FILTER: Nur Birkesdorf
                    if "birkesdorf" not in heim.lower() and "btv" not in heim.lower() and \
                       "birkesdorf" not in gast.lower() and "btv" not in gast.lower():
                        continue

                    # PDF LINK SUCHEN (In der ganzen Zeile)
                    pdf_link = None
                    for link in row.find_all('a', href=True):
                        href = link['href']
                        # Suchen nach "download" (nuLiga Standard) oder "pdf"
                        if 'download' in href.lower() or 'pdf' in href.lower():
                            pdf_link = urljoin(url, href)
                            break # Den ersten Treffer nehmen

                    games.append({
                        'datum': current_date,
                        'zeit': zeit,
                        'heim': heim,
                        'gast': gast,
                        'tore': tore,
                        'pdf': pdf_link
                    })
                    
                except Exception as e:
                    # Falls beim Zugriff was schief geht, Zeile überspringen
                    continue
                
    except Exception as e:
        print(f"Scrape Fehler: {e}")
        return []
    
    return games

@app.route('/')
def index():
    latest_results = []
    
    for team_name, url in TEAMS.items():
        games = scrape_games(url)
        
        # Logik für "Aktuellstes Spiel":
        # nuLiga sortiert chronologisch. Das letzte Spiel in der Liste mit einem Ergebnis ist das aktuellste.
        
        played_games = [g for g in games if ":" in g.get('tore', '')]
        
        last_game = None
        if played_games:
            last_game = played_games[-1]
        elif games:
            # Wenn noch gar nicht gespielt wurde, zeige das allererste Spiel der Saison (Termin)
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
    
    url = TEAMS[team_name]
    games = scrape_games(url)
    
    return render_template('team.html', team_name=team_name, games=games)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
