"use client"

import React, { useState, useEffect, useCallback } from "react"
import { motion, AnimatePresence } from "framer-motion"
import Image from "next/image"
import { ArrowLeft, ArrowRight } from "lucide-react"
import { cn } from "@/lib/utils"

interface Feature {
  step: string
  title?: string
  content: string
  image: string
}

interface FeatureStepsProps {
  features: Feature[]
  className?: string
  title?: string
  autoPlayInterval?: number
}

export function FeatureSteps({
  features,
  className,
  title = "See It in Action",
  autoPlayInterval = 5000,
}: FeatureStepsProps) {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [direction, setDirection] = useState(0)
  const [isPaused, setIsPaused] = useState(false)

  useEffect(() => {
    if (isPaused) return
    const timer = setInterval(() => {
      setDirection(1)
      setCurrentIndex((prev) => (prev + 1) % features.length)
    }, autoPlayInterval)
    return () => clearInterval(timer)
  }, [isPaused, features.length, autoPlayInterval])

  const next = useCallback(() => {
    setDirection(1)
    setCurrentIndex((prev) => (prev + 1) % features.length)
  }, [features.length])

  const prev = useCallback(() => {
    setDirection(-1)
    setCurrentIndex((prev) => (prev - 1 + features.length) % features.length)
  }, [features.length])

  const goTo = useCallback(
    (index: number) => {
      setDirection(index > currentIndex ? 1 : -1)
      setCurrentIndex(index)
    },
    [currentIndex],
  )

  const slideVariants = {
    enter: (d: number) => ({
      x: d > 0 ? 600 : -600,
      opacity: 0,
      scale: 0.95,
    }),
    center: {
      x: 0,
      opacity: 1,
      scale: 1,
    },
    exit: (d: number) => ({
      x: d < 0 ? 600 : -600,
      opacity: 0,
      scale: 0.95,
    }),
  }

  const current = features[currentIndex]

  return (
    <div className={cn("px-4 md:px-8", className)}>
      <div className="max-w-6xl mx-auto w-full">
        <h2 className="text-3xl md:text-4xl font-bold mb-10 text-center tracking-tight">
          {title}
        </h2>

        {/* Carousel container */}
        <div
          className="relative"
          onMouseEnter={() => setIsPaused(true)}
          onMouseLeave={() => setIsPaused(false)}
        >
          {/* Image area */}
          <div className="relative rounded-xl overflow-hidden border border-white/10 shadow-2xl shadow-cyan-500/10 aspect-[16/9] bg-[#0c1222]">
            <AnimatePresence initial={false} custom={direction} mode="popLayout">
              <motion.div
                key={currentIndex}
                custom={direction}
                variants={slideVariants}
                initial="enter"
                animate="center"
                exit="exit"
                transition={{
                  x: { type: "spring", stiffness: 300, damping: 30 },
                  opacity: { duration: 0.3 },
                  scale: { duration: 0.3 },
                }}
                className="absolute inset-0"
              >
                <Image
                  src={current.image}
                  alt={current.step}
                  fill
                  sizes="(max-width: 768px) 100vw, (max-width: 1200px) 80vw, 1152px"
                  className="object-contain"
                  priority={currentIndex === 0}
                />
              </motion.div>
            </AnimatePresence>



            {/* Caption overlay at bottom */}
            <div className="absolute inset-x-0 bottom-0 z-20 bg-gradient-to-t from-black/80 via-black/40 to-transparent px-6 pb-5 pt-12">
              <AnimatePresence mode="wait">
                <motion.div
                  key={currentIndex}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.25 }}
                >
                  <h3 className="text-lg font-semibold text-white mb-1">{current.step}</h3>
                  <p className="text-sm text-white/70 max-w-2xl">
                    {current.title || current.content}
                  </p>
                </motion.div>
              </AnimatePresence>
            </div>
          </div>

          {/* Navigation: arrows + dots + counter */}
          <div className="flex items-center justify-center gap-4 mt-6">
            <button
              onClick={prev}
              className="p-2 rounded-full bg-white/[0.06] border border-white/10 text-white/50 hover:text-white hover:bg-white/[0.12] transition-all"
              aria-label="Previous screenshot"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <div className="flex gap-2">
              {features.map((_, index) => (
                <button
                  key={index}
                  onClick={() => goTo(index)}
                  className={cn(
                    "h-2 rounded-full transition-all duration-300",
                    index === currentIndex
                      ? "w-8 bg-cyan-400"
                      : "w-2 bg-white/20 hover:bg-white/40",
                  )}
                  aria-label={`Go to slide ${index + 1}`}
                />
              ))}
            </div>
            <span className="text-xs text-slate-500 font-mono tabular-nums">
              {currentIndex + 1}/{features.length}
            </span>
            <button
              onClick={next}
              className="p-2 rounded-full bg-white/[0.06] border border-white/10 text-white/50 hover:text-white hover:bg-white/[0.12] transition-all"
              aria-label="Next screenshot"
            >
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
