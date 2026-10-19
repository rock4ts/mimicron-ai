import Link from "next/link";

export function PublicShell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <a className="skip-link" href="#main-content">
        Перейти к содержимому
      </a>
      <header className="site-header">
        <Link className="brand" href="/" aria-label="Главная Mimicron">
          <span className="brand-mark" aria-hidden="true">
            M
          </span>
          <span>Mimicron</span>
        </Link>
      </header>
      <div id="main-content" tabIndex={-1}>
        {children}
      </div>
    </>
  );
}
