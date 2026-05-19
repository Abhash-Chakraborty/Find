"use client";

import { useEffect, useRef } from "react";

export default function CursorGlow() {
  const glowRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let mouseX = window.innerWidth / 2;
    let mouseY = window.innerHeight / 2;
    let currentX = mouseX;
    let currentY = mouseY;
    let animationFrame: number;

    const handleMouseMove = (e: MouseEvent) => {
      mouseX = e.clientX;
      mouseY = e.clientY;
    };

    const animate = () => {
      // Smooth interpolation for premium motion
      currentX += (mouseX - currentX) * 0.08;
      currentY += (mouseY - currentY) * 0.08;

      if (glowRef.current) {
        // Center a 220px glow under the cursor
        glowRef.current.style.transform = `translate(${currentX - 110}px, ${
          currentY - 110
        }px)`;
      }

      animationFrame = requestAnimationFrame(animate);
    };

    window.addEventListener("mousemove", handleMouseMove);
    animationFrame = requestAnimationFrame(animate);

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      cancelAnimationFrame(animationFrame);
    };
  }, []);

  return (
    <div
      ref={glowRef}
      className="cursor-glow pointer-events-none fixed left-0 top-0 z-0 h-[220px] w-[220px] rounded-full opacity-70 blur-3xl transition-opacity duration-300"
      style={{
        background:
          "radial-gradient(circle, rgba(120, 255, 200, 0.16) 0%, rgba(120, 220, 255, 0.10) 45%, transparent 75%)",
      }}
    />
  );
}
