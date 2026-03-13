"use client"

import { cn } from "@/lib/utils"
import React from "react"

interface StarsBackgroundProps {
  className?: string
}

/**
 * CSS-based twinkling static star dots.
 * Works in both light and dark mode via opacity.
 */
export function StarsBackground({ className }: StarsBackgroundProps) {
  return (
    <div className={cn("absolute inset-0 overflow-hidden", className)} aria-hidden="true">
      {/* Subtle radial vignette */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(6,182,212,0.06)_0%,transparent_70%)] dark:bg-[radial-gradient(ellipse_at_center,rgba(6,182,212,0.08)_0%,transparent_70%)]" />
      {/* Twinkling star dots */}
      <div className="stars-layer absolute inset-0" />
      <style jsx>{`
        .stars-layer {
          background-image:
            radial-gradient(1.5px 1.5px at 20px 30px, currentColor, transparent),
            radial-gradient(1px 1px at 40px 70px, currentColor, transparent),
            radial-gradient(1.5px 1.5px at 90px 40px, currentColor, transparent),
            radial-gradient(1px 1px at 130px 80px, currentColor, transparent),
            radial-gradient(1.5px 1.5px at 160px 120px, currentColor, transparent),
            radial-gradient(1px 1px at 50px 160px, currentColor, transparent),
            radial-gradient(1.5px 1.5px at 180px 20px, currentColor, transparent),
            radial-gradient(1px 1px at 110px 140px, currentColor, transparent);
          background-repeat: repeat;
          background-size: 200px 200px;
          animation: stars-twinkle 6s ease-in-out infinite;
          opacity: 0.12;
        }
        :global(.dark) .stars-layer {
          opacity: 0.25;
        }
        @keyframes stars-twinkle {
          0% { opacity: inherit; }
          50% { opacity: 0.06; }
          100% { opacity: inherit; }
        }
        :global(.dark) .stars-layer {
          animation-name: stars-twinkle-dark;
        }
        @keyframes stars-twinkle-dark {
          0% { opacity: 0.25; }
          50% { opacity: 0.4; }
          100% { opacity: 0.25; }
        }
      `}</style>
    </div>
  )
}
