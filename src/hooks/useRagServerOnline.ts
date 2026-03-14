import { useState, useEffect } from "react";

const RAG_API_URL = "https://lindenhilaryachen-gpt.benfeist.com";

export function useRagServerOnline(enabled = true): boolean | undefined {
  const [online, setOnline] = useState<boolean | undefined>(undefined);

  useEffect(() => {
    if (!enabled) return;

    let eventSource: EventSource | null = null;
    let reconnectTimeout: number | null = null;

    const connect = () => {
      try {
        eventSource = new EventSource(`${RAG_API_URL}/health/stream`);

        eventSource.onopen = () => {
          setOnline(true);
          if (reconnectTimeout) {
            clearTimeout(reconnectTimeout);
            reconnectTimeout = null;
          }
        };

        eventSource.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.status === "connected" || data.status === "alive") {
              setOnline(true);
            }
          } catch (e) {
            console.error("Failed to parse health event:", e);
          }
        };

        eventSource.onerror = () => {
          setOnline(false);
          eventSource?.close();
          if (!reconnectTimeout) {
            reconnectTimeout = window.setTimeout(() => {
              reconnectTimeout = null;
              connect();
            }, 5000);
          }
        };
      } catch (error) {
        console.error("Failed to create EventSource:", error);
        setOnline(false);
      }
    };

    connect();

    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      eventSource?.close();
    };
  }, [enabled]);

  return enabled ? online : undefined;
}
