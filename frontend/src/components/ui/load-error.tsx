import { Button } from "@/components/ui/button";

export function LoadError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="panel load-error" role="alert">
      <p>{message}</p>
      {onRetry ? (
        <Button type="button" variant="secondary" onClick={onRetry}>
          Попробовать снова
        </Button>
      ) : null}
    </div>
  );
}
