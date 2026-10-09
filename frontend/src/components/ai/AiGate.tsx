"use client"

/**
 * Wraps an AI action button and disables it when the organization's per-TLP
 * AI policy refuses AI for this incident (or the given provider), with a
 * tooltip giving the reason.
 *
 *   <AiGate incidentId={id}>
 *     <Button onClick={summarize}>AI summary</Button>
 *   </AiGate>
 *
 * Pass `provider` when the user picked one, or `availability` when the parent
 * already called `useAiAvailability`. Cosmetic: the server still answers 403
 * `ai_blocked_by_tlp` (mapped by `describeError`).
 */
import * as React from 'react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useAiAvailability, type AiAvailability } from '@/hooks/use-ai-availability'

interface GateableProps {
  disabled?: boolean
  'aria-disabled'?: boolean | 'true' | 'false'
  'aria-describedby'?: string
}

export interface AiGateProps {
  incidentId: string | null | undefined
  provider?: string
  /** Precomputed availability (skips the hook's own lookup). */
  availability?: AiAvailability
  children: React.ReactElement<GateableProps>
}

function GateWithHook({ incidentId, provider, children }: Omit<AiGateProps, 'availability'>) {
  const availability = useAiAvailability(incidentId, { provider })
  return <GateView availability={availability}>{children}</GateView>
}

function GateView({ availability, children }: { availability: AiAvailability; children: React.ReactElement<GateableProps> }) {
  const reasonId = React.useId()
  if (availability.allowed || !availability.reason) return children
  const disabledChild = React.cloneElement(children, {
    disabled: true,
    'aria-disabled': true,
    'aria-describedby': reasonId,
  })
  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          {/* Disabled buttons get no pointer events: the wrapper carries the tooltip and stays focusable. */}
          <span className="inline-flex cursor-not-allowed" tabIndex={0} data-ai-blocked="true">
            {disabledChild}
          </span>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">{availability.reason}</TooltipContent>
      </Tooltip>
      <span id={reasonId} className="sr-only">
        {availability.reason}
      </span>
    </TooltipProvider>
  )
}

export function AiGate({ incidentId, provider, availability, children }: AiGateProps) {
  if (availability) return <GateView availability={availability}>{children}</GateView>
  return (
    <GateWithHook incidentId={incidentId} provider={provider}>
      {children}
    </GateWithHook>
  )
}
