"""
Simple simulator that POSTs random sensor readings to the backend every 5 seconds.
Run alongside the FastAPI server to emulate the ESP32.
"""
import time
import random
import requests

URL = 'http://127.0.0.1:8000/sensor-data'

print('Simulator ready. Posting to', URL)
try:
    while True:
        payload = {
            'device_id': 'SIM_ESP32',
            'temperature': round(20 + random.random() * 10, 2),
            'humidity': round(30 + random.random() * 50, 2),
            'air_quality': round(random.random() * 50, 2),
            'air_quality_raw': random.randint(200, 3000)
        }
        try:
            r = requests.post(URL, json=payload, timeout=5)
            print('POST', r.status_code, payload)
        except Exception as e:
            print('POST error:', e)
        time.sleep(5)
except KeyboardInterrupt:
    print('Simulator stopped')
