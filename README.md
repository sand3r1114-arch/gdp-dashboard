# 🏠 Thuis dashboard

Een dashboard van je huis, met alles op één scherm:

| Pagina | Wat | Koppeling |
|---|---|---|
| 🏠 **Overzicht** | Het belangrijkste van alles hieronder | |
| ⚡ **Energie** | Stroom nu, gas en stroom per uur/dag, kosten | HomeWizard P1-meter (lokaal) |
| 🌡️ **Verwarming** | Binnen- en buitentemperatuur, ketel, warm water | Viessmann ViCare-API |
| 💡 **Lampen** | Aan/uit en dimmen, per kamer | WiZ (lokaal, geen account) |
| 📷 **Camera's** | Stilstaand beeld dat elke 10 seconden ververst | RTSP (bijv. eufy) |
| 📡 **Netwerk** | Welke apparaten er op je wifi zitten | Eigen netwerkscan |
| 🌤️ **Weer** (op Overzicht) | Temperatuur en verwachting | Open-Meteo (gratis) |

## Starten

Draai dit op een computer die **met je thuiswifi verbonden is**. Een online
server, zoals Streamlit Cloud, kan je thuisnetwerk niet zien.

### Windows: dubbelklik op `start.bat`

1. Download de code als zip (op GitHub: **Code → Download ZIP**) en pak hem
   helemaal uit.
2. Dubbelklik op **`start.bat`**. Krijg je een blauw venster *"Windows heeft uw
   pc beschermd"*? Klik dan op **Meer informatie → Toch uitvoeren**.
3. De eerste keer installeert het script alles: zo nodig Python (via winget) en
   de benodigde pakketten. Dat duurt een paar minuten. Daarna opent het
   dashboard in je browser op http://localhost:8501.

Laat het zwarte venster open zolang je het dashboard gebruikt. Sluit het om te
stoppen.

### Mac / Linux, of handmatig

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Instellen

Ga in het dashboard naar **⚙️ Instellingen**. Daar staat per onderdeel wat je
moet doen. Kort samengevat:

- **Woonplaats:** vul je woonplaats in voor het weer.
- **HomeWizard P1-meter:** zet in de HomeWizard Energy-app de lokale API aan
  (*Instellingen → Meters → je P1-meter → Lokale API*). Klik daarna op
  **Zoek automatisch**. Het dashboard slaat elke minuut een meting op zolang het
  draait, dus de grafieken vullen zich vanzelf.
- **Energieprijzen:** optioneel, voor de kosten in euro's.
- **Viessmann:** maak eenmalig een gratis client-ID aan op
  https://app.developer.viessmann.com/. De stappen staan bij Instellingen. Het
  dashboard haalt elk kwartier gegevens op, ruim binnen de daglimiet van het
  gratis abonnement.
- **WiZ-lampen:** die worden vanzelf gevonden. Zet in de WiZ-app wel
  *Instellingen → Beveiliging → Lokale communicatie toestaan* aan.
- **eufy-camera's:** zet per camera in de eufy Security-app **NAS (RTSP)** aan
  (*camera → Instellingen → Opslag*). Plak daarna het `rtsp://`-adres op de
  pagina Camera's. Niet elke eufy-deurbel ondersteunt RTSP; batterijmodellen
  meestal niet.

## Netwerk

Klik op de pagina **📡 Netwerk** op **🔍 Scan nu**. Een scan duurt meestal 10
tot 60 seconden. Wil je eerst rondkijken? Zet dan **Voorbeeldgegevens tonen** aan.

- **Per kamer**: alle apparaten gegroepeerd per kamer, online 🟢 of offline ⚪.
- **Alle apparaten**: een tabel waarin je een naam en kamer kiest en apparaten
  als *vertrouwd* markeert. Klik daarna op *Wijzigingen opslaan*.
- **Overzicht**: hoeveel apparaten van welk soort er online zijn, plus je
  netwerkgegevens.
- **Kamers beheren**: de lijst met kamers aanpassen.

Van welk merk een apparaat is (Apple, Samsung, Philips…) zie je meteen. De
officiële IEEE-lijst met fabrikanten zit ingebouwd, via het pakket `netaddr`.
Met **Nieuwste lijst downloaden** in de zijbalk haal je optioneel de
allernieuwste versie op.

## Hoe de scan werkt

1. Het dashboard bepaalt je netwerk, bijvoorbeeld `192.168.1.0/24`.
2. Het probeert elk adres kort te bereiken (ping en een TCP-poging). Daardoor
   onthoudt je computer van elk apparaat het MAC-adres (de ARP-tabel).
3. Het leest die ARP-tabel uit en zoekt per apparaat de hostnaam, de fabrikant
   en een paar veelzeggende open poorten op. Zo wordt bijvoorbeeld een
   Chromecast, printer of iPhone herkend.

Je hebt geen admin-rechten en geen extra programma's nodig. Het werkt op
Windows, macOS en Linux. Vanaf de opdrachtregel kan het ook:
`python network_scanner.py`.

**Goed om te weten**

- Telefoons die slapen reageren soms niet. Scan dan nog eens, of maak het
  scherm even wakker.
- Moderne telefoons en laptops gebruiken een *privé-MAC-adres*. Het merk is dan
  onbekend, maar op jouw netwerk blijft het adres meestal hetzelfde. Herkenning
  blijft dus werken.
- Apparaten die alleen via Bluetooth, Zigbee of Z-Wave verbonden zijn (veel
  lampen en sensoren) zitten niet op je wifi. Die zie je hier niet. Hun bridge
  of hub zie je wel.
- Scan alleen je eigen netwerk, of een netwerk waarvoor je toestemming hebt.

## Privacy

Alles staat alleen lokaal in de map `thuis_data/`: namen, kamers,
scanresultaten, verbruiksgeschiedenis (`verbruik.sqlite`) en instellingen. Dat
geldt ook voor je Viessmann-wachtwoord en je camera-adressen, en die worden
**niet versleuteld** opgeslagen. Deel die map dus niet. Hij staat in
`.gitignore`, dus hij komt niet op GitHub terecht.

Gestart met `start.bat` luistert het dashboard alleen op deze computer
(`localhost`), dus andere apparaten in huis kunnen er niet bij. Start je het
handmatig met `streamlit run`, voeg dan `--server.address localhost` toe voor
hetzelfde effect.

## Tests

```bash
pip install pytest
python -m pytest
```
