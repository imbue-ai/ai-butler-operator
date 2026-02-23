import { WS_URL, RECONNECT_DELAY_MS, PING_INTERVAL_MS } from "./constants";
import type { ServerMessage, ExtensionMessage } from "./types";

export type ServerMessageHandler = (msg: ServerMessage) => void;

/**
 * WebSocket manager adapted for service worker context.
 * Uses self.setInterval (works in both window and service worker).
 */
export class WebSocketManager {
  private ws: WebSocket | null = null;
  private pingInterval: ReturnType<typeof setInterval> | null = null;
  private code: string;
  private onMessage: ServerMessageHandler;
  private onDisconnect: () => void;
  private shouldReconnect = true;

  constructor(
    code: string,
    onMessage: ServerMessageHandler,
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
        const msg: ServerMessage = JSON.parse(event.data);
        this.onMessage(msg);
      } catch (e) {
        console.error("Failed to parse WS message", e);
      }
    };

    this.ws.onclose = (event: CloseEvent) => {
      console.log("WebSocket closed, code:", event.code);
      this.stopPing();
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

  send(msg: ExtensionMessage): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    } else {
      console.warn("WebSocket not open, cannot send message");
    }
  }

  close(): void {
    this.shouldReconnect = false;
    this.stopPing();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  get isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  private startPing(): void {
    this.pingInterval = setInterval(() => {
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
