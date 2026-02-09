import { useState } from 'react'
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog'
import { UploadStep } from './UploadStep'
import { MappingStep } from './MappingStep'
import { PreviewStep } from './PreviewStep'
import { ParseResponse, ColumnMapping, EntityType } from './types'
import api from '@/lib/api'

interface ImportWizardModalProps {
    isOpen: boolean
    onOpenChange: (open: boolean) => void
    incidentId: string
    onComplete: () => void
}

type WizardStep = 'upload' | 'mapping' | 'preview' | 'success'

export function ImportWizardModal({ isOpen, onOpenChange, incidentId, onComplete }: ImportWizardModalProps) {
    const [step, setStep] = useState<WizardStep>('upload')
    const [parsedData, setParsedData] = useState<ParseResponse | null>(null)
    const [mapping, setMapping] = useState<ColumnMapping>({})
    const [importResults, setImportResults] = useState<any>(null)

    const handleParsed = (data: ParseResponse) => {
        setParsedData(data)
        setStep('mapping')
    }

    const handleMappingComplete = (data: ColumnMapping) => {
        setMapping(data)
        setStep('preview')
    }

    const handleSubmit = async (normalizedData: Record<EntityType, any[]>) => {
        try {
            const res = await api.post<{ results: any }>(`/incidents/${incidentId}/import/submit`, normalizedData)
            setImportResults(res.results)
            setStep('success')
            onComplete()
            setTimeout(() => {
                onOpenChange(false)
                resetWizard()
            }, 2000)
        } catch (error) {
            console.error('Submission failed:', error)
            // Error handling is managed by global toaster or we could redirect to error step
        }
    }

    const resetWizard = () => {
        setStep('upload')
        setParsedData(null)
        setMapping({})
        setImportResults(null)
    }

    return (
        <Dialog open={isOpen} onOpenChange={(open) => {
            onOpenChange(open)
            if (!open) setTimeout(resetWizard, 300)
        }}>
            <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle>
                        {step === 'upload' && 'Import Data'}
                        {step === 'mapping' && 'Map Columns'}
                        {step === 'preview' && 'Review & Fix Data'}
                        {step === 'success' && 'Import Complete!'}
                    </DialogTitle>
                </DialogHeader>

                <div className="mt-4">
                    {step === 'upload' && (
                        <UploadStep incidentId={incidentId} onParsed={handleParsed} />
                    )}

                    {step === 'mapping' && parsedData && (
                        <MappingStep
                            parsedData={parsedData}
                            onMappingComplete={handleMappingComplete}
                            onBack={() => setStep('upload')}
                        />
                    )}

                    {step === 'preview' && parsedData && (
                        <PreviewStep
                            parsedData={parsedData}
                            mapping={mapping}
                            onBack={() => setStep('mapping')}
                            onSubmit={handleSubmit}
                        />
                    )}

                    {step === 'success' && (
                        <div className="text-center py-12 space-y-4">
                            <div className="w-16 h-16 bg-green-500/20 text-green-400 rounded-full flex items-center justify-center mx-auto">
                                <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                            </div>
                            <h3 className="text-xl font-medium">Data Imported Successfully</h3>
                            {importResults && (
                                <div className="text-sm text-muted-foreground grid grid-cols-2 gap-2 max-w-xs mx-auto text-left">
                                    {Object.entries(importResults).map(([key, count]) => {
                                        if (!count) return null
                                        return <div key={key} className="flex justify-between"><span>{key}:</span> <span>{String(count)}</span></div>
                                    })}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    )
}
