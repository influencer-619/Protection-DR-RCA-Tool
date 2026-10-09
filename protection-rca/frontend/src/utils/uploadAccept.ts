/** Keep in sync with backend `Settings.allowed_upload_extensions`. */
export const UPLOAD_ACCEPT =
  '.cfg,.dat,.cff,.hdr,.inf,.csv,.txt,.xml,.json,.pdf,.docx,.doc,.zip,' +
  '.set,.rdb,.xrio,.rio,.eve,.cev,.log,.dz5,.dex,.dex5,.d5z,.pcmi,.pcmp,' +
  '.dg4,.xmlu,.reh,.rev';

export const UPLOAD_ACCEPT_HINT =
  'COMTRADE: .cfg .dat .cff .hdr .inf · Settings/SOE: .csv .txt .xml .json .set .xrio .rio .eve .log · ' +
  'Docs: .pdf .docx .doc (text extract → settings/events) · ' +
  'Vendor: .rdb .cev .dz5 .dex .dex5 .d5z .pcmi .pcmp .dg4 .xmlu · .zip (auto-extract when possible)';

const ALLOWED_EXT = new Set(
  UPLOAD_ACCEPT.split(',')
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean),
);

/** True when filename extension is in the upload allow-list. */
export function isAllowedUploadName(name: string): boolean {
  const n = String(name || '').toLowerCase();
  const dot = n.lastIndexOf('.');
  if (dot < 0) return false;
  return ALLOWED_EXT.has(n.slice(dot));
}

export function filterAllowedUploads(files: Iterable<File>): File[] {
  return Array.from(files).filter((f) => isAllowedUploadName(f.name));
}

/** True when filenames include a usable COMTRADE record (CFG+DAT or CFF). */
export function hasComtradePackage(names: Iterable<string>): boolean {
  const lower = Array.from(names, (n) => String(n || '').toLowerCase());
  const hasCff = lower.some((n) => n.endsWith('.cff'));
  const hasCfg = lower.some((n) => n.endsWith('.cfg'));
  const hasDat = lower.some((n) => n.endsWith('.dat'));
  return hasCff || (hasCfg && hasDat);
}

type FsEntry = {
  isFile: boolean;
  isDirectory: boolean;
  name: string;
  file: (ok: (f: File) => void, err?: (e: DOMException) => void) => void;
  createReader: () => {
    readEntries: (
      ok: (entries: FsEntry[]) => void,
      err?: (e: DOMException) => void,
    ) => void;
  };
};

function asFsEntry(entry: FileSystemEntry | null | undefined): FsEntry | null {
  if (!entry) return null;
  return entry as unknown as FsEntry;
}

async function walkFsEntry(entry: FsEntry, out: File[]): Promise<void> {
  if (entry.isFile) {
    const file = await new Promise<File | null>((resolve) => {
      entry.file(
        (f) => resolve(f),
        () => resolve(null),
      );
    });
    if (file && isAllowedUploadName(file.name)) out.push(file);
    return;
  }
  if (!entry.isDirectory) return;
  const reader = entry.createReader();
  const readBatch = (): Promise<FsEntry[]> =>
    new Promise((resolve) => {
      reader.readEntries(
        (ents) =>
          resolve(
            (ents as unknown as FileSystemEntry[])
              .map((e) => asFsEntry(e))
              .filter((e): e is FsEntry => e != null),
          ),
        () => resolve([]),
      );
    });
  // readEntries may return partial batches — keep reading until empty
  for (;;) {
    const batch = await readBatch();
    if (!batch.length) break;
    for (const child of batch) {
      await walkFsEntry(child, out);
    }
  }
}

/**
 * Collect files from a drag-drop (including whole folders).
 * Plain `dataTransfer.files` is often empty when a directory is dropped.
 */
export async function collectDroppedFiles(dt: DataTransfer): Promise<File[]> {
  const out: File[] = [];
  const items = dt.items;
  if (items && items.length > 0) {
    const entries: FsEntry[] = [];
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.kind !== 'file') continue;
      const raw = (
        item as DataTransferItem & { webkitGetAsEntry?: () => FileSystemEntry | null }
      ).webkitGetAsEntry?.();
      const entry = asFsEntry(raw);
      if (entry) entries.push(entry);
      else {
        const f = item.getAsFile();
        if (f && isAllowedUploadName(f.name)) out.push(f);
      }
    }
    if (entries.length) {
      for (const entry of entries) {
        await walkFsEntry(entry, out);
      }
      return out;
    }
  }
  return filterAllowedUploads(Array.from(dt.files || []));
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
