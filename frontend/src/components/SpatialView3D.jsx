import React, { useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Text, Line } from '@react-three/drei';

function AxisLines() {
    return (
        <>
            {/* X axis - red */}
            <Line points={[[-3, 0, 0], [3, 0, 0]]} color="#ef4444" lineWidth={1.5} />
            <Text position={[3.3, 0, 0]} fontSize={0.2} color="#ef4444" anchorX="left">X</Text>
            {/* Y axis - green */}
            <Line points={[[0, -3, 0], [0, 3, 0]]} color="#22c55e" lineWidth={1.5} />
            <Text position={[0, 3.3, 0]} fontSize={0.2} color="#22c55e" anchorX="center">Y</Text>
            {/* Z axis - blue */}
            <Line points={[[0, 0, -3], [0, 0, 3]]} color="#3b82f6" lineWidth={1.5} />
            <Text position={[0, 0, 3.3]} fontSize={0.2} color="#3b82f6" anchorX="center">Z</Text>
            {/* Grid lines on XZ plane */}
            {[-2, -1, 0, 1, 2].map(i => (
                <React.Fragment key={`grid-${i}`}>
                    <Line points={[[i, 0, -3], [i, 0, 3]]} color="#334155" lineWidth={0.5} />
                    <Line points={[[-3, 0, i], [3, 0, i]]} color="#334155" lineWidth={0.5} />
                </React.Fragment>
            ))}
        </>
    );
}

function ObjectSphere({ position, label, color }) {
    const meshRef = useRef();
    useFrame((_, delta) => {
        if (meshRef.current) {
            meshRef.current.rotation.y += delta * 0.5;
        }
    });

    return (
        <group position={position}>
            <mesh ref={meshRef}>
                <sphereGeometry args={[0.12, 16, 16]} />
                <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.4} />
            </mesh>
            {/* Glow ring */}
            <mesh rotation={[Math.PI / 2, 0, 0]}>
                <ringGeometry args={[0.15, 0.18, 32]} />
                <meshBasicMaterial color={color} transparent opacity={0.3} />
            </mesh>
            <Text
                position={[0, 0.25, 0]}
                fontSize={0.12}
                color="white"
                anchorX="center"
                anchorY="bottom"
                outlineWidth={0.01}
                outlineColor="black"
            >
                {label.length > 20 ? label.slice(0, 18) + '…' : label}
            </Text>
        </group>
    );
}

function hashToColor(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    const h = Math.abs(hash) % 360;
    return `hsl(${h}, 70%, 60%)`;
}

export default function SpatialView3D({ objects }) {
    if (!objects || objects.length === 0) {
        return (
            <div className="w-full h-full flex items-center justify-center border border-slate-800 rounded bg-black/30 text-slate-600 font-mono text-xs">
                NO SPATIAL DATA
            </div>
        );
    }

    return (
        <div className="w-full h-full rounded border border-slate-800 overflow-hidden bg-black/50">
            <Canvas camera={{ position: [4, 3, 4], fov: 50 }}>
                <ambientLight intensity={0.3} />
                <pointLight position={[5, 5, 5]} intensity={0.8} />
                <AxisLines />
                {objects.map((obj, i) => {
                    const pos = obj.position || {};
                    const x = Number(pos.x) || 0;
                    const y = Number(pos.y) || 0;
                    const z = Number(pos.z) || 0;
                    const label = obj.label || obj.yolo_label || 'unknown';
                    return (
                        <ObjectSphere
                            key={`${label}-${i}`}
                            position={[x, y, z]}
                            label={label}
                            color={hashToColor(obj.yolo_label || label)}
                        />
                    );
                })}
                <OrbitControls enableDamping dampingFactor={0.1} />
            </Canvas>
        </div>
    );
}
