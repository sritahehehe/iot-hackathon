"""
FastAPI Backend for ESP32 Sensor Data with Twilio Alerts
Receives sensor data, serves it to frontend, and sends alerts via Twilio
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import uvicorn
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="IoT Sensor API", version="2.0.0")

# Serve frontend static files
try:
    frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend')
    if os.path.isdir(frontend_path):
        app.mount('/static', StaticFiles(directory=frontend_path), name='static')
        print(f"✅ Frontend path configured: {frontend_path}")
    else:
        print(f"⚠ Frontend directory not found: {frontend_path}")
        frontend_path = None
except Exception as e:
    print(f"⚠ Could not mount frontend static files: {e}")
    frontend_path = None

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Twilio Configuration
# -----------------------------
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
ALERT_PHONE_NUMBER = os.getenv('ALERT_PHONE_NUMBER')

# Initialize Twilio client
twilio_client = None
try:
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
        from twilio.rest import Client
        from twilio.base.exceptions import TwilioRestException
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        print("✅ Twilio client initialized successfully")
except ImportError:
    print("⚠ Twilio package not installed. Run: pip install twilio")
except Exception as e:
    print(f"⚠ Failed to initialize Twilio: {e}")

if not twilio_client:
    print("⚠ Twilio credentials not found. Alerts will be disabled.")
    print("💡 Create a .env file with TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, ALERT_PHONE_NUMBER")

# Alert Thresholds
THRESHOLDS = {
    'temp_max': float(os.getenv('TEMP_MAX', 35.0)),
    'temp_min': float(os.getenv('TEMP_MIN', 15.0)),
    'humidity_max': float(os.getenv('HUMIDITY_MAX', 80.0)),
    'humidity_min': float(os.getenv('HUMIDITY_MIN', 20.0)),
    'air_quality_max': float(os.getenv('AIR_QUALITY_MAX', 70.0)),
}

ALERT_COOLDOWN = int(os.getenv('ALERT_COOLDOWN_MINUTES', 15))

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

class AlertSettings(BaseModel):
    enabled: bool
    alert_method: str  # "sms", "call", or "both"
    temp_max: float
    temp_min: float
    humidity_max: float
    humidity_min: float
    air_quality_max: float

class AlertHistory(BaseModel):
    timestamp: datetime
    alert_type: str
    sensor: str
    value: float
    threshold: float
    method: str
    status: str

# -----------------------------
# Global State
# -----------------------------
sensor_readings: List[SensorDataWithTimestamp] = []
alert_history: List[AlertHistory] = []
last_alert_time: Dict[str, datetime] = {}
MAX_READINGS = 100
MAX_ALERTS = 50

# Alert settings (can be modified via API)
alert_settings = {
    'enabled': True,
    'alert_method': 'both',  # 'sms', 'call', or 'both'
    **THRESHOLDS
}

# -----------------------------
# Twilio Functions
# -----------------------------
def send_sms_alert(message: str) -> bool:
    """Send SMS alert via Twilio"""
    if not twilio_client or not TWILIO_PHONE_NUMBER or not ALERT_PHONE_NUMBER:
        print("⚠ SMS not sent: Twilio not configured")
        return False
    
    try:
        from twilio.base.exceptions import TwilioRestException
        message_obj = twilio_client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=ALERT_PHONE_NUMBER
        )
        print(f"✅ SMS sent successfully: {message_obj.sid}")
        return True
    except Exception as e:
        print(f"❌ Failed to send SMS: {e}")
        return False

def make_voice_call(message: str) -> bool:
    """Make voice call via Twilio with TwiML"""
    if not twilio_client or not TWILIO_PHONE_NUMBER or not ALERT_PHONE_NUMBER:
        print("⚠ Call not made: Twilio not configured")
        return False
    
    try:
        from twilio.base.exceptions import TwilioRestException
        # Create TwiML for voice message
        twiml = f'<Response><Say voice="alice">{message}</Say><Pause length="1"/><Say voice="alice">This is an automated alert from your IoT sensor system. Please check your dashboard immediately.</Say></Response>'
        
        call = twilio_client.calls.create(
            twiml=twiml,
            to=ALERT_PHONE_NUMBER,
            from_=TWILIO_PHONE_NUMBER
        )
        print(f"✅ Call initiated successfully: {call.sid}")
        return True
    except Exception as e:
        print(f"❌ Failed to make call: {e}")
        return False

def check_and_send_alerts(reading: SensorDataWithTimestamp):
    """Check sensor readings against thresholds and send alerts"""
    if not alert_settings['enabled']:
        return
    
    alerts_to_send = []
    
    # Check temperature
    if reading.temperature > alert_settings['temp_max']:
        alerts_to_send.append({
            'sensor': 'temperature',
            'type': 'high',
            'value': reading.temperature,
            'threshold': alert_settings['temp_max'],
            'message': f"HIGH TEMPERATURE ALERT! Current: {reading.temperature}°C, Threshold: {alert_settings['temp_max']}°C"
        })
    elif reading.temperature < alert_settings['temp_min']:
        alerts_to_send.append({
            'sensor': 'temperature',
            'type': 'low',
            'value': reading.temperature,
            'threshold': alert_settings['temp_min'],
            'message': f"LOW TEMPERATURE ALERT! Current: {reading.temperature}°C, Threshold: {alert_settings['temp_min']}°C"
        })
    
    # Check humidity
    if reading.humidity > alert_settings['humidity_max']:
        alerts_to_send.append({
            'sensor': 'humidity',
            'type': 'high',
            'value': reading.humidity,
            'threshold': alert_settings['humidity_max'],
            'message': f"HIGH HUMIDITY ALERT! Current: {reading.humidity}%, Threshold: {alert_settings['humidity_max']}%"
        })
    elif reading.humidity < alert_settings['humidity_min']:
        alerts_to_send.append({
            'sensor': 'humidity',
            'type': 'low',
            'value': reading.humidity,
            'threshold': alert_settings['humidity_min'],
            'message': f"LOW HUMIDITY ALERT! Current: {reading.humidity}%, Threshold: {alert_settings['humidity_min']}%"
        })
    
    # Check air quality
    if reading.air_quality > alert_settings['air_quality_max']:
        alerts_to_send.append({
            'sensor': 'air_quality',
            'type': 'high',
            'value': reading.air_quality,
            'threshold': alert_settings['air_quality_max'],
            'message': f"POOR AIR QUALITY ALERT! Current: {reading.air_quality}%, Threshold: {alert_settings['air_quality_max']}%"
        })
    
    # Send alerts with cooldown
    for alert in alerts_to_send:
        alert_key = f"{alert['sensor']}_{alert['type']}"
        current_time = datetime.now()
        
        # Check cooldown
        if alert_key in last_alert_time:
            time_since_last = current_time - last_alert_time[alert_key]
            if time_since_last < timedelta(minutes=ALERT_COOLDOWN):
                print(f"⏱ Alert cooldown active for {alert_key}. Skipping.")
                continue
        
        # Send alert based on method
        method = alert_settings['alert_method']
        success = False
        
        if method in ['sms', 'both']:
            success = send_sms_alert(alert['message'])
        
        if method in ['call', 'both']:
            success = make_voice_call(alert['message']) or success
        
        # Record alert
        if success:
            last_alert_time[alert_key] = current_time
            alert_record = AlertHistory(
                timestamp=current_time,
                alert_type=alert['type'],
                sensor=alert['sensor'],
                value=alert['value'],
                threshold=alert['threshold'],
                method=method,
                status='sent'
            )
            alert_history.append(alert_record)
            if len(alert_history) > MAX_ALERTS:
                alert_history.pop(0)

# -----------------------------
# Routes
# -----------------------------
@app.get("/")
def root():
    twilio_status = "configured" if twilio_client else "not configured"
    return {
        "status": "online",
        "message": "IoT Sensor API with Twilio Alerts",
        "total_readings": len(sensor_readings),
        "twilio_status": twilio_status,
        "alerts_enabled": alert_settings['enabled']
    }

@app.post("/sensor-data")
async def receive_sensor_data(request: Request):
    try:
        payload = await request.json()
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
        
        # Check for alerts
        check_and_send_alerts(reading)

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

@app.get("/alert-settings")
def get_alert_settings():
    """Get current alert settings"""
    return {
        "status": "success",
        "settings": alert_settings,
        "twilio_configured": twilio_client is not None
    }

@app.put("/alert-settings")
async def update_alert_settings(settings: AlertSettings):
    """Update alert settings"""
    alert_settings['enabled'] = settings.enabled
    alert_settings['alert_method'] = settings.alert_method
    alert_settings['temp_max'] = settings.temp_max
    alert_settings['temp_min'] = settings.temp_min
    alert_settings['humidity_max'] = settings.humidity_max
    alert_settings['humidity_min'] = settings.humidity_min
    alert_settings['air_quality_max'] = settings.air_quality_max
    
    print(f"⚙ Alert settings updated: {alert_settings}")
    return {"status": "success", "settings": alert_settings}

@app.get("/alert-history")
def get_alert_history(limit: Optional[int] = 20):
    """Get alert history"""
    alerts = alert_history[-limit:] if alert_history else []
    return {
        "status": "success",
        "count": len(alerts),
        "alerts": [a.dict() for a in alerts]
    }

@app.post("/test-alert")
async def test_alert(method: str = "both"):
    """Test alert system"""
    if not twilio_client:
        return {"status": "error", "message": "Twilio not configured"}
    
    test_message = "This is a test alert from your IoT Sensor System. All systems are operational!"
    
    success = False
    if method in ['sms', 'both']:
        success = send_sms_alert(test_message)
    
    if method in ['call', 'both']:
        success = make_voice_call(test_message) or success
    
    return {
        "status": "success" if success else "error",
        "message": "Test alert sent" if success else "Failed to send test alert"
    }

@app.get("/dashboard")
def dashboard():
    if frontend_path and os.path.isdir(frontend_path):
        html_path = os.path.join(frontend_path, 'dashboard.html')
        if os.path.isfile(html_path):
            return FileResponse(html_path, media_type='text/html')
    return {"status": "error", "message": "Dashboard not found. Make sure frontend/dashboard.html exists"}

@app.delete("/readings")
def clear():
    global sensor_readings
    count = len(sensor_readings)
    sensor_readings = []
    return {"status": "success", "message": f"Cleared {count} readings"}

@app.delete("/alert-history")
def clear_alerts():
    global alert_history, last_alert_time
    count = len(alert_history)
    alert_history = []
    last_alert_time = {}
    return {"status": "success", "message": f"Cleared {count} alerts"}

# -----------------------------
# Run Server
# -----------------------------
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 Starting FastAPI server with Twilio Integration...")
    print("="*60)
    print("📡 Listening on http://0.0.0.0:8000")
    print("📊 API Docs: http://localhost:8000/docs")
    print("🖥  Dashboard: http://localhost:8000/dashboard")
    print(f"📱 Twilio Status: {'✅ Configured' if twilio_client else '❌ Not Configured'}")
    print(f"🔔 Alerts: {'✅ Enabled' if alert_settings['enabled'] else '❌ Disabled'}")
    print("="*60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")