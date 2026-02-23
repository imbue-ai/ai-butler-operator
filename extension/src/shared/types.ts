// ── Server → Extension messages ──

export interface ScreenshotRequest {
  type: "screenshot_request";
  requestId: string;
}

export interface ActionCommand {
  type: "action_command";
  requestId: string;
  action: "click" | "type" | "key" | "scroll" | "navigate";
  // click / scroll coordinates
  x?: number;
  y?: number;
  // type / navigate
  text?: string;
  // key
  keys?: string;
  // scroll deltas
  deltaX?: number;
  deltaY?: number;
  // navigate
  url?: string;
}

export interface StatusMessage {
  type: "status";
  status: string;
  detail?: string;
}

export interface SessionEndedMessage {
  type: "session_ended";
}

export interface PongMessage {
  type: "pong";
}

export type ServerMessage =
  | ScreenshotRequest
  | ActionCommand
  | StatusMessage
  | SessionEndedMessage
  | PongMessage;

// ── Extension → Server messages ──

export interface ScreenshotResponse {
  type: "screenshot_response";
  requestId: string;
  data: string; // base64 jpeg
  width: number;
  height: number;
  devicePixelRatio: number;
}

export interface ActionResult {
  type: "action_result";
  requestId: string;
  success: boolean;
  error?: string;
}

export interface PingMessage {
  type: "ping";
}

export type ExtensionMessage =
  | ScreenshotResponse
  | ActionResult
  | PingMessage;

// ── API response types ──

export interface SessionCreateResponse {
  code: string;
  phone_number: string;
}

export interface SessionStatusResponse {
  code: string;
  state: string;
}

// ── Internal messages (background ↔ content script) ──

export interface ContentActionMessage {
  source: "pbu-background";
  action: "click" | "type" | "key" | "scroll";
  x?: number;
  y?: number;
  text?: string;
  keys?: string;
  deltaX?: number;
  deltaY?: number;
}

export interface ContentActionResponse {
  success: boolean;
  error?: string;
}
