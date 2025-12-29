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
        response = session.get(url, timeout=15)
        
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Alle Tabellen finden (oft Spielplan + Tabelle)
        tables = soup.find_all('table', {'class': 'result-set'})
        
        for table in tables:
            rows = table.find_all('tr')
            
            # WICHTIG: Gedächtnis für das Datum, falls Zeilen zusammengefasst sind
            last_date = "Unbekannt"

            for row in rows:
                # Schnell-Check: Wenn "Birkesdorf" nicht in der ganzen Zeile vorkommt, weg damit.
                # Das spart uns das Parsen von Liga-Tabellen, da dort meist nur "Birkesdorf" einmal vorkommt
                # aber wir suchen ja Spielpaarungen.
                row_text = row.get_text().lower()
                if "birkesdorf" not in row_text:
                    continue

                cols = row.find_all('td')
                
                # Wir brauchen mindestens ca 5 Spalten, sonst ist es Datenmüll
                if len(cols) < 5:
                    continue

                # --- INTELLIGENTE SPALTEN ZUORDNUNG ---
                
                # Prüfen, ob Spalte 2 (Index 1) ein Datum ist (enthält Punkt, z.B. "24.09.")
                # Struktur A (Volle Zeile): Tag | Datum | Zeit | Halle ...
                # Struktur B (Kurze Zeile): Zeit | Halle | Nr ...
                
                col_offset = 0
                current_date = ""

                # Inhalt von Spalte 1 (Index 1) prüfen
                check_col = cols[1].get_text(strip=True)
                
                if "." in check_col:
                    # Es ist ein Datum! -> Struktur A
                    last_date = check_col
                    current_date = check_col
                    col_offset = 0 # Keine Verschiebung
                else:
                    # Kein Datum -> Struktur B (Zeit steht vorne)
                    current_date = last_date
                    col_offset = -2 # Alles rutscht 2 nach links, weil Tag & Datum fehlen
                
                # Jetzt prüfen wir die Halle (muss 5 Ziffern haben)
                # Halle ist bei Struktur A Index 3, bei Struktur B Index 1
                # Mit Offset-Rechnung: Index 3 + Offset
                try:
                    halle_idx = 3 + col_offset
                    halle_val = cols[halle_idx].get_text(strip=True)
                    # Kurzer Check: Ist es eine 5-stellige Zahl? (optional, aber sicher ist sicher)
                    if not (halle_val.isdigit() and len(halle_val) == 5):
                        # Falls das nicht passt, ist es vielleicht doch keine Spielzeile
                        # Aber wir sind tolerant, falls die Halle mal fehlt.
                        pass
                except:
                    # Wenn Zugriff fehlschlägt, ist die Zeile komisch -> skip
                    continue

                # Daten extrahieren mit Offset
                # Heim: A=5, B=3 -> 5 + offset
                # Gast: A=6, B=4 -> 6 + offset
                # Tore: A=7, B=5 -> 7 + offset
                
                try:
                    zeit = cols[2 + col_offset].get_text(strip=True)
                    heim = cols[5 + col_offset].get_text(strip=True)
                    gast = cols[6 + col_offset].get_text(strip=True)
                    tore = cols[7 + col_offset].get_text(strip=True) # Ergebnis
                    
                    # PDF Link suchen
                    pdf_link = None
                    link_tag = row.find('a', href=True)
                    if link_tag:
                        href = link_tag['href']
                        if 'pdf' in href.lower() or link_tag.find('img', alt=lambda x: x and 'PDF' in x):
                            pdf_link = urljoin(url, href)
                    
                    games.append({
                        'datum': current_date,
                        'zeit': zeit,
                        'heim': heim,
                        'gast': gast,
                        'tore': tore,
                        'pdf': pdf_link
                    })

                except IndexError:
                    # Falls Spalten fehlen
                    continue
                
    except Exception as e:
        print(f"Fehler: {e}")
        return []
    
    return games

@app.route('/')
def index():
    latest_results = []
    
    for team_name, url in TEAMS.items():
        games = scrape_games(url)
        
        # Suche letztes echtes Ergebnis (wo ein Doppelpunkt im Score ist)
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
    
    url = TEAMS[team_name]
    games = scrape_games(url)
    
    return render_template('team.html', team_name=team_name, games=games)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
