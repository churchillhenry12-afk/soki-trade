import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "../api";
import type { useQForge } from "../useQForge";
import type { ChatTurn, SetupStatus } from "../types";
import {
  OperationsCenter,
  type ProductSection,
} from "./OperationsCenter";

type Props = {
  setup: SetupStatus;
  qforge: ReturnType<typeof useQForge>;
  onRefreshSetup: () => Promise<void>;
  onManageSetup: () => void;
};

type DisplayMessage = ChatTurn & { id: string };
type ConnectionTask = "model" | "telegram" | "mt5";

const WELCOME: DisplayMessage = {
  id: "welcome",
  role: "assistant",
  content:
    "I’m online. Give me an outcome—not just a question. I’ll define success, do the work, and show you the proof.",
};

const PRODUCT_NAV: Array<{ id: ProductSection; label: string; key: string }> = [
  { id: "overview", label: "Overview", key: "F1" },
  { id: "agent", label: "Agent", key: "F2" },
  { id: "research", label: "Research", key: "F3" },
  { id: "runs", label: "Runs", key: "F4" },
  { id: "strategies", label: "Strategies", key: "F5" },
  { id: "labs", label: "Labs", key: "F6" },
  { id: "risk", label: "Risk", key: "F7" },
  { id: "connections", label: "Connections", key: "F8" },
];

function MessageContent({ content }: { content: string }) {
  return (
    <div className="message-content">
      <ReactMarkdown
        components={{
          a: ({ children, ...props }) => (
            <a {...props} target="_blank" rel="noreferrer">{children}</a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

function ConnectionRow({
  name,
  detail,
  connected,
}: {
  name: string;
  detail: string;
  connected: boolean;
}) {
  return (
    <div className="connection-row">
      <span className={connected ? "connection-light is-on" : "connection-light"} />
      <div><strong>{name}</strong><small>{detail}</small></div>
      <em>{connected ? "ready" : "off"}</em>
    </div>
  );
}

function ConnectionTool({
  task,
  busy,
  onCancel,
  onOpenModel,
  onConnectTelegram,
  onConnectMT5,
}: {
  task: ConnectionTask;
  busy: boolean;
  onCancel: () => void;
  onOpenModel: () => void;
  onConnectTelegram: (token: string, chatId: string) => Promise<void>;
  onConnectMT5: (
    transport: "rest" | "mcp",
    endpoint: string,
    accountMode: "DEMO" | "REAL",
    token: string,
  ) => Promise<void>;
}) {
  const [telegramToken, setTelegramToken] = useState("");
  const [chatId, setChatId] = useState("");
  const [transport, setTransport] = useState<"rest" | "mcp">("mcp");
  const [accountMode, setAccountMode] = useState<"DEMO" | "REAL">("DEMO");
  const [endpoint, setEndpoint] = useState("");
  const [mt5Token, setMT5Token] = useState("");

  if (task === "model") {
    return (
      <article className="chat-tool" aria-label="Connect AI provider">
        <div className="chat-tool__signal"><i /><span>Connection tool</span></div>
        <div className="chat-tool__heading">
          <div><strong>AI provider</strong><p>API key · base URL · live model scan</p></div>
          <em>Secure setup</em>
        </div>
        <div className="chat-tool__actions">
          <button onClick={onOpenModel}>Open provider setup</button>
          <button className="chat-tool__cancel" onClick={onCancel}>Cancel</button>
        </div>
      </article>
    );
  }

  if (task === "telegram") {
    return (
      <article className="chat-tool" aria-label="Connect Telegram">
        <div className="chat-tool__signal"><i /><span>Connection tool</span></div>
        <div className="chat-tool__heading">
          <div><strong>Connect Telegram</strong><p>Soky validates the bot and sends a test.</p></div>
          <em>Bot API</em>
        </div>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void onConnectTelegram(telegramToken, chatId);
          }}
        >
          <label>Bot token
            <input
              type="password"
              value={telegramToken}
              onChange={(event) => setTelegramToken(event.target.value)}
              placeholder="Token from @BotFather"
              required
            />
          </label>
          <label>Allowed chat ID
            <input
              value={chatId}
              onChange={(event) => setChatId(event.target.value)}
              placeholder="Only this chat can control Soky"
              required
            />
          </label>
          <div className="chat-tool__actions">
            <button disabled={busy}>{busy ? "Connecting…" : "Connect Telegram"}</button>
            <button type="button" className="chat-tool__cancel" onClick={onCancel}>Cancel</button>
          </div>
        </form>
      </article>
    );
  }

  return (
    <article className="chat-tool" aria-label="Connect MT5">
      <div className="chat-tool__signal"><i /><span>Connection tool</span></div>
      <div className="chat-tool__heading">
        <div><strong>Connect MT5</strong><p>Use a native MCP server or REST bridge.</p></div>
        <em>Protocol check</em>
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void onConnectMT5(transport, endpoint, accountMode, mt5Token);
        }}
      >
        <label>Account type
          <select
            value={accountMode}
            onChange={(event) => setAccountMode(event.target.value as "DEMO" | "REAL")}
          >
            <option value="DEMO">Demo account</option>
            <option value="REAL">Real account · read-only</option>
          </select>
        </label>
        <label>Connection type
          <select
            value={transport}
            onChange={(event) => setTransport(event.target.value as "rest" | "mcp")}
          >
            <option value="mcp">Native MCP</option>
            <option value="rest">REST bridge</option>
          </select>
        </label>
        <label className="chat-tool__wide-field">Gateway URL
          <input
            value={endpoint}
            onChange={(event) => setEndpoint(event.target.value)}
            placeholder="https://your-mt5-gateway.example"
            required
          />
        </label>
        <label>Gateway token <small>Optional when your gateway does not require one.</small>
          <input
            type="password"
            value={mt5Token}
            onChange={(event) => setMT5Token(event.target.value)}
            placeholder="Bearer token"
          />
        </label>
        <div className="chat-tool__actions">
          <button disabled={busy}>{busy ? "Checking gateway…" : "Connect MT5"}</button>
          <button type="button" className="chat-tool__cancel" onClick={onCancel}>Cancel</button>
        </div>
      </form>
    </article>
  );
}

export function AgentWorkspace({
  setup,
  qforge,
  onRefreshSetup,
  onManageSetup,
}: Props) {
  const [messages, setMessages] = useState<DisplayMessage[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [connectionTask, setConnectionTask] = useState<ConnectionTask | null>(null);
  const [toolBusy, setToolBusy] = useState(false);
  const [activeSection, setActiveSection] = useState<ProductSection>("agent");
  const messageListRef = useRef<HTMLDivElement>(null);
  const report = qforge.experiment?.report;
  const best = useMemo(() => {
    if (!report) return null;
    return [...report.statistical_results].sort(
      (left, right) => right.robustness_score - left.robustness_score,
    )[0];
  }, [report]);
  const bestBacktest = report?.backtests.find((item) => item.strategy_id === best?.strategy_id);

  useEffect(() => {
    const list = messageListRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [connectionTask, messages, sending]);

  function addAssistantMessage(content: string) {
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: "assistant", content },
    ]);
  }

  async function connectTelegram(token: string, chatId: string) {
    setToolBusy(true);
    try {
      const connected = await api.connectTelegram({ bot_token: token, chat_id: chatId });
      await onRefreshSetup();
      setConnectionTask(null);
      addAssistantMessage(
        `Telegram is connected${connected.bot_username ? ` as @${connected.bot_username}` : ""}. ` +
        "I sent a test message and restricted control to the chat ID you provided.",
      );
    } catch (error) {
      addAssistantMessage(`Telegram connection failed: ${(error as Error).message}`);
    } finally {
      setToolBusy(false);
    }
  }

  async function connectMT5(
    transport: "rest" | "mcp",
    endpoint: string,
    accountMode: "DEMO" | "REAL",
    token: string,
  ) {
    setToolBusy(true);
    try {
      await api.connectMT5({
        transport,
        endpoint,
        account_mode: accountMode,
        token: token || null,
      });
      await onRefreshSetup();
      setConnectionTask(null);
      addAssistantMessage(
        `MT5 ${accountMode} account is connected through ${transport.toUpperCase()} in ` +
        "read-only mode. Live order execution remains disabled.",
      );
    } catch (error) {
      addAssistantMessage(`MT5 connection failed: ${(error as Error).message}`);
    } finally {
      setToolBusy(false);
    }
  }

  async function send(text: string) {
    const message = text.trim();
    if (!message || sending) return;
    const userMessage: DisplayMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: message,
    };
    setMessages((current) => [...current, userMessage]);
    setInput("");
    setSending(true);
    try {
      const history = messages.map(({ role, content }) => ({ role, content }));
      const response = await qforge.chat(message, history);
      addAssistantMessage(response.reply);
      if (response.action === "CONNECTION_CHANGED") {
        await onRefreshSetup();
        setConnectionTask(null);
      }
      if (response.client_action === "CONNECT_MODEL") setConnectionTask("model");
      if (response.client_action === "CONNECT_TELEGRAM") setConnectionTask("telegram");
      if (response.client_action === "CONNECT_MT5") setConnectionTask("mt5");
    } catch (error) {
      addAssistantMessage(`I could not complete that request: ${(error as Error).message}`);
    } finally {
      setSending(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void send(input);
  }

  const state = qforge.experiment?.state ?? "IDLE";

  return (
    <div className="agent-page">
      <header className="agent-header">
        <div className="agent-identity">
          <span className="agent-avatar"><b>S</b><i /></span>
          <div><strong>SOKY CODE</strong><small>Evidence-first operating agent</small></div>
        </div>
        <div className="agent-presence"><i /> Online · {setup.model.model}</div>
        <button className="quiet-button" onClick={onManageSetup}>Connections & model</button>
      </header>

      <nav className="product-nav" aria-label="Soky Code sections">
        {PRODUCT_NAV.map((item) => (
          <button
            className={activeSection === item.id ? "is-active" : ""}
            key={item.id}
            onClick={() => setActiveSection(item.id)}
          >
            <small>{item.key}</small>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>

      {activeSection === "agent" ? (
      <main className="agent-layout">
        <aside className="connection-rail">
          <div>
            <div className="rail-title">
              <span className="rail-label">Connections</span>
              <button onClick={() => void send("Show connection status")}>Ask Soky</button>
            </div>
            <ConnectionRow
              name="Intelligence"
              detail={
                setup.hermes?.verified
                  ? "Hermes runtime · verified"
                  : `${setup.model.provider} · ${setup.model.model}`
              }
              connected={Boolean(setup.hermes?.verified) || setup.model.connected}
            />
            <ConnectionRow
              name="Market data"
              detail={`Real feed · ${String(setup.market_data.source ?? "ready")}`}
              connected={setup.market_data.status === "READY"}
            />
            <ConnectionRow
              name="Telegram"
              detail={String(setup.telegram.bot_username || "Not configured")}
              connected={Boolean(setup.telegram.inbound_ready)}
            />
            <ConnectionRow
              name="MT5"
              detail={
                setup.mt5.connected
                  ? `${String(setup.mt5.account_mode)} · read-only`
                  : String(setup.mt5.endpoint || "No bridge")
              }
              connected={Boolean(setup.mt5.connected)}
            />
          </div>
          <div className="rail-safety">
            <span>Agent boundary</span>
            <strong>Proof before completion</strong>
            <p>Soky records success checks and evidence. Trading stays research/PAPER.</p>
          </div>
        </aside>

        <section className="conversation">
          <div className="conversation-heading">
            <div><span>Soky workspace</span><h1>What outcome do you need?</h1></div>
            <span className="session-state">Proof Loop active</span>
          </div>
          <div className="message-list" aria-live="polite" ref={messageListRef}>
            {messages.map((message) => (
              <article className={`message message--${message.role}`} key={message.id}>
                <span>{message.role === "assistant" ? "S" : "You"}</span>
                <MessageContent content={message.content} />
              </article>
            ))}
            {sending ? (
              <article className="message message--assistant message--working">
                <span>S</span>
                <div className="working-card">
                  <div><strong>Soky is working</strong><small>Defining success · executing · verifying</small></div>
                  <i /><i /><i />
                </div>
              </article>
            ) : null}
            {connectionTask ? (
              <ConnectionTool
                task={connectionTask}
                busy={toolBusy}
                onCancel={() => setConnectionTask(null)}
                onOpenModel={onManageSetup}
                onConnectTelegram={connectTelegram}
                onConnectMT5={connectMT5}
              />
            ) : null}
          </div>
          <div className="prompt-suggestions">
            {[
              "Connect Telegram",
              "Connect MT5",
              "Show connection status",
              "Backtest EURUSD M15",
            ].map((suggestion) => (
              <button key={suggestion} onClick={() => void send(suggestion)}>{suggestion}</button>
            ))}
          </div>
          <form className="agent-composer" onSubmit={submit}>
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Give Soky Code a task…"
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void send(input);
                }
              }}
            />
            <button disabled={!input.trim() || sending} aria-label="Send message">↑</button>
            <small>Enter to send · Shift+Enter for a new line</small>
          </form>
        </section>

        <aside className="activity-drawer">
          <div className="activity-heading">
            <span>Proof ledger</span>
            <em className={`run-state run-state--${(qforge.lastProof?.status ?? state).toLowerCase()}`}>
              {qforge.lastProof?.status ?? state}
            </em>
          </div>
          {qforge.lastProof ? (
            <section className="proof-ledger" aria-label="Latest task proof">
              <small>Task {qforge.lastProof.task_id.slice(0, 8)} · {qforge.lastProof.runtime}</small>
              <strong>{qforge.lastProof.request}</strong>
              <div>
                {qforge.lastProof.checks.map((check) => (
                  <article key={check.key} className={`proof-check proof-check--${check.status.toLowerCase()}`}>
                    <i>{check.status === "VERIFIED" ? "✓" : check.status === "FAILED" ? "!" : "·"}</i>
                    <span><b>{check.label}</b><small>{check.evidence || check.status.toLowerCase()}</small></span>
                  </article>
                ))}
              </div>
            </section>
          ) : (
            <div className="proof-empty">
              <strong>No completion contract yet</strong>
              <p>Your next request will appear here with live success checks.</p>
            </div>
          )}
          {!qforge.experiment ? (
            <div className="activity-empty">
              <strong>No active research run</strong>
              <p>Connection work happens in chat. Strategy studies and reports appear here.</p>
            </div>
          ) : (
            <>
              <div className="run-card">
                <small>Run {qforge.experiment.experiment_id.slice(0, 8)}</small>
                <strong>{qforge.events.at(-1)?.event_type.replaceAll("_", " ") ?? state}</strong>
                <span>{qforge.connection === "LIVE" ? "Live activity stream" : "Run complete"}</span>
              </div>
              <div className="activity-feed">
                {qforge.events.slice(-7).reverse().map((event) => (
                  <div key={event.event_id}>
                    <i /><p><strong>{event.agent.replaceAll("_", " ")}</strong>{event.event_type}</p>
                  </div>
                ))}
              </div>
            </>
          )}
          {report && best && bestBacktest ? (
            <div className="report-card">
              <span>Latest report</span>
              <h2>{report.risk_decision.eligible ? "Paper review ready" : "Risk blocked"}</h2>
              <dl>
                <div><dt>Best candidate</dt><dd>{best.strategy_id}</dd></div>
                <div><dt>Net return</dt><dd>{(bestBacktest.metrics.net_return * 100).toFixed(2)}%</dd></div>
                <div><dt>Max drawdown</dt><dd>{(bestBacktest.metrics.maximum_drawdown * 100).toFixed(2)}%</dd></div>
                <div><dt>Trades</dt><dd>{bestBacktest.metrics.number_of_trades}</dd></div>
              </dl>
              <button onClick={() => void send("Show me the current report")}>Explain this report</button>
            </div>
          ) : null}
        </aside>
      </main>
      ) : (
        <main className="ops-shell">
          <OperationsCenter
            section={activeSection}
            setup={setup}
            qforge={qforge}
            onManageSetup={onManageSetup}
            onOpenAgent={() => setActiveSection("agent")}
            onRefreshSetup={onRefreshSetup}
          />
        </main>
      )}
    </div>
  );
}
