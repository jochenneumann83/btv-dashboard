from flask import Flask, render_template
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

app = Flask(__name__)

# Konfiguration der Teams und URLs (Stand: Schritt 1)
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

def scrape_games(url):
    """Holt Spiele von nuLiga und filtert strikt nach 'Birkesdorf'."""
    games = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Tabelle suchen
        table = soup.find('table', {'class': 'result-set'})
        if not table:
            return []

        rows = table.find_all('tr')
        for row in rows:
            cols = row.find_all('td')
            # Eine Spielzeile hat in nuLiga meist viele Spalten
            if len(cols) > 6:
                datum = cols[1].get_text(strip=True)
                zeit = cols[2].get_text(strip=True)
                
                # Spaltenindizes können variieren, meistens: 5=Heim, 6=Gast
                heim = cols[5].get_text(strip=True)
                gast = cols[6].get_text(strip=True)
                
                # FILTER: Nur Zeilen, in denen "Birkesdorf" vorkommt
                if "Birkesdorf" not in heim and "Birkesdorf" not in gast:
                    continue

                # Ergebnis (oft Spalte 7 oder 8)
                tore = cols[7].get_text(strip=True) 

                # PDF Link suchen
                pdf_link = None
                link_tag = row.find('a', href=True)
                if link_tag:
                    href = link_tag['href']
                    # Prüfen auf PDF Icon (img mit alt text) oder Link-Text
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
        print(f"Fehler beim Scrapen von {url}: {e}")
    
    return games

@app.route('/')
def index():
    # Startseite: Holt für jedes Team das letzte bekannte Ergebnis
    latest_results = []
    
    for team_name, url in TEAMS.items():
        games = scrape_games(url)
        # Wir suchen das letzte Spiel, das tatsächlich ein Ergebnis hat (Doppelpunkt im String)
        played_games = [g for g in games if ":" in g['tore']]
        
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
    
    # Optional: Liste umdrehen, damit das neuste Spiel oben ist? 
    # Aktuell ist es chronologisch (nuLiga Standard).
    
    return render_template('team.html', team_name=team_name, games=games)

if __name__ == '__main__':
    app.run(debug=True, port=5000)