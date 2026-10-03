import { formatFindingValue } from '@/utils/findingValue';

/** Clean evidence summary lines that still carry raw Expected/Observed dumps. */
export function formatEvidenceSummary(raw: string | null | undefined): string {
  if (!raw) return '';
  let text = raw.trim();
  if (!text) return '';

  text = text.replace(/\bstatus\s*=\s*/gi, 'Status: ');

  // "… | Expected: … Observed: …"  or  "Expected: … · Observed: …"
  const expectedMatch = text.match(/Expected:\s*(.+?)(?:\s*(?:·|\|)?\s*Observed:|$)/is);
  const observedMatch = text.match(/Observed:\s*(.+)$/is);

  if (expectedMatch || observedMatch) {
    const head = text
      .replace(/\s*\|\s*Expected:[\s\S]*$/i, '')
      .replace(/\s*Expected:[\s\S]*$/i, '')
      .trim();
    const parts: string[] = [];
    if (head) parts.push(head.replace(/^monotonic\s+/i, ''));
    if (expectedMatch?.[1]) {
      parts.push(`Expected: ${formatFindingValue(expectedMatch[1].trim())}`);
    }
    if (observedMatch?.[1]) {
      parts.push(`Observed: ${formatFindingValue(observedMatch[1].trim())}`);
    }
    return parts.join('\n');
  }

  return text;
}
