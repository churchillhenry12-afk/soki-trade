import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { AgentWorkspace } from "./components/AgentWorkspace";
import { SetupWizard } from "./components/SetupWizard";
import type { SetupStatus } from "./types";
import { useQForge } from "./useQForge";

const INSTALL_BASE_URL =
  (import.meta.env.VITE_INSTALL_BASE_URL as string | undefined) ??
  "https://github.com/churchillhenry12-afk/soki-trade/releases/latest/download";
const UNIX_INSTALL_URL = `${INSTALL_BASE_URL}/install.sh`;
const WINDOWS_INSTALL_URL = `${INSTALL_BASE_URL}/install.ps1`;

export default function App() {
  const qforge = useQForge();
  const [setup, setSetup] = useState<SetupStatus | null>(null);
  const [view, setView] = useState<"setup" | "agent">(
    window.localStorage.getItem("qforge.agent.open") === "true" ? "agent" : "setup",
  );
  const [setupError, setSetupError] = useState("");

  const refreshSetup = useCallback(async () => {
    try {
      setSetup(await api.setupStatus());
      setSetupError("");
    } catch (error) {
      setSetupError((error as Error).message);
    }
  }, []);

  useEffect(() => {
    void refreshSetup();
  }, [refreshSetup]);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [view]);

  function openAgent() {
    window.localStorage.setItem("qforge.agent.open", "true");
    setView("agent");
  }

  if (!setup) {
    const unixInstallCommand = `curl -fsSL ${UNIX_INSTALL_URL} | bash`;
    const windowsInstallCommand = `irm ${WINDOWS_INSTALL_URL} | iex`;
    return (
      <main className="boot-screen">
        <span className="boot-mark">S</span>
        <strong>
          {setupError
            ? "Connect this interface to your Soki agent"
            : "Starting Soki Trade…"}
        </strong>
        <p>
          {setupError
            ? "Install and start Soki Trade on this computer, then retry the connection."
            : "Checking the agent and its connections."}
        </p>
        {setupError ? (
          <section className="install-card" aria-label="Terminal installation">
            <span>ONE-LINE TERMINAL INSTALL</span>
            <div className="install-card__command">
              <b>Windows PowerShell</b>
              <code>{windowsInstallCommand}</code>
            </div>
            <div className="install-card__command">
              <b>macOS / Linux</b>
              <code>{unixInstallCommand}</code>
            </div>
            <small>
              The agent, API keys, MT5 access, and research database stay on your computer.
            </small>
          </section>
        ) : null}
        {setupError ? (
          <div className="boot-actions">
            <button onClick={() => void refreshSetup()}>Retry connection</button>
            <a href={WINDOWS_INSTALL_URL}>PowerShell installer</a>
            <a href={UNIX_INSTALL_URL}>Shell installer</a>
          </div>
        ) : null}
      </main>
    );
  }

  const coreReady = setup.model.connected && setup.market_data.status === "READY";

  return view === "setup" || !coreReady ? (
    <SetupWizard setup={setup} onRefresh={refreshSetup} onOpenAgent={openAgent} />
  ) : (
    <AgentWorkspace
      setup={setup}
      qforge={qforge}
      onRefreshSetup={refreshSetup}
      onManageSetup={() => setView("setup")}
    />
  );
}
