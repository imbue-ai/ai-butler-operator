export interface SessionCreateResponse {
  code: string;
  phone_number: string;
  url: string;
}

export interface SessionStatusResponse {
  code: string;
  state: string;
}

export interface WsMessage {
  type: "screenshot" | "status" | "session_ended" | "pong" | "live_view";
  data?: string;
  status?: string;
  detail?: string;
  live_view_url?: string;
}
