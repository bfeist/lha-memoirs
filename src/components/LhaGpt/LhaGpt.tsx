import { useState, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { getRecordingByPath } from "../../config/recordings";
import styles from "./LhaGpt.module.css";

interface Citation {
  recording_id: string;
  timestamp: number;
  quote_snippet: string;
}

interface ChatResponse {
  answer: string;
  citations: Citation[];
}

interface Message {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  isStreaming?: boolean;
}

function formatTimestamp(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

// Map recording_id (folder path) to recording route ID using recordings.ts
function getRecordingRoute(recordingId: string): string | null {
  const recording = getRecordingByPath(recordingId);
  if (!recording) {
    console.warn(`Unknown recording_id: ${recordingId} - citation may be hallucinated`);
    return null;
  }
  return recording.id;
}

const LhaGpt: React.FC<{
  isOpen: boolean;
  onClose: () => void;
}> = ({ isOpen, onClose }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  const handleCitationClick = (citation: Citation) => {
    const recordingId = getRecordingRoute(citation.recording_id);
    if (!recordingId) {
      // Invalid recording_id - don't navigate
      return;
    }
    // Navigate to the recording with timestamp
    navigate(`/recording/${recordingId}?t=${Math.floor(citation.timestamp)}`);
    onClose();
  };

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage = input.trim();
    setInput("");
    setMessages((prev) => [...(prev || []), { role: "user", content: userMessage }]);
    setIsLoading(true);

    // Add placeholder for streaming response
    setMessages((prev) => [...prev, { role: "assistant", content: "", isStreaming: true }]);

    // Use production URL in development, relative path in production
    const apiUrl = import.meta.env.DEV
      ? "https://lindenhilaryachen.benfeist.com/stream.php"
      : "/stream.php";

    try {
      const response = await fetch(apiUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message: userMessage }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("No response body");
      }

      const decoder = new TextDecoder();
      let accumulatedData = "";
      let accumulatedText = "";

      const updateStreamingMessage = (text: string) => {
        setMessages((prev) => {
          const newMessages = [...prev];
          const lastMsg = newMessages[newMessages.length - 1];
          if (lastMsg?.isStreaming) {
            lastMsg.content = text;
          }
          return newMessages;
        });
        scrollToBottom();
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        accumulatedData += chunk;

        // Parse SSE data - Gemini sends "data: {...}" lines
        const lines = accumulatedData.split("\n");
        accumulatedData = lines.pop() || ""; // Keep incomplete line

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const jsonStr = line.slice(6).trim();
            if (jsonStr && jsonStr !== "[DONE]") {
              try {
                const data = JSON.parse(jsonStr);
                // Extract text from Gemini response structure
                const text = data.candidates?.[0]?.content?.parts?.[0]?.text || "";
                if (text) {
                  accumulatedText += text;
                  updateStreamingMessage(accumulatedText);
                }
              } catch {
                // Continue accumulating if JSON is incomplete
              }
            }
          }
        }
      }

      // Try to parse the final accumulated text as JSON response
      try {
        const finalResponse: ChatResponse = JSON.parse(accumulatedText);
        setMessages((prev) => {
          const newMessages = [...prev];
          const lastMsg = newMessages[newMessages.length - 1];
          if (lastMsg?.isStreaming) {
            lastMsg.content = finalResponse.answer;
            lastMsg.citations = finalResponse.citations;
            lastMsg.isStreaming = false;
          }
          return newMessages;
        });
      } catch {
        // If not valid JSON, just show the raw text
        setMessages((prev) => {
          const newMessages = [...prev];
          const lastMsg = newMessages[newMessages.length - 1];
          if (lastMsg?.isStreaming) {
            lastMsg.isStreaming = false;
          }
          return newMessages;
        });
      }
    } catch (error) {
      console.error("Chat error:", error);
      setMessages((prev) => {
        const newMessages = [...prev];
        const lastMsg = newMessages[newMessages.length - 1];
        if (lastMsg?.isStreaming) {
          lastMsg.content = "Sorry, I encountered an error. Please try again.";
          lastMsg.isStreaming = false;
        }
        return newMessages;
      });
    } finally {
      setIsLoading(false);
      scrollToBottom();
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  const handleOverlayKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className={styles.overlay}
      onClick={handleOverlayClick}
      onKeyDown={handleOverlayKeyDown}
      role="button"
      tabIndex={0}
      aria-label="Close chat"
    >
      <div
        className={styles.chatContainer}
        role="dialog"
        aria-modal="true"
        aria-labelledby="lha-gpt-title"
      >
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerInfo}>
            <span className={styles.headerIcon}>🤖</span>
            <h2 id="lha-gpt-title">LHA-GPT</h2>
          </div>
          <button className={styles.closeButton} onClick={onClose}>
            ×
          </button>
        </div>

        {/* Messages */}
        <div className={styles.messagesContainer}>
          {messages.length === 0 && (
            <div className={styles.welcomeMessage}>
              <p>
                <strong>LHA-GPT</strong> can search through all of Linden&apos;s recorded memoirs
                and answer questions about his life growing up and working in Iowa and Canada.
              </p>
              <p className={styles.examplePrompts}>
                Try asking:
                <br />
                &quot;When was Lindy born?&quot;
                <br />
                &quot;What work did he do?&quot;
                <br />
                &quot;Tell me about moving to Canada&quot;
              </p>
            </div>
          )}

          {messages.map((msg, idx) => (
            <div
              key={idx}
              className={`${styles.message} ${
                msg.role === "user" ? styles.userMessage : styles.assistantMessage
              }`}
            >
              <div className={styles.messageContent}>
                {msg.content}
                {msg.isStreaming && <span className={styles.cursor}>▌</span>}
              </div>

              {msg.citations && msg.citations.length > 0 && (
                <div className={styles.citations}>
                  <span className={styles.citationsLabel}>Sources:</span>
                  {msg.citations
                    .filter((citation) => getRecordingRoute(citation.recording_id) !== null)
                    .map((citation, cidx) => {
                      const recording = getRecordingByPath(citation.recording_id);
                      return (
                        <button
                          key={cidx}
                          className={styles.citationButton}
                          onClick={() => handleCitationClick(citation)}
                          title={citation.quote_snippet}
                        >
                          📼 {recording?.title || citation.recording_id} @{" "}
                          {formatTimestamp(citation.timestamp)}
                        </button>
                      );
                    })}
                </div>
              )}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className={styles.inputContainer}>
          <textarea
            className={styles.input}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask about Lindy's life..."
            disabled={isLoading}
            rows={1}
          />
          <button
            className={styles.sendButton}
            onClick={sendMessage}
            disabled={isLoading || !input.trim()}
          >
            {isLoading ? "..." : "→"}
          </button>
        </div>
      </div>
    </div>
  );
};

export default LhaGpt;
