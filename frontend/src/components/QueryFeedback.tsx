export function QueryLoading({ children = 'Loading…' }: { children?: React.ReactNode }) {
  return <p role="status" className="text-ink-dim text-sm">{children}</p>
}

export function QueryError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" className="text-sm text-ink-mid">
      <p>{message}</p>
      <button type="button" onClick={onRetry} className="mt-2 rounded-lg border border-surface-line px-3 py-2 hover:bg-surface-raise">
        Try again
      </button>
    </div>
  )
}
