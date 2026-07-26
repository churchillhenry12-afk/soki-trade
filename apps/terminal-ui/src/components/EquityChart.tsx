type EquityChartProps = {
  values: number[];
};

export function EquityChart({ values }: EquityChartProps) {
  if (values.length < 2) return <div className="empty">Awaiting equity samples.</div>;
  const sampled = values.filter((_, index) => index % Math.max(1, Math.floor(values.length / 120)) === 0);
  const minimum = Math.min(...sampled);
  const maximum = Math.max(...sampled);
  const range = maximum - minimum || 1;
  const points = sampled
    .map((value, index) => {
      const x = (index / (sampled.length - 1)) * 100;
      const y = 38 - ((value - minimum) / range) * 34;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg
      className="equity-chart"
      viewBox="0 0 100 40"
      preserveAspectRatio="none"
      role="img"
      aria-label="Strategy equity curve"
    >
      <line x1="0" y1="38" x2="100" y2="38" />
      <polyline points={points} />
    </svg>
  );
}

