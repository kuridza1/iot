import json
import time

from sensors import DoorSensor, UltrasonicSensor, PIRSensor, MembraneSwitch
from actuators import DoorLight, DoorBuzzer

with open("config.json") as f:
    config = json.load(f)

sensors = {}

if config["DS1"]["enabled"]:
    sensors["DS1"] = DoorSensor()

if config["DUS1"]["enabled"]:
    sensors["DUS1"] = UltrasonicSensor()

if config["DPIR1"]["enabled"]:
    sensors["DPIR1"] = PIRSensor()

if config["DMS"]["enabled"]:
    sensors["DMS"] = MembraneSwitch()

door_light = DoorLight() if config["DL"]["enabled"] else None
door_buzzer = DoorBuzzer() if config["DB"]["enabled"] else None

def read_sensors():
    print("\n--- SENSOR READINGS ---")
    for name, sensor in sensors.items():
        value = sensor.read()
        print(f"{name}: {value}")

def actuator_menu():
    print("\n--- ACTUATOR CONTROL ---")
    print("1 - Door Light ON")
    print("2 - Door Light OFF")
    print("3 - Door Buzzer")
    print("0 - Back")

    choice = input("> ")

    if choice == "1" and door_light:
        door_light.on()
    elif choice == "2" and door_light:
        door_light.off()
    elif choice == "3" and door_buzzer:
        door_buzzer.buzz()

while True:
    print("\n==== PI1 SMART DOOR SYSTEM ====")
    print("1 - Read sensors")
    print("2 - Control actuators")
    print("0 - Exit")

    cmd = input("> ")

    if cmd == "1":
        read_sensors()
    elif cmd == "2":
        actuator_menu()
    elif cmd == "0":
        print("Exiting...")
        break
    else:
        print("Invalid option")

    time.sleep(0.5)
