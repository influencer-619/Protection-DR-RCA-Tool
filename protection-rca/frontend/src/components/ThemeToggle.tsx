import { useThemeStore } from '@/stores/themeStore';

export function ThemeToggle({ className, iconOnly }: { className?: string; iconOnly?: boolean }) {
  const theme = useThemeStore((s) => s.theme);
  const toggleTheme = useThemeStore((s) => s.toggleTheme);
  const label = theme === 'light' ? 'Switch to dark theme' : 'Switch to light theme';

  if (iconOnly) {
    return (
      <button type="button" className={className} onClick={toggleTheme} title={label} aria-label={label}>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          {theme === 'light' ? (
            <path d="M20 14.5A8 8 0 019.5 4a8 8 0 1010.5 10.5z" />
          ) : (
            <>
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
            </>
          )}
        </svg>
      </button>
    );
  }

  return (
    <button
      type="button"
      className={className ? `btn btn-sm ${className}` : 'btn btn-sm'}
      onClick={toggleTheme}
      title={label}
      aria-label={label}
    >
      {theme === 'light' ? 'Dark' : 'Light'}
    </button>
  );
}
