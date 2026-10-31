import { useEffect, useRef, useState } from "react";
import { OceanEngine } from "./vendor/ascii-sharks";
export function Sharks() {
  const ref = useRef<HTMLCanvasElement>(null);
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    let engine: OceanEngine | undefined;
    const start = () => {
      engine?.destroy();
      engine = undefined;
      if (!paused && !document.hidden && ref.current)
        engine = new OceanEngine(ref.current, [
          { kind: "classic", size: 0.9 },
          { kind: "classic", size: 0.65 },
          { kind: "classic", size: 0.6 },
        ]);
    };
    start();
    document.addEventListener("visibilitychange", start);
    return () => {
      engine?.destroy();
      document.removeEventListener("visibilitychange", start);
    };
  }, [paused]);
  return (
    <>
      <canvas ref={ref} className="ocean" aria-hidden="true" />
      <button
        className="motion-button"
        onClick={() => setPaused(!paused)}
        aria-pressed={paused}
      >
        {paused ? "Bật chuyển động" : "Dừng chuyển động"}
      </button>
    </>
  );
}
