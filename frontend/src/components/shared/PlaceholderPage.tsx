interface PlaceholderPageProps {
  title: string;
}

export default function PlaceholderPage({ title }: PlaceholderPageProps) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 px-6 text-center">
      <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
        Coming Soon
      </p>
      <h1 className="text-3xl font-bold text-slate-900">{title} · 規劃中</h1>
      <p className="max-w-md text-slate-500">
        此板塊將於後續子專案中實作，敬請期待。
      </p>
    </div>
  );
}
