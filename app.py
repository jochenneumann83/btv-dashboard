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

# TÄUSCHUNGSMANÖVER: Wir geben uns als normaler Browser aus
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Cache-Control': 'max-age=0',
}

def scrape_games(url):
    games = []
    try:
        # Session nutzen, um Cookies zu speichern (wirkt menschlicher)
        session = requests.Session()
        session.headers.update(HEADERS)
        
        response = session.get(url, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table', {'class': 'result-set'})
        
        if not table:
            return []

        rows = table.find_all('tr')
        for row in rows:
            cols = row.find_all('td')
            if len(cols) > 6:
                datum = cols[1].get_text(strip=True)
                zeit = cols[2].get_text(strip=True)
                heim = cols[5].get_text(strip=True)
                gast = cols[6].get_text(strip=True)
                tore = cols[7].get_text(strip=True)

                # Filter: Nur Birkesdorf Spiele
                if "Birkesdorf" not in heim and "Birkesdorf" not in gast:
                    continue

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
        # Fehler wird in den Logs von Render angezeigt
        print(f"FEHLER beim Scrapen von {url}: {e}")
        # Wir geben einen Dummy-Eintrag zurück, damit man den Fehler auf der Seite sieht
        return [{'error': str(e)}]
    
    return games

@app.route('/')
def index():
    latest_results = []
    
    for team_name, url in TEAMS.items():
        games = scrape_games(url)
        
        # Falls ein Fehler auftrat (Bot-Sperre etc.)
        if games and 'error' in games[0]:
            error_msg = games[0]['error']
            # Wir zeigen den Fehler auf der Karte an
            latest_results.append({
                'team': team_name,
                'game': {'heim': 'Fehler', 'gast': 'nuLiga', 'tore': 'ERR', 'datum': 'Verbindung geblockt'},
                'error': error_msg
            })
            continue

        # Normaler Ablauf: Suche letztes echtes Spiel
        played_games = [g for g in games if ":" in g.get('tore', '')]
        last_game = played_games[-1] if played_games else None
        
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
    
    # Fehlerprüfung für die Detailseite
    if games and 'error' in games[0]:
        return f"<h1>Fehler beim Laden</h1><p>{games[0]['error']}</p><p>NuLiga blockiert wahrscheinlich die Anfrage von Render.</p>"
    
    return render_template('team.html', team_name=team_name, games=games)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
