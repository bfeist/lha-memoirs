import React, { useState, useRef, useCallback, useEffect } from "react";
import styles from "./LhaGpt.module.css";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faCircleChevronRight, faRobot } from "@fortawesome/free-solid-svg-icons";
import ReactMarkdown from "react-markdown";
import { PlayableQuotation } from "./PlayableQuotation";

const STORAGE_KEY = "lha-gpt-chat-history";

interface Citation {
  recording_id: string;
  start_seconds: number;
  segment_count?: number; // Optional: AI can specify how many segments to play (defaults to 3)
}

interface Message {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  isStreaming?: boolean;
  thinking?: string;
}

// RAG API base URL - always use production proxy (works for local dev too)
const RAG_API_URL = "https://lindenhilaryachen-gpt.benfeist.com";

const LhaGpt: React.FC<{
  isOpen: boolean;
  onClose: () => void;
}> = ({ isOpen, onClose }) => {
  const [messages, setMessages] = useState<Message[]>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  });
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [expandedThinking, setExpandedThinking] = useState<Set<number>>(new Set());
  const [expandedCitations, setExpandedCitations] = useState<Set<number>>(new Set());
  const [serverOnline, setServerOnline] = useState(false); // Start pessimistic, set true on connect
  const [playingQuotationKey, setPlayingQuotationKey] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);

  // Persist messages to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    } catch (e) {
      console.error("Failed to save chat history:", e);
    }
  }, [messages]);

  // Monitor server health using persistent SSE connection
  useEffect(() => {
    if (!isOpen) return;

    let eventSource: EventSource | null = null;
    let reconnectTimeout: number | null = null;

    const connect = () => {
      try {
        eventSource = new EventSource(`${RAG_API_URL}/health/stream`);

        eventSource.onopen = () => {
          setServerOnline(true);
          // Clear any pending reconnect attempts
          if (reconnectTimeout) {
            clearTimeout(reconnectTimeout);
            reconnectTimeout = null;
          }
        };

        eventSource.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.status === "connected" || data.status === "alive") {
              setServerOnline(true);
            }
          } catch (e) {
            console.error("Failed to parse health event:", e);
          }
        };

        eventSource.onerror = () => {
          setServerOnline(false);
          eventSource?.close();

          // Attempt to reconnect after 5 seconds
          if (!reconnectTimeout) {
            reconnectTimeout = window.setTimeout(() => {
              reconnectTimeout = null;
              connect();
            }, 5000);
          }
        };
      } catch (error) {
        console.error("Failed to create EventSource:", error);
        setServerOnline(false);
      }
    };

    // Initial connection
    connect();

    return () => {
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
      }
      eventSource?.close();
    };
  }, [isOpen]);

  // Check if user is at the bottom of the messages
  const checkIfAtBottom = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return true;

    const threshold = 50; // pixels from bottom to consider "at bottom"
    const isAtBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight < threshold;
    isAtBottomRef.current = isAtBottom;
    return isAtBottom;
  }, []);

  const scrollToBottom = useCallback(() => {
    if (isAtBottomRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, []);

  const clearHistory = useCallback(() => {
    setMessages([]);
    setExpandedThinking(new Set());
    setExpandedCitations(new Set());
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  const toggleThinking = (messageIndex: number) => {
    // Stop auto-scrolling when user expands thinking
    isAtBottomRef.current = false;
    setExpandedThinking((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(messageIndex)) {
        newSet.delete(messageIndex);
      } else {
        newSet.add(messageIndex);
      }
      return newSet;
    });
  };

  const toggleCitations = (messageIndex: number) => {
    // Stop auto-scrolling when user expands citations
    isAtBottomRef.current = false;
    setExpandedCitations((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(messageIndex)) {
        newSet.delete(messageIndex);
      } else {
        newSet.add(messageIndex);
      }
      return newSet;
    });
  };

  /**
   * Post-process LLM response text to replace "the narrator" with "Lindy"
   * This ensures consistent naming since Lindy is the one speaking
   */
  const normalizeNarratorReferences = (text: string): string => {
    // Replace "the narrator" with "Lindy" (case-insensitive)
    return text.replace(/the narrator/gi, "Lindy");
  };

  /**
   * Remove inline citation markers from text and replace with paragraph breaks
   * Removes patterns like [Source: X, Time: Y] or [Source: X, Time: Y, Segments: N]
   */
  const removeCitationMarkers = (text: string): string => {
    // Replace citation markers with double newlines to maintain paragraph structure
    // Also remove any trailing period after the citation marker
    return text.replace(/\s*\[Source:\s*[^\]]+\]\s*\.?/g, "\n\n").trim();
  };

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage = input.trim();
    setInput("");
    setMessages((prev) => [...(prev || []), { role: "user", content: userMessage }]);
    setIsLoading(true);

    // Re-enable auto-scroll when user sends a message
    isAtBottomRef.current = true;

    // User is sending a message, ensure we're at the bottom
    isAtBottomRef.current = true;

    // Add placeholder for streaming response
    setMessages((prev) => [...prev, { role: "assistant", content: "", isStreaming: true }]);

    try {
      const response = await fetch(`${RAG_API_URL}/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query: userMessage }),
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
      let accumulatedThinking = "";
      let citations: Citation[] = [];

      const updateStreamingMessage = (text: string, thinking?: string, cites?: Citation[]) => {
        setMessages((prev) => {
          const newMessages = [...prev];
          const lastMsg = newMessages[newMessages.length - 1];
          if (lastMsg?.isStreaming) {
            lastMsg.content = text;
            if (thinking !== undefined) {
              lastMsg.thinking = thinking;
            }
            if (cites) {
              lastMsg.citations = cites;
            }
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

        // Parse SSE data
        const lines = accumulatedData.split("\n");
        accumulatedData = lines.pop() || ""; // Keep incomplete line

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const jsonStr = line.slice(6).trim();
            if (jsonStr && jsonStr !== "[DONE]") {
              try {
                const data = JSON.parse(jsonStr);

                if (data.type === "text" && data.content) {
                  accumulatedText += data.content;
                  // Normalize narrator references and remove citation markers as we stream
                  const cleanedText = removeCitationMarkers(
                    normalizeNarratorReferences(accumulatedText)
                  );
                  updateStreamingMessage(cleanedText, accumulatedThinking);
                } else if (data.type === "thinking" && data.content) {
                  accumulatedThinking += data.content;
                  const cleanedText = removeCitationMarkers(
                    normalizeNarratorReferences(accumulatedText)
                  );
                  updateStreamingMessage(cleanedText, accumulatedThinking);
                } else if (data.type === "citations" && data.citations) {
                  citations = data.citations;
                  const cleanedText = removeCitationMarkers(
                    normalizeNarratorReferences(accumulatedText)
                  );
                  updateStreamingMessage(cleanedText, accumulatedThinking, citations);
                } else if (data.type === "error") {
                  throw new Error(data.content || "Unknown error");
                }
              } catch (e) {
                // Continue accumulating if JSON is incomplete
                if (e instanceof SyntaxError) {
                  continue;
                }
                throw e;
              }
            }
          }
        }
      }

      // Finalize the message
      setMessages((prev) => {
        const newMessages = [...prev];
        const lastMsg = newMessages[newMessages.length - 1];
        if (lastMsg?.isStreaming) {
          lastMsg.isStreaming = false;
          if (!lastMsg.citations && citations.length > 0) {
            lastMsg.citations = citations;
          }
        }
        return newMessages;
      });
    } catch (error) {
      console.error("Chat error:", error);
      setMessages((prev) => {
        const newMessages = [...prev];
        const lastMsg = newMessages[newMessages.length - 1];
        if (lastMsg?.isStreaming) {
          const errorMessage = error instanceof Error ? error.message : "Unknown error";
          lastMsg.content = `Sorry, I encountered an error: ${errorMessage}. Make sure the RAG server is running on ${RAG_API_URL}`;
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

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div className={styles.overlay} onKeyDown={handleKeyDown} role="presentation">
      <div
        className={styles.chatContainer}
        role="dialog"
        aria-modal="true"
        aria-labelledby="lha-gpt-title"
      >
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerInfo}>
            <span className={styles.headerIcon}>
              <FontAwesomeIcon icon={faRobot} />
            </span>
            <h2 id="lha-gpt-title">LHA-GPT</h2>
          </div>
          <div className={styles.headerButtons}>
            {messages.length > 0 && (
              <button
                className={styles.clearButton}
                onClick={clearHistory}
                title="Clear chat history"
              >
                🗑️ Clear
              </button>
            )}
            <button className={styles.closeButton} onClick={onClose}>
              ×
            </button>
          </div>
        </div>

        {/* Messages */}
        <div
          className={styles.messagesContainer}
          ref={messagesContainerRef}
          onScroll={checkIfAtBottom}
        >
          {!serverOnline && (
            <div className={styles.offlineWarning}>
              The AI server is currently offline.
              <br /> Text Ben and ask him to turn it on for you.
            </div>
          )}

          {messages.length === 0 && (
            <div className={styles.welcomeMessage}>
              <div className={styles.welcomeHeader}>
                <div className={styles.welcomeTitle}>
                  <span className={styles.welcomeIcon}>
                    <FontAwesomeIcon icon={faRobot} />
                  </span>
                  <h3>Welcome to LHA-GPT</h3>
                </div>
                <span className={styles.experimentalBadge}>Experimental</span>
              </div>

              <p className={styles.welcomeDescription}>
                Ask questions about Linden&apos;s life and I&apos;ll search through all of his
                recorded memoirs to find answers. I can tell you about his childhood in Iowa, his
                work across the Midwest and Canada, and the stories he shared.
              </p>

              <div className={styles.examplePrompts}>
                <p className={styles.promptsLabel}>Try asking:</p>
                <ul className={styles.promptsList}>
                  <li>&quot;When was Lindy born?&quot;</li>
                  <li>&quot;What was his brother, Zip like?&quot;</li>
                  <li>&quot;Tell me about moving to Canada&quot;</li>
                  <li>&quot;Tell me about his Model T Ford&quot;</li>
                </ul>
              </div>
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
                {msg.role === "assistant" ? (
                  <>
                    {msg.thinking && (
                      <div className={styles.thinkingSection}>
                        <button
                          className={styles.thinkingToggle}
                          onClick={() => toggleThinking(idx)}
                          aria-expanded={expandedThinking.has(idx)}
                        >
                          {expandedThinking.has(idx) ? "▼" : "▶"}{" "}
                          {msg.content ? "Thinking" : "Thinking ..."}
                        </button>
                        {expandedThinking.has(idx) && (
                          <div className={styles.thinkingContent}>{msg.thinking}</div>
                        )}
                      </div>
                    )}
                    <div className={styles.markdown}>
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                      {msg.isStreaming && <span className={styles.loader} aria-hidden="true" />}
                    </div>
                    {msg.citations && msg.citations.length > 0 && (
                      <div className={styles.citationsSection}>
                        <button
                          className={styles.citationsToggle}
                          onClick={() => toggleCitations(idx)}
                          aria-expanded={expandedCitations.has(idx)}
                        >
                          {expandedCitations.has(idx) ? "▼" : "▶"} Citations ({msg.citations.length}
                          )
                        </button>
                        {expandedCitations.has(idx) && (
                          <div className={styles.citationsContent}>
                            {msg.citations.map((citation, citationIdx) => {
                              const citationKey = `msg-${idx}-cite-${citationIdx}`;
                              return (
                                <PlayableQuotation
                                  key={citationKey}
                                  recordingId={citation.recording_id}
                                  startSeconds={citation.start_seconds}
                                  segmentCount={citation.segment_count}
                                  onPlay={() => setPlayingQuotationKey(citationKey)}
                                  shouldStop={
                                    playingQuotationKey !== null &&
                                    playingQuotationKey !== citationKey
                                  }
                                  onNavigate={onClose}
                                />
                              );
                            })}
                          </div>
                        )}
                      </div>
                    )}
                  </>
                ) : (
                  msg.content
                )}
              </div>
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
            {isLoading ? "..." : <FontAwesomeIcon icon={faCircleChevronRight} />}
          </button>
        </div>
      </div>
    </div>
  );
};

export default LhaGpt;
