import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
    GlassTable,
} from '@/components/ui/table'
import { Input } from '@/components/ui/input'
import { CheckCircle2, AlertCircle, ArrowLeft, Loader2 } from 'lucide-react'
import {
    ParseResponse,
    ColumnMapping,
    ParsedSheet,
    EntityType,
    ENTITY_FIELDS
} from './types'

interface PreviewStepProps {
    parsedData: ParseResponse
    mapping: ColumnMapping
    onBack: () => void
    onSubmit: (data: Record<EntityType, any[]>) => Promise<void>
}

export function PreviewStep({ parsedData, mapping, onBack, onSubmit }: PreviewStepProps) {
    const [data, setData] = useState<Record<EntityType, any[]>>({
        timeline_events: [],
        hosts: [],
        accounts: [],
        network_iocs: [],
        host_iocs: [],
        malware: []
    })
    const [activeTab, setActiveTab] = useState<EntityType>('timeline_events')
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [errors, setErrors] = useState<Record<string, number>>({})

    useEffect(() => {
        // Transform data based on mapping
        const newData: Record<EntityType, any[]> = {
            timeline_events: [],
            hosts: [],
            accounts: [],
            network_iocs: [],
            host_iocs: [],
            malware: []
        }

        parsedData.sheets.forEach(sheet => {
            const sheetMapping = mapping[sheet.name]
            if (!sheetMapping) return

            const entityType = sheetMapping.targetEntity
            const fieldMap = sheetMapping.fieldMapping

            sheet.rows.forEach(row => {
                const item: any = {}
                let hasMappedData = false

                Object.entries(fieldMap).forEach(([excelHeader, dbField]) => {
                    if (row[excelHeader] !== undefined && row[excelHeader] !== null) {
                        item[dbField] = row[excelHeader]
                        hasMappedData = true
                    }
                })

                if (hasMappedData) {
                    newData[entityType].push(item)
                }
            })
        })

        setData(newData)

        // Set active tab to first non-empty entity
        const firstNonEmpty = Object.keys(newData).find(k => newData[k as EntityType].length > 0)
        if (firstNonEmpty) setActiveTab(firstNonEmpty as EntityType)

    }, [parsedData, mapping])

    // Validation logic
    useEffect(() => {
        const newErrors: Record<string, number> = {}

        Object.entries(data).forEach(([entity, items]) => {
            const fields = ENTITY_FIELDS[entity as EntityType]
            const requiredFields = fields.filter(f => f.required).map(f => f.value)

            let errorCount = 0
            items.forEach(item => {
                const missing = requiredFields.some(req => !item[req])
                if (missing) errorCount++
            })

            if (errorCount > 0) newErrors[entity] = errorCount
        })

        setErrors(newErrors)
    }, [data])

    const handleValueChange = (entity: EntityType, index: number, field: string, value: string) => {
        setData(prev => {
            const newList = [...prev[entity]]
            newList[index] = { ...newList[index], [field]: value }
            return { ...prev, [entity]: newList }
        })
    }

    const handleSubmit = async () => {
        setIsSubmitting(true)
        try {
            await onSubmit(data)
        } finally {
            setIsSubmitting(false)
        }
    }

    const hasCriticalErrors = Object.values(errors).reduce((a, b) => a + b, 0) > 0
    const totalItems = Object.values(data).reduce((a, b) => a + b.length, 0)

    return (
        <div className="space-y-6">
            <div className="flex items-center gap-4 p-4 bg-white/5 rounded-lg border border-white/10">
                <div className="flex-1">
                    <h3 className="font-medium text-lg">Ready to Import {totalItems} items</h3>
                    <p className="text-sm text-muted-foreground">
                        Review the data below. You can edit values directly in the grid.
                    </p>
                </div>
                {hasCriticalErrors && (
                    <div className="flex items-center gap-2 text-red-400 bg-red-500/10 px-4 py-2 rounded-lg border border-red-500/20">
                        <AlertCircle className="h-5 w-5" />
                        <span className="font-medium">Missing required fields</span>
                    </div>
                )}
            </div>

            <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as EntityType)}>
                <TabsList className="flex-wrap h-auto gap-y-2 justify-start">
                    {Object.entries(data).map(([entity, items]) => {
                        if (items.length === 0) return null
                        return (
                            <TabsTrigger key={entity} value={entity} className="gap-2">
                                {ENTITY_FIELDS[entity as EntityType][0].label.split(' ')[0]} {/* Approximate Label */}
                                <span className="bg-white/10 px-1.5 rounded text-xs">{items.length}</span>
                                {errors[entity] > 0 && <span className="text-red-400 text-xs">({errors[entity]} errors)</span>}
                            </TabsTrigger>
                        )
                    })}
                </TabsList>

                {Object.entries(data).map(([entity, items]) => {
                    if (items.length === 0) return null
                    const fields = ENTITY_FIELDS[entity as EntityType]

                    return (
                        <TabsContent key={entity} value={entity}>
                            <GlassTable>
                                <Table>
                                    <TableHeader>
                                        <TableRow>
                                            <TableHead className="w-12">#</TableHead>
                                            {fields.map(f => (
                                                <TableHead key={f.value} className={f.required ? 'text-amber-400' : ''}>
                                                    {f.label} {f.required && '*'}
                                                </TableHead>
                                            ))}
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {items.map((item, idx) => (
                                            <TableRow key={idx}>
                                                <TableCell className="text-muted-foreground">{idx + 1}</TableCell>
                                                {fields.map(f => {
                                                    const isMissing = f.required && !item[f.value]
                                                    return (
                                                        <TableCell key={f.value} className={isMissing ? 'bg-red-500/10' : ''}>
                                                            <Input
                                                                value={item[f.value] || ''}
                                                                onChange={e => handleValueChange(entity as EntityType, idx, f.value, e.target.value)}
                                                                className={`h-8 border-0 bg-transparent focus-visible:bg-black/20 ${isMissing ? 'border-b border-red-500' : ''}`}
                                                                placeholder={isMissing ? 'Required' : ''}
                                                            />
                                                        </TableCell>
                                                    )
                                                })}
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            </GlassTable>
                        </TabsContent>
                    )
                })}
            </Tabs>

            <div className="flex justify-between pt-4 border-t border-white/10">
                <Button variant="ghost" onClick={onBack} disabled={isSubmitting}>
                    <ArrowLeft className="mr-2 h-4 w-4" /> Mapping
                </Button>
                <Button onClick={handleSubmit} disabled={isSubmitting || hasCriticalErrors} loading={isSubmitting}>
                    {isSubmitting ? 'Importing...' : 'Complete Import'} <CheckCircle2 className="ml-2 h-4 w-4" />
                </Button>
            </div>
        </div>
    )
}
