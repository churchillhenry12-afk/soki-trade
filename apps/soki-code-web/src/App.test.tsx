import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const setup = {
  agent: {
    name: "soki code",
    ready: false,
    runtime: "PRODUCTION",
    execution: "RESEARCH_AND_PAPER_ONLY",
    proof_loop: "ENABLED",
  },
  hermes: {
    status: "OFF",
    adapter_kind: "hermes-http-runtime",
    configured: false,
    verified: false,
    url: "",
    last_error: "",
  },
  market_data: { status: "READY" },
  telegram: { connected: false },
  mt5: { connected: false },
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const payload =
        url.includes("/agent/tasks") || url.endsWith("/attachments") ? [] : setup;
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  Element.prototype.scrollIntoView = vi.fn();
});

describe("soki code workspace", () => {
  it("renders a focused chat-first workspace", async () => {
    render(<App />);

    expect(screen.getAllByText("soki code").length).toBeGreaterThan(0);
    expect(
      screen.getByRole("heading", { name: /What can I help you get done/ }),
    ).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Message soki code")).toBeInTheDocument();
    expect(await screen.findByText("Photos, video & files")).toBeInTheDocument();
  });
});
