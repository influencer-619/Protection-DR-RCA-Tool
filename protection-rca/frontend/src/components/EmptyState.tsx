import { Link } from 'react-router-dom';
import styles from './EmptyState.module.css';

interface Action {
  label: string;
  to?: string;
  onClick?: () => void;
  primary?: boolean;
  disabled?: boolean;
}

interface Props {
  title: string;
  description: string;
  actions?: Action[];
  tips?: string[];
}

export function EmptyState({ title, description, actions = [], tips }: Props) {
  return (
    <div className={styles.wrap}>
      <h2 className={styles.title}>{title}</h2>
      <p className={styles.desc}>{description}</p>
      {tips && tips.length > 0 && (
        <ul className={styles.tips}>
          {tips.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      )}
      {actions.length > 0 && (
        <div className={styles.actions}>
          {actions.map((a) =>
            a.to ? (
              <Link
                key={a.label}
                to={a.to}
                className={a.primary ? 'btn btn-primary' : 'btn'}
              >
                {a.label}
              </Link>
            ) : (
              <button
                key={a.label}
                type="button"
                className={a.primary ? 'btn btn-primary' : 'btn'}
                disabled={a.disabled}
                onClick={a.onClick}
              >
                {a.label}
              </button>
            ),
          )}
        </div>
      )}
    </div>
  );
}
