import { Suspense, useMemo } from "react";
import { Canvas, useLoader } from "@react-three/fiber";
import { Bounds, Center, OrbitControls } from "@react-three/drei";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import * as THREE from "three";
import { api } from "../../api/client";
import type { Part } from "../../api/types";

function Model({ url }: { url: string }) {
  const geometry = useLoader(STLLoader, url);
  const edges = useMemo(() => new THREE.EdgesGeometry(geometry, 30), [geometry]);
  return (
    // CAD is Z-up; three.js is Y-up.
    <group rotation={[-Math.PI / 2, 0, 0]}>
      <mesh geometry={geometry} castShadow>
        <meshStandardMaterial color="#94a3b8" metalness={0.35} roughness={0.45} />
      </mesh>
      <lineSegments geometry={edges}>
        <lineBasicMaterial color="#0f172a" />
      </lineSegments>
    </group>
  );
}

export function PartPreview3D({ part }: { part: Part }) {
  const url = api.meshUrl(part);
  return (
    <div className="relative h-48 overflow-hidden rounded-lg border border-slate-800 bg-gradient-to-b from-slate-800 to-slate-900">
      <Canvas camera={{ position: [1, 0.8, 1.3], fov: 35 }} dpr={[1, 2]}>
        <ambientLight intensity={0.6} />
        <directionalLight position={[3, 5, 4]} intensity={1.6} />
        <directionalLight position={[-4, -2, -3]} intensity={0.5} />
        <Suspense fallback={null}>
          <Bounds key={part.part_id} fit clip observe margin={1.25}>
            <Center>
              <Model url={url} />
            </Center>
          </Bounds>
        </Suspense>
        <OrbitControls makeDefault enablePan={false} />
      </Canvas>
      <span className="pointer-events-none absolute bottom-1.5 left-2 text-[10px] uppercase tracking-wider text-slate-500">
        drag to orbit · scroll to zoom
      </span>
    </div>
  );
}
