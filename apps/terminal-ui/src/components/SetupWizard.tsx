import { useState, type FormEvent } from "react";
import { api } from "../api";
import type { SetupStatus } from "../types";

type Props = {
  setup: SetupStatus;
  onRefresh: () => Promise<void>;
  onOpenAgent: () => void;
};

function StatePill({ connected, label }: { connected: boolean; label?: string }) {
  return (
    <span className={connected ? "state-pill state-pill--ready" : "state-pill"}>
      <i />
      {label ?? (connected ? "Connected" : "Not connected")}
    </span>
  );
}

export function SetupWizard({ setup, onRefresh, onOpenAgent }: Props) {
  const [provider, setProvider] = useState(setup.model.provider || "local");
  const [model, setModel] = useState(setup.model.model || "qwen2.5-coder:14b");
  const [availableModels, setAvailableModels] = useState(
    setup.model.model ? [setup.model.model] : [],
  );
  const [baseUrl, setBaseUrl] = useState(
    setup.model.base_url || "http://127.0.0.1:11434/v1",
  );
  const [apiKey, setApiKey] = useState("");
  const [telegramToken, setTelegramToken] = useState("");
  const [telegramChat, setTelegramChat] = useState("");
  const [mt5Transport, setMT5Transport] = useState<"rest" | "mcp">("rest");
  const [mt5AccountMode, setMT5AccountMode] = useState<"DEMO" | "REAL">(
    setup.mt5.account_mode === "REAL" ? "REAL" : "DEMO",
  );
  const [mt5Endpoint, setMT5Endpoint] = useState("");
  const [mt5Token, setMT5Token] = useState("");
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");

  function changeProvider(nextProvider: string) {
    const defaults: Record<string, string> = {
      local: "http://127.0.0.1:11434/v1",
      openai_compatible: "https://api.openai.com/v1",
      anthropic: "https://api.anthropic.com",
    };
    setProvider(nextProvider);
    setBaseUrl(defaults[nextProvider] ?? "");
    setModel("");
    setAvailableModels([]);
    setNotice("Add the provider API key and base URL, then scan available models.");
  }

  async function scanModels() {
    setBusy("model-scan");
    setNotice("");
    try {
      const catalog = await api.scanModels({
        provider,
        base_url: baseUrl,
        api_key: apiKey || null,
      });
      setAvailableModels(catalog.models);
      setModel((current) =>
        catalog.models.includes(current) ? current : (catalog.models[0] ?? ""),
      );
      setNotice(`Found ${catalog.count} available models. Choose one, then save and test.`);
    } catch (error) {
      setAvailableModels([]);
      setModel("");
      setNotice(`Model scan failed: ${(error as Error).message}`);
    } finally {
      setBusy("");
    }
  }

  async function connectModel(event: FormEvent) {
    event.preventDefault();
    setBusy("model");
    setNotice("");
    try {
      await api.configureModel({
        provider,
        model,
        base_url: baseUrl,
        api_key: apiKey || null,
      });
      await api.testModel();
      await onRefresh();
      setNotice("Model answered the connection test.");
      setApiKey("");
    } catch (error) {
      setNotice(`Model connection failed: ${(error as Error).message}`);
    } finally {
      setBusy("");
    }
  }

  async function connectTelegram(event: FormEvent) {
    event.preventDefault();
    setBusy("telegram");
    setNotice("");
    try {
      await api.connectTelegram({ bot_token: telegramToken, chat_id: telegramChat });
      await onRefresh();
      setNotice("Telegram bot answered and received the Soki Trade test message.");
      setTelegramToken("");
    } catch (error) {
      setNotice(`Telegram connection failed: ${(error as Error).message}`);
    } finally {
      setBusy("");
    }
  }

  async function connectMT5(event: FormEvent) {
    event.preventDefault();
    setBusy("mt5");
    setNotice("");
    try {
      await api.connectMT5({
        transport: mt5Transport,
        endpoint: mt5Endpoint,
        account_mode: mt5AccountMode,
        token: mt5Token || null,
      });
      await onRefresh();
      setNotice(
        `The MT5 ${mt5AccountMode} account is connected in read-only mode.`,
      );
      setMT5Token("");
    } catch (error) {
      setNotice(`MT5 connection failed: ${(error as Error).message}`);
    } finally {
      setBusy("");
    }
  }

  const coreReady = setup.model.connected && setup.market_data.status === "READY";

  return (
    <div className="setup-page">
      <header className="setup-header">
        <div className="wordmark"><span>S</span> SOKI TRADE</div>
        <p>Agent setup</p>
        <span className="safety-note">Research and paper only · live orders disabled</span>
      </header>

      <main className="setup-main">
        <section className="agent-intro">
          <div className={coreReady ? "agent-core is-ready" : "agent-core"}>
            <div className="agent-core__orbit agent-core__orbit--one" />
            <div className="agent-core__orbit agent-core__orbit--two" />
            <div className="agent-core__center">S</div>
            <span className="orbit-node orbit-node--model">AI</span>
            <span className="orbit-node orbit-node--data">DATA</span>
            <span className="orbit-node orbit-node--telegram">TG</span>
            <span className="orbit-node orbit-node--mt5">MT5</span>
          </div>
          <div>
            <span className="eyebrow">Your agentic operations workspace</span>
            <h1>{coreReady ? "Soki Trade is ready to talk." : "Bring Soki Trade online."}</h1>
            <p>
              Connect Soki’s intelligence and tools. Once online, the agent can handle
              general tasks, manage these services through chat, and run trading research.
            </p>
          </div>
        </section>

        <section className="setup-grid" aria-label="Agent connections">
          <article className="setup-card setup-card--primary">
            <div className="setup-card__heading">
              <span className="step-number">1</span>
              <div><h2>Intelligence</h2><p>The model that powers every agent task.</p></div>
              <StatePill connected={setup.model.connected} />
            </div>
            <form className="connection-form" onSubmit={(event) => void connectModel(event)}>
              <label>Provider
                <select value={provider} onChange={(event) => changeProvider(event.target.value)}>
                  <option value="local">Local Ollama / OpenAI-compatible</option>
                  <option value="openai_compatible">OpenAI-compatible cloud</option>
                  <option value="anthropic">Anthropic</option>
                </select>
              </label>
              <label>API key <small>Leave blank for local Ollama or to retain a saved key.</small>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder="Optional for local providers"
                />
              </label>
              <label>Base URL
                <input
                  value={baseUrl}
                  onChange={(event) => {
                    setBaseUrl(event.target.value);
                    setAvailableModels([]);
                    setModel("");
                  }}
                  placeholder="https://provider.example/v1"
                  required
                />
              </label>
              <button
                className="scan-models"
                type="button"
                disabled={busy === "model-scan" || !baseUrl}
                onClick={() => void scanModels()}
              >
                {busy === "model-scan" ? "Scanning provider…" : "Scan available models"}
              </button>
              <label>Available model <small>Loaded directly from the provider.</small>
                <select
                  value={model}
                  onChange={(event) => setModel(event.target.value)}
                  disabled={availableModels.length === 0}
                  required
                >
                  {availableModels.length === 0
                    ? <option value="">Scan provider first</option>
                    : availableModels.map((availableModel) => (
                        <option key={availableModel} value={availableModel}>{availableModel}</option>
                      ))}
                </select>
              </label>
              <button disabled={busy === "model" || !model}>
                {busy === "model" ? "Waiting for model…" : "Save and test model"}
              </button>
            </form>
          </article>

          <article className="setup-card">
            <div className="setup-card__heading">
              <span className="step-number">2</span>
              <div><h2>Market data</h2><p>Real candles used by the backtester.</p></div>
              <StatePill
                connected={setup.market_data.status === "READY"}
                label={setup.market_data.status === "READY" ? "Real feed ready" : "Unavailable"}
              />
            </div>
            <div className="connection-summary">
              <strong>{setup.market_data.adapter_kind}</strong>
              <span>Source: {String(setup.market_data.source ?? "public feed")}</span>
              <p>Downloaded candles are validated and cached. Local CSV/Parquet can override them.</p>
            </div>
          </article>

          <article className="setup-card">
            <div className="setup-card__heading">
              <span className="step-number">3</span>
              <div><h2>Telegram</h2><p>Reach the agent away from this screen.</p></div>
              <StatePill connected={Boolean(setup.telegram.inbound_ready)} />
            </div>
            <form className="connection-form" onSubmit={(event) => void connectTelegram(event)}>
              <label>Bot token
                <input
                  type="password"
                  value={telegramToken}
                  onChange={(event) => setTelegramToken(event.target.value)}
                  placeholder="123456:bot-token"
                  required
                />
              </label>
              <label>Chat ID <small>Required so only your chat can control the agent.</small>
                <input
                  value={telegramChat}
                  onChange={(event) => setTelegramChat(event.target.value)}
                  placeholder="-100… or your user ID"
                  required
                />
              </label>
              <button disabled={busy === "telegram"}>
                {busy === "telegram" ? "Contacting Telegram…" : "Connect Telegram"}
              </button>
            </form>
          </article>

          <article className="setup-card">
            <div className="setup-card__heading">
              <span className="step-number">4</span>
              <div><h2>MT5 bridge</h2><p>Demo or read-only Real account via REST or MCP.</p></div>
              <StatePill connected={Boolean(setup.mt5.connected)} />
            </div>
            <form className="connection-form" onSubmit={(event) => void connectMT5(event)}>
              <label>Account type
                <select
                  value={mt5AccountMode}
                  onChange={(event) =>
                    setMT5AccountMode(event.target.value as "DEMO" | "REAL")
                  }
                >
                  <option value="DEMO">Demo account</option>
                  <option value="REAL">Real account · read-only</option>
                </select>
              </label>
              <label>Transport
                <select
                  value={mt5Transport}
                  onChange={(event) => setMT5Transport(event.target.value as "rest" | "mcp")}
                >
                  <option value="rest">REST bridge</option>
                  <option value="mcp">MCP server</option>
                </select>
              </label>
              <label>Gateway URL
                <input
                  value={mt5Endpoint}
                  onChange={(event) => setMT5Endpoint(event.target.value)}
                  placeholder="https://your-windows-vps.example"
                  required
                />
              </label>
              <label>Gateway token
                <input
                  type="password"
                  value={mt5Token}
                  onChange={(event) => setMT5Token(event.target.value)}
                  placeholder="Bearer token, if required"
                />
              </label>
              <button disabled={busy === "mt5"}>
                {busy === "mt5" ? "Checking bridge…" : "Connect MT5 bridge"}
              </button>
            </form>
            <p className="inline-warning">
              The bridge-reported account type must match your selection. Real accounts are
              read-only and live order execution remains disabled.
            </p>
          </article>
        </section>

        {notice ? <div className="setup-notice" role="status">{notice}</div> : null}

        <footer className="setup-finish">
          <div>
            <strong>{coreReady ? "Core agent ready" : "Complete steps 1 and 2"}</strong>
            <span>Telegram and MT5 can be connected now or later from Agent setup.</span>
          </div>
          <button className="open-agent" disabled={!coreReady} onClick={onOpenAgent}>
            Open Soki Trade <span>→</span>
          </button>
        </footer>
      </main>
    </div>
  );
}
