import { useEffect } from "react";
import { DrawingCanvas } from "./components/canvas/DrawingCanvas";
import { Sidebar } from "./components/sidebar/Sidebar";
import { TopToolbar } from "./components/toolbar/TopToolbar";
import { Toasts } from "./components/ui/Toasts";
import { useStore } from "./state/store";
import { useAnnotationSync } from "./state/useAnnotationSync";
import { useLayoutSync } from "./state/useLayoutSync";

export default function App() {
  const init = useStore((s) => s.init);
  useEffect(() => {
    init();
  }, [init]);
  useLayoutSync();
  useAnnotationSync();

  return (
    <div className="flex h-screen flex-col">
      <TopToolbar />
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <main className="min-w-0 flex-1 bg-slate-900">
          <DrawingCanvas />
        </main>
      </div>
      <Toasts />
    </div>
  );
}
