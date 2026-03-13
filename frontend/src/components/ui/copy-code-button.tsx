"use client"

import { useState, useEffect } from "react"
import { Check, Copy } from "lucide-react"

interface CopyCodeProps {
  code: string
}

export function CopyCode({ code }: CopyCodeProps) {
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (copied) {
      const timer = setTimeout(() => {
        setCopied(false)
      }, 2000)
      return () => clearTimeout(timer)
    }
  }, [copied])

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code)
    } catch {
      const textArea = document.createElement("textarea")
      textArea.value = code
      textArea.style.position = "fixed"
      textArea.style.left = "-9999px"
      textArea.style.top = "-9999px"
      document.body.appendChild(textArea)
      textArea.focus()
      textArea.select()
      document.execCommand("copy")
      document.body.removeChild(textArea)
    }
    setCopied(true)
  }

  return (
    <button
      onClick={handleCopy}
      className="group relative p-2 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 hover:border-white/20 text-slate-400 hover:text-white transition-all duration-200"
      title={copied ? "Copied!" : "Copy to clipboard"}
    >
      {copied ? (
        <Check className="h-4 w-4 text-cyan-400" />
      ) : (
        <Copy className="h-4 w-4" />
      )}
    </button>
  )
}
