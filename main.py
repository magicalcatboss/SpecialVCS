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
import math
import asyncio
from dotenv import load_dotenv

# Import Services
from services.vision import analyze_face_image
from services.audio import text_to_speech_stream
from services.llm import GeminiClient
from services.video_processor import process_frame, crop_detections
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

def _int_env(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default

YOLO_FRAME_STRIDE = _int_env("SPATIAL_YOLO_FRAME_STRIDE", 2)
GEMINI_FRAME_STRIDE = _int_env("SPATIAL_GEMINI_FRAME_STRIDE", 3)
MAX_GEMINI_CROPS = _int_env("SPATIAL_MAX_GEMINI_CROPS", 3, minimum=1)
FALLBACK_KEY_BUCKET_PX = _int_env("SPATIAL_FALLBACK_KEY_BUCKET_PX", 96, minimum=16)
GEMINI_LABEL_TTL_SEC = float(os.getenv("SPATIAL_GEMINI_LABEL_TTL_SEC", "20"))


def _ensure_scan(scan_id: str, source: Optional[str] = None) -> dict:
    if scan_id not in spatial_scans:
        spatial_scans[scan_id] = {
            "scan_id": scan_id,
            "status": "scanning",
            "source": source,
            "frames": 0,
            "object_count": 0,
            "objects": [],
            "detections": [],
            "gemini_label_cache": {},
            "last_frame_path": None,
            "updated_at": None,
        }
    return spatial_scans[scan_id]


def _object_key_from_detection(det: dict) -> str:
    """Build a stable key for persistence and Gemini label carry-over."""
    tid = det.get("track_id", -1)
    label = det.get("label", "object")
    if tid > -1:
        return f"{label}_{tid}"

    bbox = det.get("bbox", [0, 0, 0, 0])
    cx = int((bbox[0] + bbox[2]) / 2) if len(bbox) == 4 else 0
    cy = int((bbox[1] + bbox[3]) / 2) if len(bbox) == 4 else 0
    cell_x = cx // FALLBACK_KEY_BUCKET_PX
    cell_y = cy // FALLBACK_KEY_BUCKET_PX
    z_val = float(det.get("position_3d", {}).get("z", 0.0))
    z_bucket = int(round(z_val * 2.0))
    return f"{label}_cell_{cell_x}_{cell_y}_{z_bucket}"


def _rotation_matrix_from_orientation(alpha: float, beta: float, gamma: float):
    """
    Convert device orientation angles (degrees) to a 3x3 rotation matrix.
    Approximation: R = Rz(alpha) * Rx(beta) * Ry(gamma).
    """
    a = math.radians(alpha)
    b = math.radians(beta)
    g = math.radians(gamma)

    ca, sa = math.cos(a), math.sin(a)
    cb, sb = math.cos(b), math.sin(b)
    cg, sg = math.cos(g), math.sin(g)

    rz = [
        [ca, -sa, 0.0],
        [sa, ca, 0.0],
        [0.0, 0.0, 1.0],
    ]
    rx = [
        [1.0, 0.0, 0.0],
        [0.0, cb, -sb],
        [0.0, sb, cb],
    ]
    ry = [
        [cg, 0.0, sg],
        [0.0, 1.0, 0.0],
        [-sg, 0.0, cg],
    ]

    def matmul(a3, b3):
        return [
            [
                a3[i][0] * b3[0][j] + a3[i][1] * b3[1][j] + a3[i][2] * b3[2][j]
                for j in range(3)
            ]
            for i in range(3)
        ]

    return matmul(matmul(rz, rx), ry)


def _pose_matrix_str_from_orientation(alpha: float, beta: float, gamma: float) -> str:
    rot = _rotation_matrix_from_orientation(alpha, beta, gamma)
    pose = [
        [rot[0][0], rot[0][1], rot[0][2], 0.0],
        [rot[1][0], rot[1][1], rot[1][2], 0.0],
        [rot[2][0], rot[2][1], rot[2][2], 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    return ",".join(str(pose[r][c]) for r in range(4) for c in range(4))


def _record_detections(scan_record: dict, detections: list, timestamp: float):
    for det in detections:
        scan_record["detections"].append({
            "label": det.get("label", ""),
            "yolo_label": det.get("yolo_label", det.get("label", "")),
            "gemini_name": det.get("gemini_name", ""),
            "confidence": float(det.get("confidence", 0.0)),
            "position_3d": det.get("position_3d", {}),
            "timestamp": timestamp,
            "frame_path": det.get("frame_path", ""),
        })


def _euclidean_distance(a: dict, b: dict) -> float:
    ax, ay, az = float(a.get("x", 0.0)), float(a.get("y", 0.0)), float(a.get("z", 0.0))
    bx, by, bz = float(b.get("x", 0.0)), float(b.get("y", 0.0)), float(b.get("z", 0.0))
    try:
        from scipy.spatial.distance import euclidean
        return float(euclidean([ax, ay, az], [bx, by, bz]))
    except Exception:
        dx, dy, dz = ax - bx, ay - by, az - bz
        return math.sqrt(dx * dx + dy * dy + dz * dz)


def _latest_position_by_label(detections: list) -> Dict[str, dict]:
    latest = {}
    for item in detections:
        label = item.get("yolo_label") or item.get("label")
        position = item.get("position_3d")
        if not label or not isinstance(position, dict):
            continue
        prev = latest.get(label)
        if prev is None or float(item.get("timestamp", 0.0)) > float(prev.get("timestamp", 0.0)):
            latest[label] = item
    return latest

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

            if data.get("type") == "auth":
                msg_key = data.get("api_key")
                if msg_key:
                    gemini = GeminiClient(msg_key)
                    await socket_manager.send_to_probe(client_id, {"type": "auth_ack"})
                continue

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
                frame_api_key = data.get("api_key")
                if frame_api_key:
                    try:
                        gemini = GeminiClient(frame_api_key)
                    except Exception:
                        pass

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
                alpha = float(pose_data.get("alpha", 0) or 0)
                beta = float(pose_data.get("beta", 0) or 0)
                gamma = float(pose_data.get("gamma", 0) or 0)
                pose_str = _pose_matrix_str_from_orientation(alpha, beta, gamma)
                estimated_depth = 1.5  # Default assumed distance

                # --- Step 3: YOLO Detection + 3D Coordinate Estimation ---
                detections = []
                frame_path = ""
                should_run_yolo = (frame_count % YOLO_FRAME_STRIDE == 1)
                if should_run_yolo:
                    detections, frame_path = process_frame(
                        image_bytes, estimated_depth, pose_str, scan_id, return_frame_path=True
                    )
                else:
                    # Save this frame path without running detection to reduce 8m load spikes.
                    _, frame_path = process_frame(
                        image_bytes, estimated_depth, pose_str, scan_id, run_detection=False, return_frame_path=True
                    )

                # --- Step 4: Gemini Semantic Description (per-object via crops) ---
                gemini_objects = []
                run_gemini = gemini and (frame_count % GEMINI_FRAME_STRIDE == 1)
                if run_gemini and detections:
                    try:
                        crops = crop_detections(image_bytes, detections)
                        pairs = [(c, d) for c, d in zip(crops, detections) if c is not None]
                        pairs = pairs[:MAX_GEMINI_CROPS]

                        async def _describe(crop, det):
                            desc = await asyncio.to_thread(gemini.describe_crop, crop, det["label"])
                            return desc, det

                        results = await asyncio.gather(*[_describe(c, d) for c, d in pairs])
                        for desc, det in results:
                            gemini_obj = {
                                "name": desc.get("name", det["label"]),
                                "position": det.get("position_3d", {}),
                                "details": desc.get("details", ""),
                                "bbox": det.get("bbox"),
                                "track_id": det.get("track_id", -1),
                                "yolo_label": det["label"],
                                "confidence": det["confidence"],
                            }
                            gemini_objects.append(gemini_obj)
                            # Enrich the detection with Gemini description
                            det["gemini_name"] = gemini_obj["name"]
                            det["gemini_details"] = gemini_obj["details"]
                    except Exception as e:
                        print(f"Gemini crop error: {e}")

                # --- Step 5: Store in Spatial Memory ---
                scan_record = _ensure_scan(scan_id, source=client_id)
                scan_record["frames"] += 1
                scan_record["updated_at"] = timestamp
                if frame_path:
                    scan_record["last_frame_path"] = frame_path
                elif detections:
                    scan_record["last_frame_path"] = detections[0].get("frame_path")

                if detections:
                    _record_detections(scan_record, detections, timestamp)

                for obj in gemini_objects:
                    meta = {
                        "scan_id": scan_id,
                        "frame_path": frame_path or (detections[0]["frame_path"] if detections else ""),
                        "timestamp": timestamp,
                        "bbox": obj.get("bbox"),
                        "track_id": obj.get("track_id", -1),
                        "yolo_label": obj.get("yolo_label", ""),
                        "confidence": obj.get("confidence", 0),
                        "position_3d": obj.get("position"),
                        "source": client_id
                    }
                    text_to_index = f"{obj.get('name','')} {obj.get('details','')}"
                    try:
                        spatial_memory.add_observation(text_to_index, meta)
                    except Exception as e:
                        print(f"Spatial memory add failed: {e}")
                    scan_record["objects"].append({
                        "name": obj.get("name", ""),
                        "position": obj.get("position", {}),
                        "details": obj.get("details", ""),
                        "timestamp": timestamp,
                        "frame_path": meta["frame_path"],
                    })

                scan_record["object_count"] += len(gemini_objects)

                # --- Step 6: Broadcast Results to All Dashboards ---
                broadcast_objects = []
                state_vector = {} # Map<ID, Vector>
                gemini_label_cache = scan_record.get("gemini_label_cache", {})

                for d in detections:
                    tid = d.get("track_id", -1)
                    label = d["label"]
                    obj_key = _object_key_from_detection(d)

                    # Preserve the latest Gemini naming for this tracked object so
                    # non-Gemini frames do not revert UI labels back to raw YOLO words.
                    if d.get("gemini_name"):
                        gemini_label_cache[obj_key] = {
                            "name": d.get("gemini_name", label),
                            "details": d.get("gemini_details", ""),
                            "updated_at": float(timestamp),
                        }

                    cached = gemini_label_cache.get(obj_key)
                    if cached and (float(timestamp) - float(cached.get("updated_at", 0.0)) <= GEMINI_LABEL_TTL_SEC):
                        display_label = cached.get("name", label)
                        display_details = cached.get("details", d.get("gemini_details", ""))
                    else:
                        display_label = d.get("gemini_name", label)
                        display_details = d.get("gemini_details", "")
                        if cached:
                            gemini_label_cache.pop(obj_key, None)

                    # Simplified Vector for Frontend
                    vec = {
                        "x": d.get("position_3d", {}).get("x", 0),
                        "y": d.get("position_3d", {}).get("y", 0),
                        "z": d.get("position_3d", {}).get("z", 0),
                        "confidence": d["confidence"],
                        "track_id": tid,
                        "label": display_label,
                        "yolo_label": d["label"]
                    }
                    state_vector[obj_key] = vec

                    broadcast_objects.append({
                        "label": display_label,
                        "yolo_label": d["label"],
                        "details": display_details,
                        "confidence": d["confidence"],
                        "track_id": tid,
                        "bbox": d.get("bbox"),
                        "position": d.get("position_3d", {"x": 0, "y": 0, "z": estimated_depth})
                    })

                scan_record["gemini_label_cache"] = gemini_label_cache

                await socket_manager.broadcast_to_dashboards({
                    "type": "detection",
                    "source": client_id,
                    "scan_id": scan_id,
                    "frame_number": frame_count,
                    "objects": broadcast_objects,
                    "state_vector": state_vector,
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
        try:
            await socket_manager.broadcast_to_dashboards({
                "type": "probe_disconnected", "source": client_id
            })
        except Exception:
            pass
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
    threshold: float = 0.5

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
        _record_detections(scan_record, detections, timestamp)
    
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
    
    before_scan = spatial_scans[request.scan_id_before]
    after_scan = spatial_scans[request.scan_id_after]
    before_latest = _latest_position_by_label(before_scan.get("detections", []))
    after_latest = _latest_position_by_label(after_scan.get("detections", []))

    before_labels = set(before_latest.keys())
    after_labels = set(after_latest.keys())
    common_labels = before_labels & after_labels

    events = []
    for label in sorted(common_labels):
        old_pos = before_latest[label].get("position_3d", {})
        new_pos = after_latest[label].get("position_3d", {})
        dist = _euclidean_distance(new_pos, old_pos)
        if dist > request.threshold:
            events.append({
                "type": "MOVE",
                "label": label,
                "distance": round(dist, 4),
                "from": old_pos,
                "to": new_pos,
            })

    for label in sorted(after_labels - before_labels):
        events.append({
            "type": "ADDED",
            "label": label,
            "distance": None,
            "from": None,
            "to": after_latest[label].get("position_3d", {}),
        })

    for label in sorted(before_labels - after_labels):
        events.append({
            "type": "REMOVED",
            "label": label,
            "distance": None,
            "from": before_latest[label].get("position_3d", {}),
            "to": None,
        })

    summary = f"{len(events)} changes detected (threshold={request.threshold}m)."
    return {
        "before_scan": request.scan_id_before,
        "after_scan": request.scan_id_after,
        "threshold": request.threshold,
        "change_count": len(events),
        "events": events,
        "summary": summary,
    }

@app.delete("/spatial/reset")
async def reset_spatial_data(x_api_key: Optional[str] = Header(None)):
    """
    Reset all spatial memory and scans.
    """
    # Require API key to prevent accidental or unauthorized reset.
    get_gemini_client(x_api_key)
    
    # 1. Clear Chroma
    spatial_memory.reset_database()
    
    # 2. Clear In-Memory Scans
    spatial_scans.clear()
    
    # 3. Notify Dashboards
    await socket_manager.broadcast_to_dashboards({
        "type": "system_reset",
        "log": "SYSTEM RESET: All spatial memory cleared."
    })
    
    return {"status": "ok", "message": "Spatial memory cleared"}

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
                "detection_count": len(data.get("detections", [])),
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
