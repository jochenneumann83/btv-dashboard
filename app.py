from flask import Flask, render_template
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

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

# Browser-Tarnung
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
}

def scrape_games(url):
    games = []
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        response = session.get(url, timeout=20)
        
        # DEBUG: Prüfen, ob wir HTML bekommen
        if response.status_code != 200:
            return [{'error': f'Status Code Fehler: {response.status_code}'}]

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # DEBUG: Findet er überhaupt eine Tabelle?
        table = soup.find('table', {'class': 'result-set'})
        if not table:
            # Falls nuLiga die Klasse geändert hat, suchen wir irgendeine Tabelle
            if soup.find('table'):
                return [{'error': 'Tabelle gefunden, aber falsche CSS-Klasse (Struktur geändert?)'}]
            else:
                return [{'error': 'Keine Tabelle im HTML gefunden (Evtl. Bot-Schutz Seite?)'}]

        rows = table.find_all('tr')
        for row in rows:
            cols = row.find_all('td')
            if len(cols) > 6:
                datum = cols[1].get_text(strip=True)
                zeit = cols[2].get_text(strip=True)
                heim = cols[5].get_text(strip=True)
                gast = cols[6].get_text(strip=True)
                tore = cols[7].get_text(strip=True)

                # DEBUG: Filter ist DEAKTIVIERT!
                # Wir nehmen jetzt ALLES auf, um zu sehen, ob überhaupt was kommt.
                # if "Birkesdorf" not in heim and "Birkesdorf" not in gast:
                #     continue

                pdf_link = None
                link_tag = row.find('a', href=True)
                if link_tag:
                    href = link_tag['href']
                    if 'pdf' in href.lower() or link_tag.find('img', alt=lambda x: x and 'PDF' in x):
                         pdf_link = urljoin(url, href)
                
                games.append({
                    'datum': datum,
                    'zeit': zeit,
                    'heim': heim,
                    'gast': gast,
                    'tore': tore,
                    'pdf': pdf_link
                })
                
    except Exception as e:
        return [{'error': str(e)}]
    
    # Fallback, falls Schleife durchläuft aber nichts appended wurde
    if not games:
        return [{'error': 'Tabelle da, aber keine Zeilen erkannt.'}]

    return games

@app.route('/')
def index():
    latest_results = []
    
    for team_name, url in TEAMS.items():
        games = scrape_games(url)
        
        # Fehlerbehandlung anzeigen
        if games and 'error' in games[0]:
            latest_results.append({
                'team': team_name,
                'game': {'heim': 'DEBUG', 'gast': 'INFO', 'tore': '!!!', 'datum': games[0]['error']},
                'error': games[0]['error']
            })
            continue

        # Normales Spiel suchen
        played_games = [g for g in games if ":" in g.get('tore', '')]
        last_game = played_games[-1] if played_games else None
        
        # Falls wir kein gespieltes Spiel finden, nehmen wir das allerletzte (zukünftige Spiel) zur Ansicht
        if not last_game and games:
            last_game = games[-1]

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
    
    if games and 'error' in games[0]:
         return f"<h1>Debug Info</h1><p>{games[0]['error']}</p>"

    return render_template('team.html', team_name=team_name, games=games)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
