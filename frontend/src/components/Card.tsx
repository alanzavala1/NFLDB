import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

type LinkAction = {
  label: string
  to: string
}

type CardProps = {
  title?: ReactNode
  action?: LinkAction | ReactNode
  children: ReactNode
  className?: string
  headerClassName?: string
}

type CardRowProps = {
  children: ReactNode
  to?: string
  className?: string
}

function isLinkAction(action: CardProps['action']): action is LinkAction {
  return (
    typeof action === 'object' &&
    action !== null &&
    !Array.isArray(action) &&
    'label' in action &&
    'to' in action
  )
}

function renderAction(action: CardProps['action']) {
  if (!action) return null
  if (isLinkAction(action)) {
    return (
      <Link to={action.to} className="ml-auto shrink-0 text-xs font-bold text-indigo-400 hover:text-indigo-300">
        {action.label}
      </Link>
    )
  }
  return <div className="ml-auto shrink-0">{action}</div>
}

export default function Card({ title, action, children, className = '', headerClassName = '' }: CardProps) {
  return (
    <section className={`overflow-hidden rounded-card bg-surface-card ${className}`}>
      {(title || action) && (
        <div className={`flex items-center gap-2.5 px-4 py-[13px] text-[13px] font-bold text-ink ${headerClassName}`}>
          {title && <div className="min-w-0 truncate">{title}</div>}
          {renderAction(action)}
        </div>
      )}
      {children}
    </section>
  )
}

export function CardRow({ children, to, className = '' }: CardRowProps) {
  const classes = `flex items-center gap-2.5 border-t border-surface-line px-4 py-[11px] text-ink transition-colors hover:bg-surface-raise ${className}`
  if (to) {
    return (
      <Link to={to} className={`${classes} no-underline`}>
        {children}
      </Link>
    )
  }
  return <div className={classes}>{children}</div>
}
