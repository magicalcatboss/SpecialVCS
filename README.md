# SpatialVCS (CTRL+HACK+DEL 2.0)

> **Empowering the Unseen: Mapping Physical Reality into Searchable Memory.**

[![GitHub](https://img.shields.io/badge/GitHub-SpatialVCS-blue?logo=github)](https://github.com/magicalcatboss/SpatialVCS)
[![Status](https://img.shields.io/badge/Status-Active-success)](#)
[![Competition](https://img.shields.io/badge/Competition-CTRL+HACK+DEL_2.0-red)](#)

## 🌟 Our Mission

In a world defined by three-dimensional space, navigating and tracking objects can be a significant challenge, especially for individuals with visual impairments. **SpatialVCS** is designed to rewrite this narrative by creating a bridge between physical reality and digital intelligence.

By leveraging advanced spatial mapping and AI-powered computer vision (YOLO and Gemini), we transform your mobile phone into a "smart probe." Our mission is to empower users to seamlessly track, search, and understand their surroundings, ensuring that no object is ever "lost" and every space is intuitively accessible.

This project is a submission for the **CTRL+HACK+DEL 2.0** competition.

## Why "SpatialVCS"?

- **Spatial (Space):** Transforming raw video data into precise XYZ coordinates and semantic understandings of the physical world.
- **Version (History):** Tracking changes over time, allowing users to query not just where an object is, but where it *was*.
- **Control (System):** Providing a robust, searchable management layer for physical objects and spatial data.

## ✨ Key Features

- **Real-time Object Tracking:** Seamlessly detect and map objects in 3D space using mobile sensors.
- **Natural Language Querying:** Ask "Where are my keys?" and get precise, AI-assisted locations.
- **Semantic Memory:** Powered by Gemini for deep understanding of object context and identity.
- **Access Control & Diffs:** Manage who sees what and see what has moved between scans.

---

## 🚀 Quick Start for Teammates (One-Click)

### Option A: One-Click Script (Recommended)
We have prepared `.command` scripts to automate everything.
1.  Double-click `setup_env.command` to install Python/Node dependencies and generate SSL certs.
2.  Double-click `start_app.command` to launch both backend and frontend.

### Option B: Manual Setup
If the scripts don't work, follow these steps:

### Prerequisites
- **Node.js** (v18+)
- **Python** (3.10+)
- **mkcert** (For SSL certificates - Required for mobile camera access)
  - macOS: `brew install mkcert nss`
  - Windows: `choco install mkcert`

### 1. Clone & Setup Backend
```bash
# Clone repository
git clone <repo-url>
cd gemini_toolkit

# Create Python Virtual Environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install Dependencies
pip install -r requirements.txt
```

### 2. Setup Frontend
```bash
cd frontend
npm install
```

### 3. Generate SSL Certificates (Crucial!)
Since we use the camera on mobile and connect via local network IP, we need HTTPS.
Run this in the root directory:

```bash
# Install CA
mkcert -install

# Generate certs for localhost and your local IP (e.g., 100.x.y.z or 192.168.x.y)
# IMPORTANT: Replace 100.104.16.42 with YOUR actual LAN IP!
mkcert -key-file key.pem -cert-file cert.pem localhost 127.0.0.1 ::1 100.104.16.42
```
*Note: The frontend must act as HTTPS server for the mobile camera to work. If you skip this, mobile access will fail.*

### 4. Run the System
You need two terminal windows.

**Terminal 1: Backend**
```bash
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2: Frontend**
```bash
cd frontend
npm run dev -- --host
```

### 5. Open & Connect
1.  **Mobile (Probe)**: Open `https://<YOUR-IP>:5173/probe` (Accept SSL warning).
    -   Click "CFG" -> Enter Gemini API Key.
    -   Click "START SCAN".
2.  **Desktop (Dashboard)**: Open `https://localhost:5173/dashboard`.
    -   Enter Gemini API Key.
    -   See live detections and XYZ coordinates.
    -   Search: "Where is the [object]?"

## Project Structure
- `main.py`: FastAPI backend entry point.
- `services/`: Logic for YOLO (`video_processor.py`) and Vector DB (`spatial_memory.py`).
- `frontend/src/components/`: React views (`ProbeView.jsx`, `DashboardView.jsx`).

## Troubleshooting
- **White Screen on Mobile?**
  - Check the console (remote debug).
  - Ensure SSL certs are valid and generated for your specific LAN IP.
  - Verify your phone is on the same Wi-Fi network as your computer.
  - Try accessing `https://<YOUR-IP>:5173/probe` directly.
- **Search fails?** Ensure you entered the API Key in Settings ("CFG" button).
- **Backend 422 Error?** Fixed in latest version (scan_id is optional).

## Screenshots
*(Add screenshots here)*

## License
Distributed under the MIT License. See `LICENSE` for more information.

## Team Members

<div align="center">

| [<img src="https://github.com/HansonHe-UW.png?size=100" width="100"><br><sub><b>Hanson He</b></sub>](https://github.com/HansonHe-UW) | [<img src="https://github.com/magicalcatboss.png?size=100" width="100"><br><sub><b>Yingxuan Wang</b></sub>](https://github.com/magicalcatboss) | [<img src="https://github.com/molly-xie-uw.png?size=100" width="100"><br><sub><b>Molly Xie</b></sub>](https://github.com/molly-xie-uw) |
| :---: | :---: | :---: |
| [![GitHub](https://img.shields.io/badge/GitHub-181717?style=flat-square&logo=github&logoColor=white)](https://github.com/HansonHe-UW) | [![GitHub](https://img.shields.io/badge/GitHub-181717?style=flat-square&logo=github&logoColor=white)](https://github.com/magicalcatboss) | [![GitHub](https://img.shields.io/badge/GitHub-181717?style=flat-square&logo=github&logoColor=white)](https://github.com/molly-xie-uw) |
| [![LinkedIn](https://img.shields.io/badge/LinkedIn-0A66C2?style=flat-square&logo=linkedin&logoColor=white)](https://linkedin.com/in/shengyuan-he) | [![LinkedIn](https://img.shields.io/badge/LinkedIn-0A66C2?style=flat-square&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/yingxuan-wang-uw) | [![LinkedIn](https://img.shields.io/badge/LinkedIn-0A66C2?style=flat-square&logo=linkedin&logoColor=white)](https://linkedin.com/in/molly-xie-uw) |

</div>
