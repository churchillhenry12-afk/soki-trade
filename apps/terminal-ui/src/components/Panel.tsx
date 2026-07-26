import type { PropsWithChildren, ReactNode } from "react";

type PanelProps = PropsWithChildren<{
  title: string;
  code: string;
  className?: string;
  action?: ReactNode;
}>;

export function Panel({ title, code, className = "", action, children }: PanelProps) {
  return (
    <section className={`panel ${className}`}>
      <header className="panel__header">
        <span className="panel__code">{code}</span>
        <h2>{title}</h2>
        {action ? <div className="panel__action">{action}</div> : null}
      </header>
      <div className="panel__body">{children}</div>
    </section>
  );
}

