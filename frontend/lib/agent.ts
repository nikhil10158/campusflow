import { API_URL } from "./api";
import { useAuth } from "./store";
import type { AgentEvent } from "./types";

export async function streamAgent(
  message: string,
  clarification: { original: string; answer: string; field: string } | null,
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = useAuth.getState().token;
  const response = await fetch(`${API_URL}/agent/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ message, clarification }),
    signal,
  });
  if (!response.ok || !response.body) {
    const detail = await response.text();
    throw new Error(detail || `Agent request failed (${response.status})`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const dataLine = block.split("\n").find((line) => line.startsWith("data:"));
      if (dataLine) onEvent(JSON.parse(dataLine.slice(5).trim()) as AgentEvent);
      boundary = buffer.indexOf("\n\n");
    }
  }
}
