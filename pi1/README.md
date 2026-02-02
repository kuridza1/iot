# PI1 Smart Door (InfluxDB + Grafana + MQTT)

Sistem ima dve celine:
- `device/` (Raspberry Pi): čita ulaze i šalje telemetriju preko MQTT-a.
- `server/` (PC/laptop): sluša MQTT i upisuje telemetriju u InfluxDB.
Vizualizacija ide kroz Grafana dashboard.

## 1) Prerequisites

Na računaru:
- Docker + Docker Compose
- Python 3.10+ (preporuka) i pip

Na Raspberry Pi:
- Raspberry Pi OS
- Python 3 + pip
- mrežna konekcija do računara (ista mreža ili VPN)

## 2) Povezivanje na Raspberry Pi (SSH)

1. Nađi IP adresu Raspberry Pi (npr. sa rutera ili preko `hostname -I` na Pi).
2. Poveži se:
   - Windows PowerShell:
     ssh pi@<PI_IP>
3. (Opcionalno) kopiranje koda na Pi:
   - ako koristiš git:
     git clone <repo>
   - ili SCP:
     scp -r ./device pi@<PI_IP>:/home/pi/

## 3) Pokretanje infrastrukture (InfluxDB + Grafana + MQTT)

U folderu `infra/`:
1. Start:
   docker compose up -d
2. Provera:
   docker ps

Servisi tipično:
- InfluxDB: http://localhost:8086
- Grafana:  http://localhost:3000
- MQTT broker: localhost:1883

## 4) InfluxDB: kreiranje tokena

1. Otvori Influx UI: http://localhost:8086
2. Kreiraj / proveri:
   - Organization: `org`
   - Bucket: `iot`
3. Kreiraj token:
   - Load Data -> API Tokens -> Generate API Token
   - All-Access ili barem permission za bucket `iot` (read/write)
4. Sačuvaj token (biće korišćen u server env var).

## 5) Server: podešavanje env var i pokretanje ingestion-a

U `server/` napravi `.env` na osnovu `.env.example`.

Primer `.env`:
INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=PASTE_YOUR_TOKEN_HERE
INFLUX_ORG=org
INFLUX_BUCKET=iot

MQTT_BROKER=localhost
MQTT_PORT=1883
MQTT_TOPIC_FILTER=iot/smart-house/#

Windows PowerShell varijanta (ako ne koristiš `.env`):
$env:INFLUX_URL="http://localhost:8086"
$env:INFLUX_TOKEN="PASTE_YOUR_TOKEN_HERE"
$env:INFLUX_ORG="org"
$env:INFLUX_BUCKET="iot"
$env:MQTT_BROKER="localhost"
$env:MQTT_PORT="1883"
$env:MQTT_TOPIC_FILTER="iot/smart-house/#"

Pokretanje server aplikacije:
1. Instalacija dependencija:
   cd server
   pip install -r requirements.txt
2. Start:
   python app.py

Napomena: ako si promenila Influx token, ingestion mora da koristi NOVI token (update `.env` / env var).

## 6) Grafana: konekcija na InfluxDB

1. Otvori Grafana: http://localhost:3000
2. Add data source -> InfluxDB (InfluxQL/Flux u zavisnosti od implementacije; najčešće Flux za InfluxDB 2.x)
3. Podesi:
   - URL: http://influxdb:8086 (ako Grafana radi u Docker mreži) ili http://localhost:8086 (ako van Dockera)
   - Organization: org
   - Token: isti token (mora imati read permission)
   - Default bucket: iot
4. Save & Test

## 7) Flux query-ji za panele (Grafana)

Query-je drži u `grafana/*.flux`:

- `grafana/dus1.flux` – DUS1 (distance)
- `grafana/dpir1.flux` – PIR
- `grafana/ds1.flux` – Door button
- `grafana/dl.flux` – Door light

Ako želiš ručno (primeri):

DUS1:
from(bucket: "iot")
  |> range(start: -15m)
  |> filter(fn: (r) => r._measurement == "telemetry")
  |> filter(fn: (r) => r.code == "DUS1")
  |> filter(fn: (r) => r._field == "value_num")

PIR:
from(bucket: "iot")
  |> range(start: -15m)
  |> filter(fn: (r) => r._measurement == "telemetry")
  |> filter(fn: (r) => r.code == "DPIR1")
  |> filter(fn: (r) => r._field == "value_bool")

Door button:
from(bucket: "iot")
  |> range(start: -15m)
  |> filter(fn: (r) => r._measurement == "telemetry")
  |> filter(fn: (r) => r.code == "DS1")
  |> filter(fn: (r) => r._field == "value_bool")

Door light:
from(bucket: "iot")
  |> range(start: -15m)
  |> filter(fn: (r) => r._measurement == "telemetry")
  |> filter(fn: (r) => r.code == "DL")
  |> filter(fn: (r) => r._field == "value_bool")

## 8) Device: pokretanje na Raspberry Pi

U `device/`:
1. Instalacija:
   pip install -r requirements.txt
2. Konfiguracija:
   - proveri `settings.json` (pinovi, simulated=true/false, mqtt parametri)
3. Start:
   python main.py

Ako device šalje MQTT ka računaru, proveri da `MQTT_BROKER` u settings-u pokazuje na IP računara (ne localhost).

## 9) Tipičan “full run” redosled

1. `infra/`: docker compose up -d
2. Influx: kreiraj token (ako treba) i update `.env`
3. `server/`: pokreni `python app.py`
4. `device/`: pokreni `python main.py`
5. Grafana: otvori dashboard/panele

## Troubleshooting (kratko)

- Influx connection refused: proveri da je Influx container up i port 8086 otvoren.
- Grafana ne vidi Influx: koristi `http://influxdb:8086` ako su oba u docker-compose mreži.
- Nema podataka u panelu: proveri MQTT ingestion (server log), i da li se upisuje u bucket `iot`.
