import React, { useState, useEffect } from 'react';
import useWebSocket, { ReadyState } from 'react-use-websocket';
import { Search, Database, Box, Play, Wifi, Cpu, Activity, Clock, Settings } from 'lucide-react';

export default function DashboardView() {
    const [query, setQuery] = useState('');
    const [searchResults, setSearchResults] = useState([]);
    const [liveDetections, setLiveDetections] = useState([]);
    const [stats, setStats] = useState({ frames: 0, objects: 0, fps: 0 });
    const [apiKey, setApiKey] = useState(localStorage.getItem('gemini_api_key') || '');
    const [showSettings, setShowSettings] = useState(false);
    const [activeScanId, setActiveScanId] = useState('');

    // Save API Key
    const handleSaveKey = (key) => {
        setApiKey(key);
        localStorage.setItem('gemini_api_key', key);
    };

    // WebSocket - Use same origin (Vite proxy)
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socketUrl = `${protocol}//${window.location.host}/ws/dashboard/dashboard_Main`;

    const { lastMessage, readyState } = useWebSocket(socketUrl, {
        shouldReconnect: () => true,
        onOpen: () => console.log('Dashboard Connected'),
    });

    // Handle Incoming Data
    useEffect(() => {
        if (lastMessage !== null) {
            try {
                const data = JSON.parse(lastMessage.data);
                if (data.type === 'detection' && Array.isArray(data.objects)) {
                    if (data.scan_id) {
                        setActiveScanId(data.scan_id);
                    }
                    // Update Live Detections (keep last 6)
                    setLiveDetections(prev => {
                        const newItems = data.objects.map(obj => ({
                            ...obj,
                            id: Math.random().toString(36).substr(2, 9),
                            timestamp: Date.now()
                        }));
                        return [...newItems, ...prev].slice(0, 6);
                    });

                    // Update Stats
                    setStats(prev => ({
                        frames: prev.frames + 1,
                        objects: prev.objects + data.objects.length,
                        fps: Math.round(1000 / (Date.now() - prev.lastFrameTime || 1000)) || 30, // Rough estimate
                        lastFrameTime: Date.now()
                    }));
                }
            } catch (e) {
                console.error("Parse error", e);
            }
        }
    }, [lastMessage]);

    // Search Logic
    const handleSearch = async (e) => {
        e.preventDefault();
        try {
            // Use relative URL (proxy)
            const res = await fetch('/spatial/query', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'x-api-key': apiKey
                },
                body: JSON.stringify({
                    query,
                    top_k: 4,
                    ...(activeScanId ? { scan_id: activeScanId } : {})
                })
            });

            if (!res.ok) {
                const errText = await res.text();
                console.error("Search failed:", res.status, errText);
                alert(`Search failed: ${res.status} ${res.statusText}`); // Simple feedback
                setSearchResults([]);
                return;
            }

            const data = await res.json();
            setSearchResults(data.results || []);
        } catch (err) {
            console.error("Search Exception:", err);
            alert("Search error (see console)");
            setSearchResults([]);
        }
    };

    return (
        <div className="bg-background-dark min-h-screen text-slate-200 font-display selection:bg-primary selection:text-background-dark p-6 flex flex-col">

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

            {/* Header */}
            <header className="flex items-center justify-between mb-8 border-b border-white/5 pb-4">
                <div className="flex items-center space-x-4">
                    <div className="w-10 h-10 bg-gradient-to-br from-primary to-blue-600 rounded-lg flex items-center justify-center shadow-lg shadow-primary/20 border border-primary/30">
                        <Box className="text-white w-6 h-6" />
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold tracking-tight text-white flex items-center">
                            SPATIAL<span className="text-primary">VCS</span>
                        </h1>
                        <p className="text-[10px] font-mono text-primary/60 tracking-widest uppercase">Command Center</p>
                    </div>
                </div>

                <div className="flex items-center space-x-6">
                    {/* Key Config Button */}
                    <button
                        onClick={() => setShowSettings(true)}
                        className={`flex items-center space-x-2 px-3 py-1.5 rounded border border-slate-700 text-xs font-mono transition-colors ${apiKey ? 'text-green-400 border-green-900/50 bg-green-900/10' : 'text-red-400 border-red-900/50 bg-red-900/10 animate-pulse'}`}
                    >
                        <Settings className="w-3 h-3" />
                        <span>{apiKey ? 'API KEY SET' : 'NO API KEY'}</span>
                    </button>

                    <div className="flex items-center space-x-6">
                        {/* Stats Items */}
                        <div className="flex items-center space-x-3 bg-surface-dark px-4 py-2 rounded border border-white/5">
                            <div className="p-1.5 bg-blue-500/10 rounded text-blue-400"><Activity className="w-4 h-4" /></div>
                            <div>
                                <div className="text-[10px] text-slate-500 font-mono uppercase tracking-wider">Frames Processed</div>
                                <div className="text-lg font-bold text-white leading-none">{stats.frames}</div>
                            </div>
                        </div>
                        <div className="flex items-center space-x-3 bg-surface-dark px-4 py-2 rounded border border-white/5">
                            <div className="p-1.5 bg-purple-500/10 rounded text-purple-400"><Database className="w-4 h-4" /></div>
                            <div>
                                <div className="text-[10px] text-slate-500 font-mono uppercase tracking-wider">Objects Scanned</div>
                                <div className="text-lg font-bold text-white leading-none">{stats.objects}</div>
                            </div>
                        </div>
                        <div className="flex items-center space-x-3 bg-surface-dark px-4 py-2 rounded border border-white/5">
                            <div className="p-1.5 bg-green-500/10 rounded text-green-400"><Clock className="w-4 h-4" /></div>
                            <div>
                                <div className="text-[10px] text-slate-500 font-mono uppercase tracking-wider">Real-time FPS</div>
                                <div className="text-lg font-bold text-white leading-none">{stats.fps}</div>
                            </div>
                        </div>
                    </div>

                    <div className={`px-3 py-1 rounded border flex items-center space-x-2 ${readyState === ReadyState.OPEN ? 'border-green-500/50 bg-green-500/10 text-green-400' : 'border-red-500/50 bg-red-500/10 text-red-400'}`}>
                        <div className={`w-2 h-2 rounded-full ${readyState === ReadyState.OPEN ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}></div>
                        <span className="text-xs font-mono font-bold">{readyState === ReadyState.OPEN ? 'ONLINE' : 'OFFLINE'}</span>
                    </div>
                </div>
            </header>

            <div className="flex-1 grid grid-cols-12 gap-6 overflow-hidden">

                {/* Left: Live Detections */}
                <div className="col-span-8 flex flex-col space-y-4">
                    <div className="flex justify-between items-center">
                        <h2 className="text-sm font-mono text-primary/80 flex items-center"><Wifi className="w-4 h-4 mr-2" /> LIVE INTERCEPT</h2>
                    </div>

                    <div className="flex-1 grid grid-cols-3 gap-4 overflow-y-auto pr-2 content-start">
                        {liveDetections.map((obj) => (
                            <div key={obj.id} className="bg-surface-dark border border-slate-800 p-4 rounded-lg hover:border-primary/50 transition-colors group relative overflow-hidden">
                                <div className="absolute top-0 right-0 p-2 opacity-50 text-[10px] font-mono text-slate-500">#{obj.id.toUpperCase()}</div>
                                <div className="w-10 h-10 bg-slate-800 rounded-full flex items-center justify-center mb-3 group-hover:bg-primary/20 transition-colors">
                                    <Box className="w-5 h-5 text-slate-400 group-hover:text-primary" />
                                </div>
                                <h3 className="text-lg font-bold text-white mb-1 group-hover:text-primary transition-colors">{obj.label}</h3>
                                <div className="text-xs font-mono text-slate-500 mb-3">CONFIDENCE: {(obj.confidence * 100).toFixed(1)}%</div>
                                <div className="p-2 bg-black rounded text-[10px] font-mono text-slate-400 grid grid-cols-3 gap-1 text-center">
                                    <div>X: {obj.position?.x.toFixed(1)}</div>
                                    <div>Y: {obj.position?.y.toFixed(1)}</div>
                                    <div>Z: {obj.position?.z.toFixed(1)}</div>
                                </div>
                            </div>
                        ))}
                        {liveDetections.length === 0 && (
                            <div className="col-span-3 h-64 flex items-center justify-center border-2 border-dashed border-slate-800 rounded-xl text-slate-600 font-mono">
                                WAITING FOR PROBE DATA...
                            </div>
                        )}
                    </div>
                </div>

                {/* Right: Search */}
                <div className="col-span-4 bg-surface-darker/50 border-l border-slate-800 pl-6 flex flex-col">
                    <h2 className="text-sm font-mono text-primary/80 mb-4 flex items-center"><Cpu className="w-4 h-4 mr-2" /> SEMANTIC QUERY</h2>

                    <form onSubmit={handleSearch} className="mb-6 relative">
                        <input
                            type="text"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            placeholder="Example: 'Where are my keys?'"
                            className="w-full bg-surface-dark border border-slate-700 rounded-lg py-3 pl-4 pr-12 text-sm text-white focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all"
                        />
                        <button type="submit" className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 bg-primary rounded text-black hover:bg-white transition-colors">
                            <Search className="w-4 h-4" />
                        </button>
                    </form>

                    <div className="flex-1 overflow-y-auto space-y-4">
                        {Array.isArray(searchResults) && searchResults.map((res, i) => (
                            <div key={i} className="bg-ui-panel border border-slate-700 rounded p-3 hover:border-primary/40 transition-colors">
                                <div className="text-xs font-mono text-green-400 mb-1">MATCH SCORE: {(res.score * 100).toFixed(0)}%</div>
                                <p className="text-sm text-slate-300 mb-2">{res.description}</p>
                                {res.frame_url && (
                                    <div className="h-24 bg-black rounded overflow-hidden relative group cursor-pointer">
                                        {/* Use relative path for proxy */}
                                        <img src={res.frame_url} className="w-full h-full object-cover opacity-70 group-hover:opacity-100 transition-opacity" />
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                </div>

            </div>
        </div>
    );
}

function StatBox({ label, value, icon: Icon, color = "text-primary" }) {
    return (
        <div className="flex items-center space-x-3">
            <div className={`p-2 rounded bg-slate-800/50 ${color}`}>
                <Icon className="w-4 h-4" />
            </div>
            <div>
                <div className="text-[10px] font-mono text-slate-500 tracking-wider">{label}</div>
                <div className={`text-lg font-bold font-mono ${color}`}>{value}</div>
            </div>
        </div>
    )
}
