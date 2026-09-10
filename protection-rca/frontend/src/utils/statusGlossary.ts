/** In-app glossary for status / DQ labels — no invented measurements. */

export const STATUS_GLOSSARY: Record<string, string> = {
  UPLOADED: 'Files received; analysis not started yet.',
  PARSING: 'COMTRADE / settings files are being parsed.',
  ANALYZING: 'Analysis pipeline is running.',
  AWAITING_REVIEW: 'Analysis finished — engineer review required.',
  REVIEW: 'Event is in engineer review.',
  CLOSED: 'Review complete; event closed.',
  FAILED: 'A pipeline step failed — check COMTRADE / Files and re-run.',
  CONSISTENT: 'Observed behaviour matches verified settings for this check.',
  INCONSISTENT: 'Observed behaviour conflicts with verified settings. Not automatic relay malfunction.',
  UNVERIFIABLE: 'Cannot judge consistency — settings missing, NOT VERIFIED, or data insufficient.',
  DATA_QUALITY_ISSUE: 'Data quality problems limit what can be concluded.',
  CONSISTENT_WITH_WARNINGS: 'Consistent overall, with non-blocking warnings.',
  VALID: 'Record passed validation.',
  VALID_WITH_WARNINGS: 'Usable record with non-fatal validation warnings.',
  INVALID: 'Record failed validation — do not trust derived results.',
  NOT_VALIDATED: 'Validation has not been run yet.',
  PARTIALLY_SUPPORTED: 'Format quirks handled with reduced confidence.',
  SUPPORTED: 'Format fully supported.',
  PENDING: 'Queued / not started.',
  RUNNING: 'In progress.',
  COMPLETED: 'Finished successfully.',
  CANCELLED: 'Cancelled or not asserted.',
  STORED: 'File stored with integrity hash.',
  VALIDATED: 'Validation completed.',
  DRAFT: 'Draft — not final.',
  APPROVED: 'Approved by engineer.',
  REJECTED: 'Rejected by engineer.',
  SUPERSEDED: 'Replaced by a newer version.',
  PROBABLE: 'Likely hypothesis — still verify evidence.',
  CONFIRMED: 'Hypothesis confirmed by engineer or strong evidence.',
  POSSIBLE: 'Plausible but weakly supported.',
  UNLIKELY: 'Weak support / contradicted.',
  INCONCLUSIVE: 'Evidence insufficient for a firm root cause.',
  CLASSIFIED: 'Fault type classified from electrical evidence.',
  UNKNOWN: 'Not determined from available data.',
  ANALYSIS_COMPLETE: 'Analysis finished; primary RCA is CONFIRMED without material warnings.',
  ANALYSIS_COMPLETE_WITH_WARNINGS:
    'Analysis finished, but review warnings (or primary RCA is only PROBABLE).',
  ENGINEER_REVIEW_REQUIRED: 'Human review required before closing.',
  DATA_INSUFFICIENT: 'Not enough verified data for a conclusion.',
  UNSUPPORTED_FORMAT: 'File format not supported or unreadable.',
  NOT_VERIFIED: 'Plant / settings field not confirmed — leave blank rather than guess.',
  NOT_CALCULABLE: 'Quantity cannot be calculated from available channels.',
};

export const DQ_GLOSSARY: Record<string, string> = {
  GOOD: 'Data quality good for engineering use.',
  ACCEPTABLE: 'Usable with minor limitations.',
  WARNING: 'Use with caution — check COMTRADE / channel mapping.',
  POOR: 'Significant quality issues — conclusions may be unreliable.',
  INVALID: 'Data quality invalid — do not base decisions on derived results.',
};

export function explainStatus(status: string): string {
  return STATUS_GLOSSARY[status] ?? `${status.replace(/_/g, ' ')} — see Help → Status glossary.`;
}

export function explainDq(quality: string): string {
  return DQ_GLOSSARY[quality] ?? `Data quality: ${quality}`;
}
