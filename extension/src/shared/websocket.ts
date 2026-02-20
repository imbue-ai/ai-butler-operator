import { WS_URL, RECONNECT_DELAY_MS, PING_INTERVAL_MS } from "./constants";
import type { WsMessage } from "./types";

export type MessageHandler = (msg: WsMessage) => void;

export class WebSocketManager {
  private ws: WebSocket | null = null;
  private pingInterval: number | null = null;
  private code: string;
  private onMessage: MessageHandler;
  private onDisconnect: () => void;
  private shouldReconnect = true;

  constructor(
    code: string,
    onMessage: MessageHandler,
    onDisconnect: () => void
  ) {
    this.code = code;
    this.onMessage = onMessage;
    this.onDisconnect = onDisconnect;
  }

  connect(): void {
    this.shouldReconnect = true;
    this.ws = new WebSocket(`${WS_URL}/ws/${this.code}`);

    this.ws.onopen = () => {
      console.log("WebSocket connected");
      this.startPing();
    };

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const msg: WsMessage = JSON.parse(event.data);
        this.onMessage(msg);
      } catch (e) {
        console.error("Failed to parse WS message", e);
      }
    };

    this.ws.onclose = (event: CloseEvent) => {
      console.log("WebSocket closed, code:", event.code);
      this.stopPing();
      // Stop reconnecting if the session is invalid (4004) or ended normally (1000)
      if (event.code === 4004 || event.code === 1000) {
        this.shouldReconnect = false;
      }
      if (this.shouldReconnect) {
        setTimeout(() => this.connect(), RECONNECT_DELAY_MS);
      }
      this.onDisconnect();
    };

    this.ws.onerror = (err) => {
      console.error("WebSocket error", err);
    };
  }

  close(): void {
    this.shouldReconnect = false;
    this.stopPing();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  private startPing(): void {
    this.pingInterval = window.setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "ping" }));
      }
    }, PING_INTERVAL_MS);
  }

  private stopPing(): void {
    if (this.pingInterval !== null) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }
}
