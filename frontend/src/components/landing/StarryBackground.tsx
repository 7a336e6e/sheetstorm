"use client"

import { useEffect, useRef, useState } from 'react'

// Deterministic pseudo-random to avoid hydration mismatch
function hash(seed: number): number {
  const x = Math.sin(seed * 127.1 + 311.7) * 43758.5453
  return x - Math.floor(x)
}

const STAR_COUNT = 200

const staticStars = Array.from({ length: STAR_COUNT }, (_, i) => ({
  x: hash(i * 3 + 1) * 100,
  y: hash(i * 3 + 2) * 100,
  size: 0.5 + hash(i * 3 + 3) * 1.5,
  opacity: 0.1 + hash(i * 7 + 5) * 0.6,
  twinkles: i % 5 === 0,
  animDuration: 3 + hash(i * 7 + 6) * 5,
  animDelay: hash(i * 7 + 7) * 6,
}))

interface ShootingStar {
  id: number
  top: string
  left: string
  angle: number
  duration: number
}

export function StarryBackground() {
  const [shootingStars, setShootingStars] = useState<ShootingStar[]>([])
  const idRef = useRef(0)

  useEffect(() => {
    let timeout: ReturnType<typeof setTimeout>

    const spawn = () => {
      const id = idRef.current++
      const star: ShootingStar = {
        id,
        top: `${5 + Math.random() * 40}%`,
        left: `${5 + Math.random() * 60}%`,
        angle: 25 + Math.random() * 30,
        duration: 0.6 + Math.random() * 0.5,
      }

      setShootingStars(prev => [...prev.slice(-3), star])

      setTimeout(() => {
        setShootingStars(prev => prev.filter(s => s.id !== id))
      }, (star.duration + 0.5) * 1000)

      timeout = setTimeout(spawn, 4000 + Math.random() * 8000)
    }

    timeout = setTimeout(spawn, 2000 + Math.random() * 2000)

    return () => clearTimeout(timeout)
  }, [])

  return (
    <div className="fixed inset-0 z-0 overflow-hidden pointer-events-none">
      {/* Sky gradient */}
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse at 50% 0%, hsl(240 15% 14%) 0%, hsl(240 6% 9%) 50%, hsl(240 8% 5%) 100%)',
        }}
      />

      {/* Static stars */}
      {staticStars.map((star, i) => (
        <div
          key={i}
          className={`absolute rounded-full bg-white${star.twinkles ? ' animate-twinkle' : ''}`}
          style={{
            left: `${star.x}%`,
            top: `${star.y}%`,
            width: star.size,
            height: star.size,
            opacity: star.opacity,
            ...(star.twinkles
              ? {
                  animationDuration: `${star.animDuration}s`,
                  animationDelay: `${star.animDelay}s`,
                }
              : {}),
          }}
        />
      ))}

      {/* Shooting stars */}
      {shootingStars.map(star => (
        <div
          key={star.id}
          className="absolute"
          style={{
            top: star.top,
            left: star.left,
            transform: `rotate(${star.angle}deg)`,
          }}
        >
          <div
            className="animate-shooting-star"
            style={{
              width: 100,
              height: 1.5,
              borderRadius: 999,
              background:
                'linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.3) 30%, rgba(255,255,255,0.8) 80%, white 100%)',
              boxShadow: '0 0 6px 1px rgba(255,255,255,0.15)',
              transformOrigin: 'right center',
              animationDuration: `${star.duration}s`,
            }}
          />
        </div>
      ))}

      {/* Subtle nebula glow */}
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse at 70% 20%, rgba(99,102,241,0.04) 0%, transparent 50%), radial-gradient(ellipse at 20% 80%, rgba(59,130,246,0.03) 0%, transparent 50%)',
        }}
      />
    </div>
  )
}
