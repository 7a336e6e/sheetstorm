"use client"

import { motion } from 'framer-motion'
import { Github, BookOpen, Scale, Heart, ExternalLink } from 'lucide-react'

interface SocialLink {
  icon: React.ReactNode
  label: string
  href: string
  color: string
}

const links: SocialLink[] = [
  {
    icon: <Github className="h-5 w-5" />,
    label: "GitHub",
    href: "https://github.com/7a336e6e/sheetstorm",
    color: "group-hover:text-white",
  },
  {
    icon: <BookOpen className="h-5 w-5" />,
    label: "Docs",
    href: "#features",
    color: "group-hover:text-cyan-400",
  },
  {
    icon: <Scale className="h-5 w-5" />,
    label: "MIT License",
    href: "https://github.com/7a336e6e/sheetstorm/blob/main/LICENSE",
    color: "group-hover:text-emerald-400",
  },
  {
    icon: <Heart className="h-5 w-5" />,
    label: "Contribute",
    href: "https://github.com/7a336e6e/sheetstorm/issues",
    color: "group-hover:text-rose-400",
  },
]

export function SocialLinks() {
  return (
    <div className="flex items-center gap-1">
      {links.map((link) => (
        <motion.a
          key={link.label}
          href={link.href}
          target={link.href.startsWith("http") ? "_blank" : undefined}
          rel={link.href.startsWith("http") ? "noopener noreferrer" : undefined}
          className="group relative flex items-center gap-2 rounded-full px-3 py-2 text-slate-500 transition-colors hover:text-white"
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.97 }}
        >
          <motion.span
            className="absolute inset-0 rounded-full bg-white/5 opacity-0 transition-opacity group-hover:opacity-100"
          />
          <span className={`relative z-10 transition-colors ${link.color}`}>
            {link.icon}
          </span>
          <span className="relative z-10 text-xs font-medium hidden sm:inline">
            {link.label}
          </span>
          <ExternalLink className="relative z-10 h-3 w-3 opacity-0 group-hover:opacity-50 transition-opacity hidden sm:inline" />
        </motion.a>
      ))}
    </div>
  )
}
