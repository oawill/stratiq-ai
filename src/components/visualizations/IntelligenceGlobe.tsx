"use client";

import { useEffect, useRef } from "react";

/** The four module anchors on the globe: [latitude, longitude] in degrees, and the colour that module is drawn in. */
export const GLOBE_MODULES = [
  { lat: 35, lon: -20, colour: "0,229,255" },
  { lat: 25, lon: 70, colour: "139,92,246" },
  { lat: -30, lon: 110, colour: "96,165,250" },
  { lat: -25, lon: -70, colour: "52,211,153" },
] as const;

const rad = (d: number) => (d * Math.PI) / 180;
const toVec = (lat: number, lon: number): [number, number, number] => [Math.cos(rad(lat)) * Math.sin(rad(lon)), Math.sin(rad(lat)), Math.cos(rad(lat)) * Math.cos(rad(lon))];

/**
 * A lightweight rotating globe of nodes and connecting arcs on a 2D canvas: no 3D engine. It only draws while on screen and while
 * the tab is visible, draws a single still frame when reduced motion is requested, and releases everything on unmount.
 */
export function IntelligenceGlobe({ highlight }: { highlight: number | null }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const hi = useRef<number | null>(null);
  useEffect(() => {
    hi.current = highlight;
  }, [highlight]);

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    // Evenly spread nodes (Fibonacci sphere) plus the four module anchors, joined to their nearest neighbours.
    const N = 70;
    const nodes: [number, number, number][] = Array.from({ length: N }, (_, i) => {
      const y = 1 - (2 * (i + 0.5)) / N;
      const r = Math.sqrt(1 - y * y);
      const a = i * Math.PI * (3 - Math.sqrt(5));
      return [Math.cos(a) * r, y, Math.sin(a) * r];
    });
    const anchors = GLOBE_MODULES.map((m) => toVec(m.lat, m.lon));
    nodes.push(...anchors);
    const edges: [number, number][] = [];
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const d = Math.hypot(nodes[i][0] - nodes[j][0], nodes[i][1] - nodes[j][1], nodes[i][2] - nodes[j][2]);
        if (d < 0.46) edges.push([i, j]);
      }
    }
    let size = 0;
    let angle = 0.6;
    let raf = 0;
    let visible = true;
    let last = 0;
    const tilt = rad(-18);

    const resize = () => {
      const r = el.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      size = r.width;
      el.width = Math.round(r.width * dpr);
      el.height = Math.round(r.height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    const project = (v: [number, number, number]) => {
      const x1 = v[0] * Math.cos(angle) + v[2] * Math.sin(angle);
      const z1 = -v[0] * Math.sin(angle) + v[2] * Math.cos(angle);
      const y2 = v[1] * Math.cos(tilt) - z1 * Math.sin(tilt);
      const z2 = v[1] * Math.sin(tilt) + z1 * Math.cos(tilt);
      return { x: x1, y: y2, z: z2 };
    };
    const draw = (t: number) => {
      const R = size * 0.36;
      const c = size / 2;
      ctx.clearRect(0, 0, size, size);
      const halo = ctx.createRadialGradient(c, c, R * 0.2, c, c, R * 1.35);
      halo.addColorStop(0, "rgba(37,99,235,0.28)");
      halo.addColorStop(0.7, "rgba(0,229,255,0.07)");
      halo.addColorStop(1, "rgba(3,11,28,0)");
      ctx.fillStyle = halo;
      ctx.fillRect(0, 0, size, size);
      // latitude and longitude lines
      ctx.lineWidth = 1;
      for (let lat = -60; lat <= 60; lat += 30) {
        ctx.beginPath();
        for (let lon = 0; lon <= 360; lon += 6) {
          const p = project(toVec(lat, lon));
          const px = c + p.x * R, py = c - p.y * R;
          if (lon === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
        }
        ctx.strokeStyle = "rgba(0,229,255,0.12)";
        ctx.stroke();
      }
      for (let lon = 0; lon < 180; lon += 30) {
        ctx.beginPath();
        for (let lat = -90; lat <= 90; lat += 6) {
          const p = project(toVec(lat, lon));
          const px = c + p.x * R, py = c - p.y * R;
          if (lat === -90) ctx.moveTo(px, py); else ctx.lineTo(px, py);
        }
        ctx.strokeStyle = "rgba(0,229,255,0.1)";
        ctx.stroke();
      }
      const pts = nodes.map(project);
      for (const [i, j] of edges) {
        const a = pts[i], b = pts[j];
        const depth = (a.z + b.z) / 2;
        if (depth < -0.15) continue;
        ctx.strokeStyle = `rgba(96,165,250,${0.1 + 0.4 * Math.max(0, depth)})`;
        ctx.beginPath();
        ctx.moveTo(c + a.x * R, c - a.y * R);
        ctx.lineTo(c + b.x * R, c - b.y * R);
        ctx.stroke();
      }
      for (let i = 0; i < pts.length; i++) {
        const p = pts[i];
        if (p.z < -0.1) continue;
        const anchor = i >= N ? i - N : -1;
        const px = c + p.x * R, py = c - p.y * R;
        if (anchor >= 0) {
          const col = GLOBE_MODULES[anchor].colour;
          const on = hi.current === anchor;
          const pulse = reduce ? 1 : 1 + 0.25 * Math.sin(t / 500 + anchor);
          ctx.fillStyle = `rgba(${col},${on ? 0.28 : 0.14})`;
          ctx.beginPath();
          ctx.arc(px, py, (on ? 16 : 11) * pulse, 0, Math.PI * 2);
          ctx.fill();
          ctx.fillStyle = `rgba(${col},1)`;
          ctx.beginPath();
          ctx.arc(px, py, on ? 4.5 : 3.5, 0, Math.PI * 2);
          ctx.fill();
        } else {
          ctx.fillStyle = `rgba(165,243,252,${0.25 + 0.6 * Math.max(0, p.z)})`;
          ctx.beginPath();
          ctx.arc(px, py, 1.4 + p.z, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    };
    const frame = (t: number) => {
      if (visible && !document.hidden) {
        angle += Math.min(t - last, 50) * 0.00007;
        draw(t);
      }
      last = t;
      raf = requestAnimationFrame(frame);
    };
    resize();
    draw(0);
    const io = new IntersectionObserver((entries) => { visible = entries.some((e) => e.isIntersecting); });
    io.observe(el);
    window.addEventListener("resize", resize);
    if (!reduce) raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
      window.removeEventListener("resize", resize);
    };
  }, []);

  return <canvas ref={canvas} role="img" aria-label="A slowly rotating globe of connected data nodes linking the four intelligence modules" className="absolute inset-0 h-full w-full" />;
}
