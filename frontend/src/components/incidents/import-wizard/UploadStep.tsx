import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Upload, Loader2, AlertCircle } from 'lucide-react'
import api from '@/lib/api'
import { ParseResponse } from './types'

interface UploadStepProps {
    incidentId: string
    onParsed: (data: ParseResponse) => void
}

export function UploadStep({ incidentId, onParsed }: UploadStepProps) {
    const [isUploading, setIsUploading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const handleFileChange = async (file: File) => {
        if (!file) return
        setIsUploading(true)
        setError(null)

        const formData = new FormData()
        formData.append('file', file)

        try {
            const data = await api.uploadFile<ParseResponse>(`/incidents/${incidentId}/import/parse`, formData)
            onParsed(data)
        } catch (err: any) {
            console.error('Parse failed:', err)
            setError(err.response?.data?.message || 'Failed to parse file. Please ensure it is a valid Excel file.')
        } finally {
            setIsUploading(false)
        }
    }

    return (
        <div className="space-y-4">
            <div
                className="border-2 border-dashed border-white/10 rounded-xl p-12 text-center hover:border-white/20 transition-colors cursor-pointer"
                onClick={() => document.getElementById('wizard-upload')?.click()}
            >
                {isUploading ? (
                    <div className="space-y-3">
                        <Loader2 className="h-10 w-10 mx-auto animate-spin text-cyan-400" />
                        <p className="text-muted-foreground">Parsing Excel file...</p>
                    </div>
                ) : (
                    <div className="space-y-3">
                        <Upload className="h-10 w-10 mx-auto text-muted-foreground" />
                        <h3 className="text-lg font-medium">Upload Excel File</h3>
                        <p className="text-muted-foreground text-sm">Drag and drop or click to select</p>
                    </div>
                )}
                <input
                    type="file"
                    accept=".xlsx,.xls"
                    className="hidden"
                    id="wizard-upload"
                    disabled={isUploading}
                    onChange={e => e.target.files?.[0] && handleFileChange(e.target.files[0])}
                />
            </div>

            {error && (
                <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 flex items-center gap-2 text-red-400 text-sm">
                    <AlertCircle className="h-4 w-4" />
                    {error}
                </div>
            )}

            <div className="flex justify-end pt-4">
                {/* Placeholder for alignment */}
            </div>
        </div>
    )
}
