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
  const sidebarOpen = useStore((s) => s.sidebarOpen);
  const setSidebarOpen = useStore((s) => s.setSidebarOpen);
  useEffect(() => {
    init();
  }, [init]);
  useLayoutSync();
  useAnnotationSync();

  return (
    <div className="flex h-dvh flex-col">
      <TopToolbar />
      <div className="relative flex min-h-0 flex-1">
        {/* Phones: the settings panel is a slide-in drawer over the canvas. */}
        {sidebarOpen && (
          <div
            className="absolute inset-0 z-30 bg-slate-950/60 backdrop-blur-[1px] md:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}
        <div
          className={`absolute inset-y-0 left-0 z-40 w-[min(20rem,88vw)] transition-transform duration-200 md:static md:z-auto md:w-80 md:translate-x-0 md:transition-none ${
            sidebarOpen ? "translate-x-0 shadow-2xl" : "-translate-x-full"
          }`}
        >
          <Sidebar />
        </div>
        <main className="min-w-0 flex-1 bg-slate-900">
          <DrawingCanvas />
        </main>
      </div>
      <Toasts />
    </div>
  );
}
