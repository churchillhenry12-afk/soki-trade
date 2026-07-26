import { useState, type FormEvent } from "react";

type Props = {
  disabled: boolean;
  onLaunch: (input: {
    title: string;
    thesis: string;
    symbol: string;
    timeframe: string;
  }) => Promise<void>;
};

export function CommandTerminal({ disabled, onLaunch }: Props) {
  const [title, setTitle] = useState("EURUSD intraday resilience");
  const [thesis, setThesis] = useState(
    "Test whether volatility-gated moving-average transitions survive realistic spread and slippage stress.",
  );
  const [symbol, setSymbol] = useState("EURUSD");
  const [timeframe, setTimeframe] = useState("M15");
  const [launching, setLaunching] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLaunching(true);
    try {
      await onLaunch({ title, thesis, symbol, timeframe });
    } finally {
      setLaunching(false);
    }
  }

  return (
    <form className="command" onSubmit={(event) => void submit(event)}>
      <label>
        <span>OBJECTIVE.NAME</span>
        <input value={title} onChange={(event) => setTitle(event.target.value)} minLength={3} required />
      </label>
      <label className="command__thesis">
        <span>RESEARCH.TASK</span>
        <textarea
          value={thesis}
          onChange={(event) => setThesis(event.target.value)}
          minLength={12}
          required
        />
      </label>
      <label>
        <span>SYMBOL</span>
        <input value={symbol} onChange={(event) => setSymbol(event.target.value.toUpperCase())} required />
      </label>
      <label>
        <span>FRAME</span>
        <select value={timeframe} onChange={(event) => setTimeframe(event.target.value)}>
          {["M5", "M15", "M30", "H1", "H4", "D1"].map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
      </label>
      <button className="command__launch" disabled={disabled || launching}>
        {launching ? "INITIALIZING…" : "RUN ADVERSARIAL STUDY ↵"}
      </button>
    </form>
  );
}

