/** Keep in sync with backend `Settings.allowed_upload_extensions`. */
export const UPLOAD_ACCEPT =
  '.cfg,.dat,.cff,.hdr,.inf,.csv,.txt,.xml,.json,.pdf,.zip,' +
  '.set,.rdb,.xrio,.rio,.eve,.cev,.log,.dz5,.dex5,.d5z,.pcmi,.pcmp';

export const UPLOAD_ACCEPT_HINT =
  'COMTRADE: .cfg .dat .cff .hdr .inf · Settings/SOE: .csv .txt .xml .json .set .xrio .rio .eve .log · ' +
  'Vendor: .rdb .cev .dz5 .dex5 .d5z .pcmi .pcmp · .pdf .zip (ZIP / packages auto-extract when possible)';
