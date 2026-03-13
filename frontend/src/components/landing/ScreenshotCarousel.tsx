"use client"

import { useState, useEffect, useCallback } from 'react'
import Image from 'next/image'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ShowcaseItem {
  title: string
  description: string
  image: string
}

interface ScreenshotCarouselProps {
  items: ShowcaseItem[]
}

export function ScreenshotCarousel({ items }: ScreenshotCarouselProps) {
  const [active, setActive] = useState(0)
  const [isPaused, setIsPaused] = useState(false)
  const mode = 'dark_mode'

  const goTo = useCallback(
    (i: number) => setActive(((i % items.length) + items.length) % items.length),
    [items.length]
  )

  const next = useCallback(() => goTo(active + 1), [active, goTo])
  const prev = useCallback(() => goTo(active - 1), [active, goTo])

  useEffect(() => {
    if (isPaused) return
    const timer = setInterval(next, 6000)
    return () => clearInterval(timer)
  }, [isPaused, next])

  const item = items[active]

  return (
    <div
      className="w-full max-w-5xl mx-auto"
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
    >
      {/* Carousel viewport — fixed 16:9 aspect ratio */}
      <div className="relative rounded-xl overflow-hidden border border-white/[0.08] bg-white/[0.04] group" style={{ aspectRatio: '16 / 9' }}>
        {/* Screenshot — centered within fixed container */}
        <div key={active} className="animate-carousel-fade absolute inset-0 flex items-center justify-center">
          <Image
            src={`/screenshots/${mode}/${item.image}.png`}
            alt={item.title}
            width={1200}
            height={700}
            className="max-w-full max-h-full object-contain"
            priority={active === 0}
          />
        </div>

        {/* Overlay description — bottom gradient */}
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 via-black/50 to-transparent p-6 pt-16">
          <div key={`text-${active}`} className="animate-phase-slide-in">
            <h3 className="text-white text-lg font-semibold mb-1">
              {item.title}
            </h3>
            <p className="text-white/70 text-sm max-w-xl leading-relaxed">
              {item.description}
            </p>
          </div>
        </div>

        {/* Nav arrows */}
        <button
          onClick={prev}
          className={cn(
            'absolute left-3 top-1/2 -translate-y-1/2 p-2 rounded-full',
            'bg-black/40 text-white/80 backdrop-blur-sm',
            'opacity-0 group-hover:opacity-100 transition-opacity duration-200',
            'hover:bg-black/60 hover:text-white',
          )}
          aria-label="Previous screenshot"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>
        <button
          onClick={next}
          className={cn(
            'absolute right-3 top-1/2 -translate-y-1/2 p-2 rounded-full',
            'bg-black/40 text-white/80 backdrop-blur-sm',
            'opacity-0 group-hover:opacity-100 transition-opacity duration-200',
            'hover:bg-black/60 hover:text-white',
          )}
          aria-label="Next screenshot"
        >
          <ChevronRight className="h-5 w-5" />
        </button>
      </div>

      {/* Dot indicators */}
      <div className="flex justify-center gap-1.5 mt-4">
        {items.map((_, i) => (
          <button
            key={i}
            onClick={() => goTo(i)}
            className={cn(
              'h-1.5 rounded-full transition-all duration-300',
              i === active
                ? 'w-6 bg-primary'
                : 'w-1.5 bg-muted-foreground/30 hover:bg-muted-foreground/50'
            )}
            aria-label={`Go to ${items[i].title}`}
          />
        ))}
      </div>
    </div>
  )
}
