import random
import time

class DoorSensor:
    def read(self):
        return random.choice([0, 1])  # 0 closed, 1 open

class UltrasonicSensor:
    def read(self):
        return round(random.uniform(5.0, 150.0), 2)  # cm

class PIRSensor:
    def read(self):
        return random.choice([0, 1])  # motion / no motion

class MembraneSwitch:
    def read(self):
        return random.choice([0, 1])  # pressed / not pressed
