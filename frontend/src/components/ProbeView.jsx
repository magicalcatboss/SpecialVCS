import React, { useEffect, useRef, useState, useCallback } from 'react';
import useWebSocket, { ReadyState } from 'react-use-websocket';
import { Camera, Radio, Wifi, Settings, History, User } from 'lucide-react';

export default function ProbeView() {
    const [scanId] = useState(`SCN-${Math.floor(Math.random() * 10000)}`);
    const [isScanning, setIsScanning] = useState(false);
    const [logs, setLogs] = useState([]);
    const [framesSent, setFramesSent] = useState(0);
    const [apiKey, setApiKey] = useState(localStorage.getItem('gemini_api_key') || '');
    const [showSettings, setShowSettings] = useState(false);

    const videoRef = useRef(null);
    const canvasRef = useRef(null);
    const intervalRef = useRef(null);

    // Save API Key
    const handleSaveKey = (key) => {
        setApiKey(key);
        localStorage.setItem('gemini_api_key', key);
    };

    // WebSocket — connect via SAME ORIGIN (Vite proxy handles forwarding to :8000)
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Append API Key if exists
    const socketUrl = `${protocol}//${window.location.host}/ws/probe/${scanId}${apiKey ? `?api_key=${apiKey}` : ''}`;

    const { sendMessage, lastMessage, readyState } = useWebSocket(socketUrl, {
        shouldReconnect: () => true,
        reconnectInterval: 3000,
        onOpen: () => addLog('✅ Connected to server!'),
        onClose: () => addLog('❌ Disconnected'),
        onError: (e) => {
            console.error('WS Error:', e);
            addLog('⚠️ WebSocket Error (Check Key?)');
        },
    });

    const addLog = (msg) => {
        setLogs(prev => [msg, ...prev].slice(0, 20));
    };

    // Camera Logic
    useEffect(() => {
        async function startCamera() {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({
                    video: { facingMode: 'environment', width: { ideal: 640 } }
                });
                if (videoRef.current) {
                    videoRef.current.srcObject = stream;
                }
                addLog('📷 Camera initialized');
            } catch (e) {
                addLog(`❌ Camera Error: ${e.message}`);
            }
        }
        startCamera();
    }, []);

    // Scanning Loop
    const captureAndSend = useCallback(() => {
        if (!videoRef.current || !canvasRef.current) return;

        const canvas = canvasRef.current;
        const context = canvas.getContext('2d');

        // Match canvas to video dimensions
        const vw = videoRef.current.videoWidth || 640;
        const vh = videoRef.current.videoHeight || 480;
        canvas.width = vw;
        canvas.height = vh;

        context.drawImage(videoRef.current, 0, 0, vw, vh);
        const base64 = canvas.toDataURL('image/jpeg', 0.4);

        if (readyState === ReadyState.OPEN) {
            sendMessage(JSON.stringify({
                type: 'frame',
                scan_id: scanId,
                timestamp: Date.now() / 1000,
                image: base64
            }));
            setFramesSent(prev => prev + 1);
            addLog(`📤 Frame #${framesSent + 1} sent (${(base64.length / 1024).toFixed(0)}KB)`);
        } else {
            addLog(`⏳ WS not open (state: ${readyState})`);
        }
    }, [readyState, scanId, sendMessage, framesSent]);

    useEffect(() => {
        if (isScanning) {
            intervalRef.current = setInterval(captureAndSend, 1500);
            addLog('🔴 Scan started');
        } else {
            clearInterval(intervalRef.current);
        }
        return () => clearInterval(intervalRef.current);
    }, [isScanning, captureAndSend]);

    const toggleScan = () => {
        if (isScanning) {
            setIsScanning(false);
            if (readyState === ReadyState.OPEN) {
                sendMessage(JSON.stringify({
                    type: 'stop_scan',
                    scan_id: scanId
                }));
                addLog('🛑 Stop signal sent');
            }
        } else {
            setIsScanning(true);
        }
    };

    const connectionColor = readyState === ReadyState.OPEN ? 'bg-green-500' : 'bg-red-500';
    const connectionText = readyState === ReadyState.OPEN ? 'CONNECTED' : 'DISCONNECTED';

    return (
        <div className="bg-background-dark font-display text-slate-200 h-screen flex flex-col overflow-hidden selection:bg-primary selection:text-background-dark">

            {/* Settings Modal */}
            {showSettings && (
                <div className="absolute inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
                    <div className="bg-surface-dark border border-primary/30 rounded-lg p-6 w-full max-w-sm shadow-neon">
                        <h3 className="text-lg font-bold text-primary mb-4 flex items-center">
                            <Settings className="w-5 h-5 mr-2" /> CONFIG
                        </h3>
                        <div className="space-y-4">
                            <div>
                                <label className="text-xs text-slate-400 mb-1 block">GEMINI API KEY</label>
                                <input
                                    type="text"
                                    value={apiKey}
                                    onChange={(e) => handleSaveKey(e.target.value)}
                                    placeholder="AIzaSy..."
                                    className="w-full bg-black border border-slate-700 rounded p-2 text-xs font-mono text-white focus:border-primary outline-none"
                                />
                                <p className="text-[10px] text-slate-500 mt-1">Found in Google AI Studio. Required for object descriptions.</p>
                            </div>
                            <button
                                onClick={() => setShowSettings(false)}
                                className="w-full bg-primary/20 hover:bg-primary/30 text-primary border border-primary/50 rounded py-2 text-sm font-bold transition-colors"
                            >
                                CLOSE
                            </button>
                        </div>
                    </div>
                </div>
            )}

            <canvas ref={canvasRef} className="hidden" />

            {/* Header */}
            <header className="h-14 flex-shrink-0 border-b border-primary/20 bg-surface-darker/90 backdrop-blur-md flex items-center justify-between px-4 z-30 relative shadow-neon">
                <div className="flex items-center space-x-3">
                    <div className={`flex items-center space-x-1.5 px-2 py-0.5 border rounded text-[10px] font-bold tracking-wider ${isScanning ? 'bg-red-500/10 border-red-500/50 text-red-400 animate-pulse-slow' : 'bg-slate-800/50 border-slate-700 text-slate-500'}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${isScanning ? 'bg-red-500 animate-ping' : 'bg-slate-500'}`}></span>
                        <span>{isScanning ? 'LIVE' : 'READY'}</span>
                    </div>
                    <span className="text-xs font-mono text-primary/80 tracking-widest">SCANNER</span>
                </div>
                <div className="flex items-center space-x-2">
                    <div className={`w-2 h-2 rounded-full ${connectionColor}`}></div>
                    <span className="text-[10px] font-mono text-slate-400">{connectionText}</span>
                    <div className="ml-2 w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center border border-primary/50">
                        <User className="text-primary w-4 h-4" />
                    </div>
                </div>
            </header>

            {/* Main Content */}
            <main className="flex-1 relative flex flex-col overflow-hidden bg-black">
                {/* Viewport */}
                <div className="relative w-full h-3/5 bg-surface-darker overflow-hidden border-b-2 border-primary/30 crt-overlay group">
                    <video ref={videoRef} autoPlay playsInline muted className="absolute inset-0 w-full h-full object-cover opacity-60 mix-blend-luminosity brightness-125 contrast-125" />
                    <div className="absolute inset-0 bg-cyber-grid opacity-30"></div>
                    {isScanning && (
                        <div className="absolute w-full h-1 bg-primary/50 blur-[2px] shadow-[0_0_15px_rgba(0,240,255,0.8)] z-10 animate-scan-vertical"></div>
                    )}
                    <div className="absolute top-4 left-4 font-mono text-[10px] text-primary space-y-1">
                        <div>FRAMES: {framesSent}</div>
                        <div>SESSION: {scanId}</div>
                        <div>WS: {connectionText}</div>
                    </div>
                </div>

                {/* Controls */}
                <div className="flex-1 bg-background-dark relative z-20 flex flex-col">
                    <div className="h-1 w-full bg-gradient-to-r from-transparent via-primary/40 to-transparent"></div>
                    <div className="flex-1 px-5 py-4 flex flex-col justify-between">
                        {/* Start Button */}
                        <div className="mt-2 mb-2">
                            <button
                                onClick={toggleScan}
                                className={`group w-full relative overflow-hidden border rounded-lg py-5 shadow-[0_0_20px_rgba(0,240,255,0.15)] active:scale-[0.98] transition-all
                                    ${isScanning ? 'bg-red-900/20 border-red-500/50' : 'bg-surface-dark border-primary/30'}`}
                            >
                                <div className={`absolute inset-0 transition-colors ${isScanning ? 'bg-red-500/10' : 'bg-primary/10 group-hover:bg-primary/20'}`}></div>
                                <div className="relative z-10 flex flex-col items-center justify-center">
                                    <span className={`text-xl font-bold tracking-widest transition-colors flex items-center ${isScanning ? 'text-red-400' : 'text-white group-hover:text-primary'}`}>
                                        <Radio className={`mr-2 ${isScanning ? 'animate-pulse' : ''}`} />
                                        {isScanning ? 'STOP SCAN' : 'START SCAN'}
                                    </span>
                                    <span className="text-[10px] text-primary/60 font-mono mt-1">
                                        {isScanning ? `TRANSMITTING... (${framesSent} frames)` : 'TAP TO BEGIN'}
                                    </span>
                                </div>
                            </button>
                        </div>
                    </div>

                    {/* Logs */}
                    <div className="bg-black border-t border-slate-800 h-40 flex flex-col">
                        <div className="flex items-center justify-between px-3 py-1 bg-surface-darker border-b border-slate-800">
                            <span className="text-[10px] font-mono text-slate-500 uppercase">System Log</span>
                            <div className={`w-2 h-2 rounded-full ${connectionColor}`}></div>
                        </div>
                        <div className="flex-1 overflow-y-auto p-3 font-mono text-[10px] space-y-1">
                            {logs.map((log, i) => (
                                <div key={i} className="text-slate-400">{log}</div>
                            ))}
                        </div>
                    </div>
                </div>
            </main>

            {/* Nav */}
            <nav className="h-16 bg-surface-darker border-t border-primary/20 flex justify-around items-center px-2 z-30">
                <button
                    onClick={() => setShowSettings(true)}
                    className="flex flex-col items-center justify-center w-16 space-y-1 text-slate-500 hover:text-primary transition-colors group"
                >
                    <Settings className="w-6 h-6 group-hover:animate-pulse" />
                    <span className="text-[9px] font-mono tracking-wider">CFG</span>
                </button>
                <div className="relative -top-5">
                    <button className="w-14 h-14 rounded-full bg-primary/10 border border-primary text-primary shadow-[0_0_15px_rgba(0,240,255,0.4)] flex items-center justify-center hover:bg-primary hover:text-black transition-all">
                        <Camera className="w-6 h-6" />
                    </button>
                </div>
                <button className="flex flex-col items-center justify-center w-16 space-y-1 text-slate-500 hover:text-primary transition-colors">
                    <History className="w-6 h-6" />
                    <span className="text-[9px] font-mono tracking-wider">LOGS</span>
                </button>
            </nav>
        </div>
    );
}
