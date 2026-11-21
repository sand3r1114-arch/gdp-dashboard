# 🏠 Thuis dashboard

Een dashboard van je huis: scan je wifi, zie welke apparaten er verbonden zijn,
geef ze een naam en deel ze in per kamer. Nieuwe of onbekende apparaten springen
er meteen uit.

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

Het dashboard opent in je browser. Klik links op **🔍 Scan nu**. Een scan duurt
meestal 10 tot 60 seconden.

Wil je eerst rondkijken? Zet dan **Voorbeeldgegevens tonen** aan.

## Wat je ziet

- **Per kamer**: alle apparaten gegroepeerd per kamer, online 🟢 of offline ⚪.
- **Alle apparaten**: een tabel waarin je een naam en kamer kiest en apparaten
  als *vertrouwd* markeert. Klik daarna op *Wijzigingen opslaan*.
- **Overzicht**: hoeveel apparaten van welk soort er online zijn, plus je
  netwerkgegevens.
- **Kamers beheren**: de lijst met kamers aanpassen.

Klik in de zijbalk op **Download fabrikantenlijst**. Dan zie je ook van welk merk
elk apparaat is (eenmalig, ongeveer 5 MB).

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

Namen, kamers en scanresultaten staan alleen lokaal in de map `thuis_data/`.
Die map staat in `.gitignore`, dus hij komt niet op GitHub terecht.

## Tests

```bash
pip install pytest
python -m pytest
```
