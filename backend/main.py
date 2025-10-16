"""
FastAPI Backend for ESP32 Sensor Data
Receives sensor data and serves it to frontend dashboard
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import uvicorn
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI(title="IoT Sensor API", version="1.0.1")

# Serve frontend static files (dashboard)
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend')
if os.path.isdir(frontend_path):
    app.mount('/static', StaticFiles(directory=frontend_path), name='static')

# -----------------------------
# CORS Middleware
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Data Models
# -----------------------------
class SensorData(BaseModel):
    device_id: str
    temperature: float
    humidity: float
    air_quality: float
    air_quality_raw: int

class SensorDataWithTimestamp(SensorData):
    timestamp: datetime


sensor_readings: List[SensorDataWithTimestamp] = []
MAX_READINGS = 100

# -----------------------------
# Routes
# -----------------------------
@app.get("/")
def root():
    return {"status": "online", "message": "IoT Sensor API is running", "total_readings": len(sensor_readings)}

@app.post("/sensor-data")
async def receive_sensor_data(request: Request):
    try:
        payload = await request.json()
        # Log raw incoming payload so the VS Code / terminal shows the sensor values
        print(f"📩 Incoming payload: {payload}")

        reading = SensorDataWithTimestamp(
            device_id=str(payload.get("device_id", "unknown")),
            temperature=float(payload.get("temperature", 0)),
            humidity=float(payload.get("humidity", 0)),
            air_quality=float(payload.get("air_quality", 0)),
            air_quality_raw=int(payload.get("air_quality_raw", 0)),
            timestamp=datetime.now(),
        )

        sensor_readings.append(reading)
        if len(sensor_readings) > MAX_READINGS:
            sensor_readings.pop(0)

        print(f"✅ Stored reading from {reading.device_id} @ {reading.timestamp}")
        # Return serializable dict (Pydantic model -> dict)
        return {"status": "success", "data": reading.dict()}

    except Exception as e:
        print("❌ Error:", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/latest-reading")
def get_latest():
    if not sensor_readings:
        return {"status": "no_data", "message": "No readings yet"}
    return {"status": "success", "data": sensor_readings[-1].dict()}

@app.get("/readings")
def get_all(limit: Optional[int] = 50):
    readings = sensor_readings[-limit:] if sensor_readings else []
    # Convert Pydantic models to dicts for JSON serialization
    readings_out = [r.dict() for r in readings]
    return {"status": "success", "count": len(readings_out), "readings": readings_out}


@app.get("/statistics")
def get_statistics():
    if not sensor_readings:
        return {"status": "no_data", "message": "No readings yet"}

    temps = [r.temperature for r in sensor_readings]
    hums = [r.humidity for r in sensor_readings]
    aqs = [r.air_quality for r in sensor_readings]

    def stats(arr):
        return {"min": round(min(arr), 2), "avg": round(sum(arr)/len(arr), 2), "max": round(max(arr), 2)}

    return {
        "status": "success",
        "temperature": stats(temps),
        "humidity": stats(hums),
        "air_quality": stats(aqs),
    }


@app.get("/dashboard")
def dashboard():
    html_path = os.path.join(frontend_path, 'dashboard.html')
    if os.path.isfile(html_path):
        return FileResponse(html_path, media_type='text/html')
    return {"status": "error", "message": "Dashboard not found"}

@app.delete("/readings")
def clear():
    global sensor_readings
    count = len(sensor_readings)
    sensor_readings = []
    return {"status": "success", "message": f"Cleared {count} readings"}

# -----------------------------
# Run Server
# -----------------------------
if __name__ == "__main__":
    print("🚀 Starting FastAPI server...")
    print("📡 Listening on http://0.0.0.0:8000")
    print("📊 Docs: http://localhost:8000/docs")
    # Use uvicorn programmatically so running `python main.py` starts the server.
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")