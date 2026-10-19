import Link from "next/link";

export function ErrorCard({
  title,
  message,
  actionHref = "/companions",
  actionLabel = "К компаньонам",
}: {
  title: string;
  message: string;
  actionHref?: string;
  actionLabel?: string;
}) {
  return (
    <main className="error-page">
      <section className="panel error-card" role="alert">
        <span className="empty-icon" aria-hidden="true">
          !
        </span>
        <p className="eyebrow">Mimicron</p>
        <h1>{title}</h1>
        <p>{message}</p>
        <Link className="button primary" href={actionHref}>
          {actionLabel}
        </Link>
      </section>
    </main>
  );
}
