# 🐳 SpatialVCS Docker Setup

How to run this project on another computer using Docker.

## Prerequisites
1.  **Install Docker Desktop**: [Download here](https://www.docker.com/products/docker-desktop/)
2.  **Get a Gemini API Key**: [Google AI Studio](https://aistudio.google.com/)

## Rapid Start (3 Steps)

### 1. Configure API Key
Copy the example environment file and add your key:
```bash
cp .env.example .env
# Edit .env and paste your GEMINI_API_KEY
```

### 2. Generate SSL Certs (Required for Camera)
Run this command to generate self-signed certificates:
```bash
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
```

### 3. Launch!
```bash
docker-compose up --build
```

---

## Access URLs

Once running (wait for "VITE ready in..." logs):

*   **💻 Dashboard (Computer)**: `https://localhost:5173/dashboard`
*   **📱 Scanner (Mobile)**:
    1.  Find your computer's **Local IP Address** (e.g., `192.168.1.5`).
    2.  On mobile browser: `https://YOUR_IP:5173/probe` (e.g., `https://192.168.1.5:5173/probe`).
    3.  **Accept the "Unsafe Certificate" warning**.

## Troubleshooting

*   **Camera Not Working?**: Make sure you are using `HTTPS`. HTTP will block camera access on mobile.
*   **Search Failed?**: Check if your `GEMINI_API_KEY` is valid in `.env`.
*   **Reset Data**: Click the "Trash" icon in the Dashboard header.
