# PI1 Smart Door — Run Instructions

## 1) Pokretanje na Raspberry Pi

ssh korisnik@hostname (hostname ce nam dati)

mkdir -p ~/tojest

exit

scp -r ./iot(ili pi1)/* korisnik@hostname:/home/korisnik/tojest/

ssh korisnik@hostname

cd ~/tojest

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python3 device/main.py

// za izlazak
sudo shutdown -h now


---

## 2) Kreiranje InfluxDB tokena (jednom)

1. Pokreni InfluxDB: 
   cd /infra
   docker compose up -d influxdb
2. Otvori Influx UI:
   http://localhost:8086
3. Kreiraj:
   - Organization: org
   - Bucket: iot
4. Generate API Token:
   - Load Data → API Tokens → Generate API Token
   - Permission: read/write za bucket iot
   - Sačuvaj token

---

## 3) Podešavanje .env fajlova

### server/.env

INFLUX_URL=http://influxdb:8086  
INFLUX_ORG=org  
INFLUX_BUCKET=iot  
INFLUX_TOKEN=PASTE_TOKEN_HERE  

GRAFANA_ADMIN_USER=admin  
GRAFANA_ADMIN_PASSWORD=admin  
GRAFANA_PORT=3000  

MQTT_BROKER=mosquitto  
MQTT_PORT=1883  
MQTT_TOPIC_FILTER=iot/smart-house/#  

INFLUX_URL=http://localhost:8086  
INFLUX_ORG=org  
INFLUX_BUCKET=iot  
INFLUX_TOKEN=PASTE_TOKEN_HERE  

MQTT_BROKER=localhost  
MQTT_PORT=1883  
MQTT_TOPIC_FILTER=iot/smart-house/#  
---


## 4) Pokretanje infrastrukture (InfluxDB + Grafana + MQTT)

cd infra  
docker compose up -d  
docker ps  

---

## 5) Grafana (automatski)

1. Otvori http://localhost:3000
2. Login:
   - admin / admin (ili vrednosti iz .env)
3. Otvori dashboard: PI1 Smart Door

Ako dashboard nije učitan:
docker compose restart grafana

---

## 6) Pokretanje server aplikacije

cd server  
python app.py  

---

## 7) Pokretanje device aplikacije (Raspberry Pi)

1. SSH:
   ssh pi@<PI_IP>
2. Install:
   cd device  
3. Proveri settings.json:
   - mqtt.host = IP adresa servera
   - mqtt.port = 1883
4. Start:
   python main.py

---

## 8) Tipičan redosled pokretanja

1. infra: docker compose up -d
2. server: python app.py
3. device: python main.py
4. Grafana: dashboard live

---

## 9) Brzi troubleshooting

- Grafana prazan dashboard:
  - proveri Last 15m i auto refresh 5s
- Nema podataka u Influx:
  - proveri server log i token
- MQTT ne radi:
  - device ne sme koristiti localhost
