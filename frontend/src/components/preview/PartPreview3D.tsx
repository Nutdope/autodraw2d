import { Suspense, useEffect, useMemo, useRef } from "react";
import { Canvas, useFrame, useLoader, useThree } from "@react-three/fiber";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import * as THREE from "three";
import { api } from "../../api/client";
import type { Part } from "../../api/types";

const VIEW_DIR = new THREE.Vector3(1, 0.8, 1.3).normalize(); // front-right-top, like the iso view

/** Orbit controls + camera framed on the part (replaces drei's Bounds/OrbitControls). */
function Rig({ radius }: { radius: number }) {
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera;
  const dom = useThree((s) => s.gl.domElement);
  const controlsRef = useRef<OrbitControls | null>(null);

  useEffect(() => {
    // Created inside the effect so StrictMode's mount/unmount/mount never reuses a disposed instance.
    const controls = new OrbitControls(camera, dom);
    controlsRef.current = controls;
    const fit = (radius / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2))) * 1.15;
    camera.position.copy(VIEW_DIR).multiplyScalar(fit);
    camera.near = fit / 100;
    camera.far = fit * 100;
    camera.updateProjectionMatrix();
    controls.target.set(0, 0, 0);
    controls.enablePan = false;
    controls.enableDamping = true;
    controls.minDistance = radius * 1.2;
    controls.maxDistance = fit * 4;
    controls.update();
    return () => {
      controls.dispose();
      controlsRef.current = null;
    };
  }, [camera, dom, radius]);

  useFrame(() => controlsRef.current?.update());
  return null;
}

function Model({ url }: { url: string }) {
  const loaded = useLoader(STLLoader, url);
  const { geometry, edges, radius } = useMemo(() => {
    const g = loaded.clone();
    g.rotateX(-Math.PI / 2); // CAD is Z-up; three.js is Y-up
    g.center();
    g.computeBoundingSphere();
    return { geometry: g, edges: new THREE.EdgesGeometry(g, 30), radius: g.boundingSphere?.radius || 1 };
  }, [loaded]);

  return (
    <>
      <mesh geometry={geometry}>
        <meshStandardMaterial color="#94a3b8" metalness={0.35} roughness={0.45} />
      </mesh>
      <lineSegments geometry={edges}>
        <lineBasicMaterial color="#0f172a" />
      </lineSegments>
      <Rig radius={radius} />
    </>
  );
}

export function PartPreview3D({ part }: { part: Part }) {
  const url = api.meshUrl(part);
  return (
    <div className="relative h-48 overflow-hidden rounded-lg border border-slate-800 bg-gradient-to-b from-slate-800 to-slate-900">
      <Canvas camera={{ fov: 35 }} dpr={[1, 2]}>
        <ambientLight intensity={0.6} />
        <directionalLight position={[3, 5, 4]} intensity={1.6} />
        <directionalLight position={[-4, -2, -3]} intensity={0.5} />
        <Suspense fallback={null}>
          <Model key={part.part_id} url={url} />
        </Suspense>
      </Canvas>
      <span className="pointer-events-none absolute bottom-1.5 left-2 text-[10px] uppercase tracking-wider text-slate-500">
        drag to orbit · scroll to zoom
      </span>
    </div>
  );
}
