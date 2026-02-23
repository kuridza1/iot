# PI1 Smart Door — Run Instructions

## 1) Pokretanje na Raspberry Pi

ssh student@192.168.107.14X
mkdir -p ~/tojest
exit

// idi u iot folder
scp -r ./pi1-2-3 korisnik@hostname:/home/korisnik/tojest/
scp -r ./helper korisnik@hostname:/home/korisnik/tojest/
scp -r ./actuators korisnik@hostname:/home/korisnik/tojest/
scp -r ./sensors korisnik@hostname:/home/korisnik/tojest/
scp -r ./security korisnik@hostname:/home/korisnik/tojest/
scp -r ./mqtt korisnik@hostname:/home/korisnik/tojest/

ssh student@192.163.107.14X
cd ~/tojest

py -m pi1.main
py -m pi2.main
py -m pi3.main

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

## 6) Pokretanje server aplikacije

cd server  
python app.py  

---


