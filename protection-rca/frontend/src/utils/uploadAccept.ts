/** Keep in sync with backend `Settings.allowed_upload_extensions`. */
export const UPLOAD_ACCEPT =
  '.cfg,.dat,.cff,.hdr,.inf,.csv,.txt,.xml,.json,.pdf,.docx,.doc,.zip,' +
  '.set,.rdb,.xrio,.rio,.eve,.cev,.log,.dz5,.dex,.dex5,.d5z,.pcmi,.pcmp,' +
  '.dg4,.xmlu,.reh,.rev';

export const UPLOAD_ACCEPT_HINT =
  'COMTRADE: .cfg .dat .cff .hdr .inf · Settings/SOE: .csv .txt .xml .json .set .xrio .rio .eve .log · ' +
  'Docs: .pdf .docx .doc (text extract → settings/events) · ' +
  'Vendor: .rdb .cev .dz5 .dex .dex5 .d5z .pcmi .pcmp .dg4 .xmlu · .zip (auto-extract when possible)';

/** True when filenames include a usable COMTRADE record (CFG+DAT or CFF). */
export function hasComtradePackage(names: Iterable<string>): boolean {
  const lower = Array.from(names, (n) => String(n || '').toLowerCase());
  const hasCff = lower.some((n) => n.endsWith('.cff'));
  const hasCfg = lower.some((n) => n.endsWith('.cfg'));
  const hasDat = lower.some((n) => n.endsWith('.dat'));
  return hasCff || (hasCfg && hasDat);
}

export function looksLikeSettingsFile(name: string): boolean {
  const n = name.toLowerCase();
  return (
    n.includes('setting') ||
    n.includes('relay') ||
    n.endsWith('.set') ||
    n.endsWith('.xrio') ||
    n.endsWith('.rio') ||
    ((n.endsWith('.pdf') || n.endsWith('.docx') || n.endsWith('.doc')) &&
      (n.includes('setting') || n.includes('param') || n.includes('relay'))) ||
    (n.endsWith('.json') && (n.includes('param') || n.includes('relay')))
  );
}
