interface Props {
  title: string;
  subtitle?: string;
  /** @deprecated Combined RCA removed — ignored */
  event?: unknown;
  cascadeTitle?: string;
  lineTitle?: string;
  cascadeSubtitle?: string;
  lineSubtitle?: string;
}

/** Simple event-page H1/subtitle (Combined RCA product removed). */
export function CombinedPageHeader({ title, subtitle }: Props) {
  return (
    <div className="page-header" style={{ padding: 0 }}>
      <div>
        <h1 style={{ fontSize: '1.1rem' }}>{title}</h1>
        {subtitle ? <p className="subtitle">{subtitle}</p> : null}
      </div>
    </div>
  );
}
