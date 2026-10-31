import { useEffect, useRef } from "react";
import { OceanEngine, type SharkSpec } from "./vendor/ascii-sharks";

const SHARK_HERO_SPECS: SharkSpec[] = [
  {
    kind: "classic",
    size: 0.95,
    palette: {
      name: "Cyber Cyan",
      tint: [0.35, 1.25, 1.75],
      accent: "#00f0ff",
      eyeColor: "#cbfdff",
    },
  },
  {
    kind: "classic",
    size: 0.72,
    palette: {
      name: "Solar Flare",
      tint: [1.85, 0.95, 0.25],
      accent: "#ff9900",
      eyeColor: "#fff1cc",
    },
  },
  {
    kind: "hammerhead", // Cá mập đầu búa độc đáo với cephalofoil rộng
    size: 0.88,
    palette: {
      name: "Jade Hammerhead",
      tint: [0.25, 1.75, 0.7],
      accent: "#00ff77",
      eyeColor: "#dcffe7",
    },
  },
  {
    kind: "classic",
    size: 0.6,
    palette: {
      name: "Violet Specter",
      tint: [1.5, 0.45, 1.85],
      accent: "#d946ef",
      eyeColor: "#fce7f3",
    },
  },
];

export function Sharks() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let engine: OceanEngine | undefined;
    const start = () => {
      engine?.destroy();
      engine = undefined;
      if (!document.hidden && ref.current) {
        engine = new OceanEngine(ref.current, SHARK_HERO_SPECS);
      }
    };
    start();
    document.addEventListener("visibilitychange", start);
    return () => {
      engine?.destroy();
      document.removeEventListener("visibilitychange", start);
    };
  }, []);

  return <canvas ref={ref} className="ocean" aria-hidden="true" />;
}
