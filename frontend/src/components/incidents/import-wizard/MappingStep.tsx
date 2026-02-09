import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
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
import { AlertCircle, ArrowRight, ArrowLeft } from 'lucide-react'
import {
    ParseResponse,
    ColumnMapping,
    ParsedSheet,
    EntityType,
    ENTITY_FIELDS
} from './types'

interface MappingStepProps {
    parsedData: ParseResponse
    onMappingComplete: (mapping: ColumnMapping) => void
    onBack: () => void
}

export function MappingStep({ parsedData, onMappingComplete, onBack }: MappingStepProps) {
    const [activeSheet, setActiveSheet] = useState(parsedData.sheets[0]?.name || '')
    const [mapping, setMapping] = useState<ColumnMapping>({})

    // Initialize mapping structure
    useEffect(() => {
        const initialMapping: ColumnMapping = {}
        parsedData.sheets.forEach(sheet => {
            initialMapping[sheet.name] = {
                targetEntity: 'timeline_events', // Default
                fieldMapping: {}
            }

            // Auto-map based on name similarity
            sheet.headers.forEach(header => {
                const headerLower = header.toLowerCase().replace(/_/g, '').replace(/ /g, '')

                // Find best match in default entity fields
                const fields = ENTITY_FIELDS['timeline_events']
                const match = fields.find(f => {
                    const fieldLower = f.value.toLowerCase().replace(/_/g, '')
                    return headerLower.includes(fieldLower) || fieldLower.includes(headerLower)
                })

                if (match) {
                    initialMapping[sheet.name].fieldMapping[header] = match.value
                }
            })
        })
        setMapping(prev => Object.keys(prev).length === 0 ? initialMapping : prev)
    }, [parsedData])

    const handleEntityChange = (sheetName: string, entity: EntityType) => {
        setMapping(prev => {
            const newMapping = { ...prev }
            newMapping[sheetName] = {
                targetEntity: entity,
                fieldMapping: {} // Reset mapping when entity changes
            }

            // Re-run auto-map for new entity
            const sheet = parsedData.sheets.find(s => s.name === sheetName)
            if (sheet) {
                const fields = ENTITY_FIELDS[entity]
                sheet.headers.forEach(header => {
                    const headerLower = header.toLowerCase().replace(/_/g, '').replace(/ /g, '')
                    const match = fields.find(f => {
                        const fieldLower = f.value.toLowerCase().replace(/_/g, '')
                        return headerLower.includes(fieldLower) || fieldLower.includes(headerLower)
                    })

                    if (match) {
                        newMapping[sheetName].fieldMapping[header] = match.value
                    }
                })
            }

            return newMapping
        })
    }

    const handleFieldMap = (sheetName: string, header: string, field: string) => {
        setMapping(prev => ({
            ...prev,
            [sheetName]: {
                ...prev[sheetName],
                fieldMapping: {
                    ...prev[sheetName].fieldMapping,
                    [header]: field
                }
            }
        }))
    }

    const handleNext = () => {
        onMappingComplete(mapping)
    }

    const currentSheetData = parsedData.sheets.find(s => s.name === activeSheet)
    const currentMapping = mapping[activeSheet]

    if (!currentSheetData || !currentMapping) return <div>Loading...</div>

    return (
        <div className="space-y-6">
            <Tabs value={activeSheet} onValueChange={setActiveSheet}>
                <div className="flex items-center justify-between mb-4">
                    <TabsList>
                        {parsedData.sheets.map(sheet => (
                            <TabsTrigger key={sheet.name} value={sheet.name}>
                                {sheet.name}
                            </TabsTrigger>
                        ))}
                    </TabsList>
                </div>

                {parsedData.sheets.map(sheet => (
                    <TabsContent key={sheet.name} value={sheet.name} className="space-y-4">
                        <div className="flex items-center gap-4 bg-white/5 p-4 rounded-lg border border-white/10">
                            <span className="text-sm font-medium whitespace-nowrap">Map this sheet to:</span>
                            <Select
                                value={mapping[sheet.name]?.targetEntity}
                                onValueChange={(val: EntityType) => handleEntityChange(sheet.name, val)}
                            >
                                <SelectTrigger className="w-[200px]">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="timeline_events">Timeline Events</SelectItem>
                                    <SelectItem value="hosts">Compromised Hosts</SelectItem>
                                    <SelectItem value="accounts">Compromised Accounts</SelectItem>
                                    <SelectItem value="network_iocs">Network IOCs</SelectItem>
                                    <SelectItem value="host_iocs">Host IOCs</SelectItem>
                                    <SelectItem value="malware">Malware/Tools</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>

                        <GlassTable>
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead className="w-[40%]">Excel Column</TableHead>
                                        <TableHead className="w-[10%] text-center"><ArrowRight className="h-4 w-4 mx-auto" /></TableHead>
                                        <TableHead className="w-[40%]">Database Field</TableHead>
                                        <TableHead className="w-[10%]">Sample Value</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {sheet.headers.map(header => {
                                        const mappedField = mapping[sheet.name]?.fieldMapping[header]
                                        const targetFields = ENTITY_FIELDS[mapping[sheet.name]?.targetEntity]

                                        return (
                                            <TableRow key={header}>
                                                <TableCell className="font-medium">{header}</TableCell>
                                                <TableCell className="text-center text-muted-foreground"><ArrowRight className="h-4 w-4 mx-auto" /></TableCell>
                                                <TableCell>
                                                    <Select
                                                        value={mappedField || 'ignore'}
                                                        onValueChange={(val) => handleFieldMap(sheet.name, header, val === 'ignore' ? '' : val)}
                                                    >
                                                        <SelectTrigger className={mappedField ? 'bg-cyan-500/10 border-cyan-500/50' : ''}>
                                                            <SelectValue placeholder="Ignore column" />
                                                        </SelectTrigger>
                                                        <SelectContent>
                                                            <SelectItem value="ignore">-- Ignore --</SelectItem>
                                                            {targetFields.map(f => (
                                                                <SelectItem key={f.value} value={f.value}>
                                                                    {f.label} {f.required && '*'}
                                                                </SelectItem>
                                                            ))}
                                                        </SelectContent>
                                                    </Select>
                                                </TableCell>
                                                <TableCell className="text-muted-foreground text-xs font-mono truncate max-w-[150px]">
                                                    {String(sheet.rows[0]?.[header] || '')}
                                                </TableCell>
                                            </TableRow>
                                        )
                                    })}
                                </TableBody>
                            </Table>
                        </GlassTable>
                    </TabsContent>
                ))}
            </Tabs>

            <div className="flex justify-between pt-4 border-t border-white/10">
                <Button variant="ghost" onClick={onBack}>
                    <ArrowLeft className="mr-2 h-4 w-4" /> Upload
                </Button>
                <Button onClick={handleNext}>
                    Preview Data <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
            </div>
        </div>
    )
}
