from flask import Flask, render_template
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re # Für Mustererkennung (Uhrzeit)

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
        
        # Wir suchen alle Tabellen.
        tables = soup.find_all('table', {'class': 'result-set'})
        
        for table in tables:
            rows = table.find_all('tr')
            
            # Gedächtnis für das Datum (Initial leer)
            current_date = "???"

            for row in rows:
                cols = row.find_all('td')
                
                # Zu wenige Spalten? Weg damit (Überschriften etc.)
                if len(cols) < 3:
                    continue

                # --- 1. DATUM & STRUKTUR ERKENNEN ---
                # nuLiga hat zwei Zeilentypen:
                # Typ A (Start eines Tages): [Tag, Datum, Zeit, Halle, ...]
                # Typ B (Weiteres Spiel):    [Zeit, Halle, ...]
                
                check_col_1 = cols[1].get_text(strip=True)
                
                is_type_a = "." in check_col_1 and len(check_col_1) >= 6 # z.B. "24.09."
                
                offset = 0
                if is_type_a:
                    current_date = check_col_1 # Datum aktualisieren
                    offset = 0 # Normale Indizes
                else:
                    # Typ B: Wir nutzen das `current_date` vom vorherigen Durchlauf
                    offset = -2 # Indizes verschieben sich um 2 nach links

                # --- 2. IST ES WIRKLICH EIN SPIEL? ---
                # Wir prüfen die Uhrzeit-Spalte. Bei Typ A ist es Index 2, bei Typ B Index 0.
                try:
                    time_idx = 2 + offset
                    zeit_text = cols[time_idx].get_text(strip=True)
                    
                    # WICHTIGSTER FILTER: Hat der Text einen Doppelpunkt? (z.B. "14:00")
                    # Tabellenzeilen (Platz 1, 2, 3) haben KEINE Uhrzeit.
                    if ":" not in zeit_text and "abges" not in zeit_text.lower():
                        continue # Keine Uhrzeit -> Keine Spielzeile -> Weiter zur nächsten Zeile
                except IndexError:
                    continue

                # --- 3. IST BIRKESDORF BETEILIGT? ---
                # Jetzt, wo wir wissen, dass es ein Spiel ist, lesen wir Heim/Gast
                try:
                    heim = cols[5 + offset].get_text(strip=True)
                    gast = cols[6 + offset].get_text(strip=True)
                    tore = cols[7 + offset].get_text(strip=True)
                except IndexError:
                    continue

                # Check: Spielt Birkesdorf?
                row_teams = (heim + gast).lower()
                if "birkesdorf" not in row_teams and "btv" not in row_teams:
                    continue # Spiel gefunden, aber ohne BTV -> ignorieren

                # --- 4. PDF SUCHEN ---
                pdf_link = None
                # Wir suchen in allen Spalten der Zeile nach einem Download-Link
                # Typischerweise ist es in der letzten Spalte, aber wir suchen sicherheitshalber in der ganzen Zeile
                link_tag = row.find('a', href=True)
                
                if link_tag:
                    href = link_tag['href']
                    # nuLiga Links enthalten oft "download" oder "pdf"
                    if 'download' in href.lower() or 'pdf' in href.lower():
                         pdf_link = urljoin(url, href)
                    # Manchmal ist es ein Icon Image
                    elif link_tag.find('img'):
                        img_src = link_tag.find('img').get('src', '')
                        if 'pdf' in img_src.lower():
                            pdf_link = urljoin(url, href)

                # Spiel speichern
                games.append({
                    'datum': current_date,
                    'zeit': zeit_text,
                    'heim': heim,
                    'gast': gast,
                    'tore': tore,
                    'pdf': pdf_link
                })
                
    except Exception as e:
        print(f"Fehler: {e}")
        return []
    
    return games

@app.route('/')
def index():
    latest_results = []
    
    for team_name, url in TEAMS.items():
        games = scrape_games(url)
        
        # Logik: Was ist das "aktuellste" Ergebnis?
        # 1. Wir filtern Spiele, die ein Ergebnis haben (Doppelpunkt im Score)
        played_games = [g for g in games if ":" in g.get('tore', '')]
        
        last_game = None
        if played_games:
            # Die Liste kommt von nuLiga chronologisch (alt -> neu).
            # Das letzte Element [-1] ist also das neuste gespielte Spiel.
            last_game = played_games[-1]
        elif games:
            # Saisonbeginn: Kein Spiel gespielt -> Zeige das erste kommende an
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
