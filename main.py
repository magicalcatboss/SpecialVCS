from fastapi import FastAPI, UploadFile, File, HTTPException, Body, Header, Depends, WebSocket, WebSocketDisconnect, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict
import uvicorn
import os
import json
import uuid
import base64
import time
from dotenv import load_dotenv

# Import Services
from services.vision import analyze_face_image
from services.audio import text_to_speech_stream
from services.llm import GeminiClient
from services.video_processor import process_frame
from services.spatial_memory import SpatialMemory
from services.frame_annotator import annotate_frame
from services.socket_manager import ConnectionManager

load_dotenv()

# Initialize App
app = FastAPI(
    title="SpatialVCS API",
    description="Spatial Version Control System — Search reality like the web, manage space like code. "
                "Built on Gemini Toolkit with Vision, Audio, and Spatial AI.",
    version="2.1.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Managers
spatial_memory = SpatialMemory()
socket_manager = ConnectionManager()
spatial_scans: Dict[str, dict] = {}


def _ensure_scan(scan_id: str, source: Optional[str] = None) -> dict:
    if scan_id not in spatial_scans:
        spatial_scans[scan_id] = {
            "scan_id": scan_id,
            "status": "scanning",
            "source": source,
            "frames": 0,
            "object_count": 0,
            "objects": [],
            "last_frame_path": None,
            "updated_at": None,
        }
    return spatial_scans[scan_id]

# --- Helpers ---
def _get_gemini():
    """Get a GeminiClient from env (for WebSocket context where headers aren't available)."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    return GeminiClient(api_key)

def get_gemini_client(x_api_key: Optional[str] = Header(None)):
    api_key = x_api_key or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header or GEMINI_API_KEY env var")
    return GeminiClient(api_key)

# ============================================================
# WebSocket Connectors
# ============================================================

@app.websocket("/ws/probe/{client_id}")
async def websocket_probe(websocket: WebSocket, client_id: str, api_key: Optional[str] = None):
    """
    WebSocket Endpoint for Mobile Probe (Data Sender).
    Receives real-time stream of frames + pose data.
    Full pipeline: Base64 decode → YOLO → Gemini describe → FAISS index → Broadcast.
    """
    await socket_manager.connect_probe(websocket, client_id)
    
    # Use provided API key or fallback to env
    final_key = api_key or os.getenv("GEMINI_API_KEY")
    gemini = GeminiClient(final_key) if final_key else None
    
    frame_count = 0

    try:
        while True:
            data = await websocket.receive_json()
            # Expected: {"type":"frame", "image":"base64...", "pose":{"alpha":0,"beta":0,"gamma":0}, "scan_id":"room_01"}

            if data.get("type") == "stop_scan":
                scan_id = data.get("scan_id", f"scan_{client_id}")
                if scan_id in spatial_scans:
                    spatial_scans[scan_id]["status"] = "completed"
                # Notify dashboards
                await socket_manager.broadcast_to_dashboards({
                    "type": "scan_completed",
                    "scan_id": scan_id,
                    "log": f"Scan {scan_id} completed."
                })
                continue

            if data.get("type") == "frame":
                scan_id = data.get("scan_id", f"scan_{client_id}")
                timestamp = data.get("timestamp", time.time())
                frame_count += 1

                # --- Step 1: Decode Base64 Image ---
                image_b64 = data.get("image", "")
                # Strip data URL prefix if present (e.g. "data:image/jpeg;base64,")
                if "," in image_b64:
                    image_b64 = image_b64.split(",", 1)[1]
                try:
                    image_bytes = base64.b64decode(image_b64)
                except Exception:
                    await socket_manager.send_to_probe(client_id, {
                        "type": "error", "message": "Invalid base64 image"
                    })
                    continue

                # --- Step 2: Build Pose string from gyroscope ---
                # Web sends {alpha, beta, gamma}; we construct a simplified pose
                pose_data = data.get("pose", {})
                alpha = pose_data.get("alpha", 0)
                beta = pose_data.get("beta", 0)
                gamma = pose_data.get("gamma", 0)
                # For Web (no LiDAR), we use identity matrix with estimated depth
                # The pose string is expected as 16 comma-separated floats (4x4 matrix)
                pose_str = "1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1"
                estimated_depth = 1.5  # Default assumed distance

                # --- Step 3: YOLO Detection + 3D Coordinate Estimation ---
                detections = process_frame(image_bytes, estimated_depth, pose_str, scan_id)

                # --- Step 4: Gemini Semantic Description (every 3rd frame to save API quota) ---
                gemini_objects = []
                if gemini and detections and (frame_count % 3 == 1):
                    try:
                        description_data = gemini.describe_for_spatial(image_bytes)
                        gemini_objects = description_data.get("objects", [])
                    except Exception as e:
                        print(f"Gemini error: {e}")

                # --- Step 5: Store in Spatial Memory ---
                scan_record = _ensure_scan(scan_id, source=client_id)
                scan_record["frames"] += 1
                scan_record["updated_at"] = timestamp
                if detections:
                    scan_record["last_frame_path"] = detections[0].get("frame_path")

                for obj in gemini_objects:
                    frame_path = detections[0]["frame_path"] if detections else ""
                    meta = {
                        "scan_id": scan_id,
                        "frame_path": frame_path,
                        "timestamp": timestamp,
                        "yolo_detections": detections,
                        "details": obj,
                        "source": client_id
                    }
                    text_to_index = f"{obj.get('name','')} {obj.get('position','')} {obj.get('details','')}"
                    spatial_memory.add_observation(text_to_index, meta)
                    scan_record["objects"].append({
                        "name": obj.get("name", ""),
                        "position": obj.get("position", ""),
                        "details": obj.get("details", ""),
                        "timestamp": timestamp,
                        "frame_path": frame_path,
                    })

                scan_record["object_count"] += len(gemini_objects)

                # --- Step 6: Broadcast Results to All Dashboards ---
                broadcast_objects = []
                for d in detections:
                    broadcast_objects.append({
                        "label": d["label"],
                        "confidence": d["confidence"],
                        "bbox": d.get("bbox"),
                        "position": d.get("position_3d", {"x": 0, "y": 0, "z": estimated_depth})
                    })

                await socket_manager.broadcast_to_dashboards({
                    "type": "detection",
                    "source": client_id,
                    "scan_id": scan_id,
                    "frame_number": frame_count,
                    "objects": broadcast_objects,
                    "gemini_objects": gemini_objects,
                    "pose": {"alpha": alpha, "beta": beta, "gamma": gamma},
                    "timestamp": timestamp,
                    "log": f"[{scan_id}] Frame #{frame_count}: {len(detections)} objects detected"
                })

                # Acknowledge to Probe
                await socket_manager.send_to_probe(client_id, {
                    "type": "ack",
                    "frame": frame_count,
                    "objects_found": len(detections)
                })

    except WebSocketDisconnect:
        socket_manager.disconnect_probe(client_id)
        # Notify dashboards that probe left
        await socket_manager.broadcast_to_dashboards({
            "type": "probe_disconnected", "source": client_id
        })
    except Exception as e:
        print(f"Error in probe ws: {e}")
        socket_manager.disconnect_probe(client_id)

@app.websocket("/ws/dashboard/{client_id}")
async def websocket_dashboard(websocket: WebSocket, client_id: str):
    """
    WebSocket Endpoint for Wall Dashboard (Data Receiver).
    Receives real-time updates of detected objects.
    """
    await socket_manager.connect_dashboard(websocket, client_id)
    try:
        while True:
            # Dashboard might send commands like "Start Recording" etc.
            data = await websocket.receive_text()
            # Echo or process commands
    except WebSocketDisconnect:
        socket_manager.disconnect_dashboard(client_id)

# ============================================================
# Routes
# ============================================================

# Serve demo frontend at /demo
if os.path.exists("demo"):
    app.mount("/demo", StaticFiles(directory="demo", html=True), name="demo")

@app.get("/")
def health_check():
    from services.video_processor import _get_yolo
    return {
        "status": "online", 
        "name": "SpatialVCS", 
        "version": "2.1.0", 
        "capabilities": {
            "search": spatial_memory.is_ready(),
            "yolo": _get_yolo() is not None,
            "gemini": os.getenv("GEMINI_API_KEY") is not None
        }
    }


@app.get("/project_specification.md")
def get_project_specification():
    path = "project_specification.md"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="project_specification.md not found")
    return FileResponse(path, media_type="text/markdown")


@app.get("/backend_capabilities.md")
def get_backend_capabilities():
    path = "backend_capabilities.md"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="backend_capabilities.md not found")
    return FileResponse(path, media_type="text/markdown")

# ------- 1. Vision Module -------

@app.post("/vision/face-analysis")
async def analyze_face(file: UploadFile = File(...)):
    """
    Local face detection.
    """
    contents = await file.read()
    return analyze_face_image(contents)

@app.post("/vision/describe")
async def describe_scene(
    file: UploadFile = File(...),
    x_api_key: Optional[str] = Header(None)
):
    """
    Gemini Vision: Describes the scene.
    """
    client = get_gemini_client(x_api_key)
    contents = await file.read()
    return client.describe_image(contents)

# ------- 2. Audio Module -------

class SpeakRequest(BaseModel):
    text: str
    lang: str = "en"

@app.post("/audio/speak")
async def speak(request: SpeakRequest):
    """
    Text-to-Speech.
    """
    audio_stream = text_to_speech_stream(request.text, request.lang)
    if not audio_stream:
        raise HTTPException(status_code=500, detail="TTS Generation failed")
    return StreamingResponse(audio_stream, media_type="audio/mpeg")

@app.post("/audio/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    x_api_key: Optional[str] = Header(None)
):
    """
    Speech-to-Text via Gemini.
    """
    client = get_gemini_client(x_api_key)
    contents = await file.read()
    
    mime_map = {"wav": "audio/wav", "mp3": "audio/mpeg", "webm": "audio/webm", "ogg": "audio/ogg", "m4a": "audio/mp4"}
    ext = (file.filename or "audio.wav").rsplit(".", 1)[-1].lower()
    mime_type = mime_map.get(ext, "audio/wav")
    
    return client.transcribe_audio(contents, mime_type)

# ------- 3. Agent Module -------

class ChatRequest(BaseModel):
    prompt: str
    context: Optional[str] = ""

@app.post("/agent/chat")
async def agent_chat(request: ChatRequest, x_api_key: Optional[str] = Header(None)):
    client = get_gemini_client(x_api_key)
    return client.chat(request.prompt, request.context)

class ExtractRequest(BaseModel):
    text: str
    schema_description: str

@app.post("/agent/extract")
async def extract_data(request: ExtractRequest, x_api_key: Optional[str] = Header(None)):
    client = get_gemini_client(x_api_key)
    return client.extract_structured_data(request.text, request.schema_description)

# ------- 4. Spatial Module (SpatialVCS) -------

class SpatialQueryRequest(BaseModel):
    query: str
    scan_id: Optional[str] = None
    top_k: int = 3

class SpatialDiffRequest(BaseModel):
    scan_id_before: str
    scan_id_after: str

@app.post("/spatial/scan/frame")
async def receive_frame(
    scan_id: str = Form(...),
    center_depth: float = Form(...),
    pose: str = Form(...),
    image: UploadFile = File(...),
    x_api_key: Optional[str] = Header(None)
):
    """
    SpatialVCS: Receive single frame (REST).
    """
    client = get_gemini_client(x_api_key)
    timestamp = time.time()
    
    image_bytes = await image.read()
    detections = process_frame(image_bytes, center_depth, pose, scan_id)
    scan_record = _ensure_scan(scan_id, source="rest")
    scan_record["frames"] += 1
    scan_record["updated_at"] = timestamp
    if detections:
        scan_record["last_frame_path"] = detections[0].get("frame_path")
    
    if detections:
        description_data = client.describe_for_spatial(image_bytes)
        gemini_objects = description_data.get("objects", [])
        
        for obj in gemini_objects:
            meta = {
                "scan_id": scan_id,
                "frame_path": detections[0]["frame_path"],
                "timestamp": timestamp,
                "yolo_detections": detections,
                "details": obj
            }
            text_to_index = f"{obj.get('name', '')} {obj.get('position', '')} {obj.get('details', '')}"
            spatial_memory.add_observation(text_to_index, meta)
            scan_record["objects"].append({
                "name": obj.get("name", ""),
                "position": obj.get("position", ""),
                "details": obj.get("details", ""),
                "timestamp": timestamp,
                "frame_path": detections[0]["frame_path"],
            })
            
        scan_record["object_count"] += len(gemini_objects)

    return {"status": "processed", "objects_found": len(detections)}

@app.post("/spatial/query")
async def spatial_query(request: SpatialQueryRequest, x_api_key: Optional[str] = Header(None)):
    client = get_gemini_client(x_api_key)
    results = spatial_memory.search(request.query, request.top_k, scan_id=request.scan_id)
    answer = client.answer_spatial_query(request.query, results)
    
    formatted_results = []
    for r in results:
        meta = r["metadata"]
        frame_filename = os.path.basename(meta.get("frame_path", ""))
        scan_id = meta.get("scan_id", "unknown")
        frame_url = f"/spatial/frame/{scan_id}/{frame_filename}"
        
        formatted_results.append({
            "score": r["score"],
            "description": r["description"],
            "frame_url": frame_url,
            "yolo_data": meta.get("yolo_detections", [])
        })

    return {
        "query": request.query,
        "answer": answer.get("answer"),
        "results": formatted_results
    }

@app.get("/spatial/frame/{scan_id}/{filename}")
def get_frame(scan_id: str, filename: str):
    if filename != os.path.basename(filename):
        raise HTTPException(status_code=400, detail="Invalid frame filename")
    path = f"data/frames/{scan_id}/{filename}"
    if os.path.exists(path):
        return FileResponse(path)
    raise HTTPException(status_code=404, detail="Frame not found")

@app.post("/spatial/diff")
async def spatial_diff(request: SpatialDiffRequest, x_api_key: Optional[str] = Header(None)):
    for sid in [request.scan_id_before, request.scan_id_after]:
        if sid not in spatial_scans:
            raise HTTPException(status_code=404, detail=f"Scan '{sid}' not found")
    
    client = get_gemini_client(x_api_key)
    before = spatial_scans[request.scan_id_before].get("objects", [])
    after = spatial_scans[request.scan_id_after].get("objects", [])
    
    result = client.compare_spatial_diffs(before, after)
    return {
        "before_scan": request.scan_id_before,
        "after_scan": request.scan_id_after,
        **result
    }

@app.get("/spatial/scans")
def list_scans():
    return {
        "scans": [
            {
                "scan_id": sid,
                "status": data.get("status", "unknown"),
                "source": data.get("source"),
                "frames": data.get("frames", 0),
                "object_count": data.get("object_count", 0),
                "updated_at": data.get("updated_at"),
                "last_frame": os.path.basename(data.get("last_frame_path") or ""),
            }
            for sid, data in spatial_scans.items()
        ]
    }

@app.get("/spatial/memory/{scan_id}")
def get_memory(scan_id: str):
    if scan_id not in spatial_scans:
        raise HTTPException(status_code=404, detail=f"Scan '{scan_id}' not found")
    return spatial_scans[scan_id]

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
