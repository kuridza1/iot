# PI1 Smart Door — Run Instructions

## 1) Pokretanje na Raspberry Pi

ssh student@192.168.107.147
mkdir -p ~/tojest
exit

// idi u iot folder
scp -r ./pi1 student@192.168.107.147:/home/student/tojest/
scp -r ./helper student@192.168.107.147:/home/student/tojest/
scp -r ./actuators student@192.168.107.147:/home/student/tojest/
scp -r ./sensors student@192.168.107.147:/home/student/tojest/
scp -r ./security student@192.168.107.147:/home/student/tojest/
scp -r ./mqtt student@192.168.107.147:/home/student/tojest/

ssh student@192.168.107.147
cd ~/tojest

py -m pi1.main
py -m pi2.main
py -m pi3.main

// za izlazak
sudo shutdown -h now

KAMERA:
mjpg_streamer -i "input_uvc.so" -o "output_http.so -p 8080 -w /usr/local/share/mjpg-streamer/www"

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


