"use client"

import React from 'react'
import Link from 'next/link'
import { ArrowRight, Github, BookOpen, Star } from 'lucide-react'

const menuItems = [
  {
    title: 'Get Started',
    icon: <ArrowRight className="h-5 w-5" />,
    href: '/register',
    gradientFrom: '#06b6d4',
    gradientTo: '#3b82f6',
  },
  {
    title: 'GitHub',
    icon: <Github className="h-5 w-5" />,
    href: 'https://github.com/7a336e6e/sheetstorm',
    external: true,
    gradientFrom: '#a855f7',
    gradientTo: '#ec4899',
  },
  {
    title: 'Docs',
    icon: <BookOpen className="h-5 w-5" />,
    href: '#features',
    gradientFrom: '#f97316',
    gradientTo: '#ef4444',
  },
  {
    title: 'Star',
    icon: <Star className="h-5 w-5" />,
    href: 'https://github.com/7a336e6e/sheetstorm',
    external: true,
    gradientFrom: '#facc15',
    gradientTo: '#f59e0b',
  },
]

export function GradientMenu() {
  return (
    <ul className="flex flex-wrap justify-center gap-4 sm:gap-6">
      {menuItems.map(({ title, icon, href, external, gradientFrom, gradientTo }) => {
        const style = {
          '--gradient-from': gradientFrom,
          '--gradient-to': gradientTo,
        } as React.CSSProperties

        const inner = (
          <li
            style={style}
            className="relative w-[56px] h-[56px] bg-white/10 backdrop-blur-sm shadow-lg shadow-black/20 rounded-full flex items-center justify-center transition-all duration-500 hover:w-[170px] hover:shadow-none group cursor-pointer border border-white/10 hover:border-transparent"
          >
            {/* Gradient background on hover */}
            <span className="absolute inset-0 rounded-full bg-[linear-gradient(135deg,var(--gradient-from),var(--gradient-to))] opacity-0 transition-all duration-500 group-hover:opacity-100" />
            {/* Blur glow */}
            <span className="absolute top-[10px] inset-x-0 h-full rounded-full bg-[linear-gradient(135deg,var(--gradient-from),var(--gradient-to))] blur-[15px] opacity-0 -z-10 transition-all duration-500 group-hover:opacity-40" />

            {/* Icon */}
            <span className="relative z-10 transition-all duration-500 group-hover:scale-0 delay-0">
              <span className="text-slate-400 group-hover:text-white">{icon}</span>
            </span>

            {/* Title */}
            <span className="absolute text-white uppercase tracking-wide text-sm font-semibold transition-all duration-500 scale-0 group-hover:scale-100 delay-150">
              {title}
            </span>
          </li>
        )

        if (external) {
          return (
            <a key={title} href={href} target="_blank" rel="noopener noreferrer">
              {inner}
            </a>
          )
        }
        return (
          <Link key={title} href={href}>
            {inner}
          </Link>
        )
      })}
    </ul>
  )
}
