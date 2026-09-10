import styles from './Skeleton.module.css';

interface Props {
  rows?: number;
  height?: number;
  label?: string;
}

export function Skeleton({ rows = 4, height = 14, label }: Props) {
  return (
    <div className={styles.wrap} aria-busy="true" aria-label={label || 'Loading'}>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className={styles.bar}
          style={{ height, width: `${72 + ((i * 11) % 28)}%` }}
        />
      ))}
    </div>
  );
}
