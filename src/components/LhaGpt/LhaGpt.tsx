import React, { useState, useRef, useCallback, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import { getRecordingByPath, getRecordingById } from "../../config/recordings";
import styles from "./LhaGpt.module.css";

const STORAGE_KEY = "lha-gpt-chat-history";

interface Citation {
  recording_id: string;
  timestamp: number;
  quote_snippet: string;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  isStreaming?: boolean;
  thinking?: string;
}

// RAG API base URL - configurable via environment variable
const RAG_API_URL = import.meta.env.VITE_RAG_API_URL || "http://localhost:8000";

// Map recording_id (folder path or ID) to recording route ID using recordings.ts
function getRecordingRoute(recordingId: string): string | null {
  // First try lookup by ID
  const recordingById = getRecordingById(recordingId);
  if (recordingById) return recordingById.id;

  // Fallback to path lookup
  const recording = getRecordingByPath(recordingId);
  if (!recording) {
    console.warn(`Unknown recording_id: ${recordingId} - citation may be hallucinated`);
    return null;
  }
  return recording.id;
}

// Parse time from MM:SS format to seconds
function parseTimeToSeconds(timeStr: string): number {
  const parts = timeStr.split(":");
  if (parts.length === 2) {
    const mins = parseInt(parts[0], 10);
    const secs = parseInt(parts[1], 10);
    return mins * 60 + secs;
  }
  return 0;
}

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
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);
  const navigate = useNavigate();

  // Persist messages to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    } catch (e) {
      console.error("Failed to save chat history:", e);
    }
  }, [messages]);

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
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  const handleInlineSourceClick = (source: string, timeStr: string) => {
    const recordingId = getRecordingRoute(source);
    if (!recordingId) {
      return;
    }
    const seconds = parseTimeToSeconds(timeStr);
    navigate(`/recording/${recordingId}?t=${seconds}`);
    onClose();
  };

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

  // Helper to process children and replace source text with buttons
  const processCitationText = (children: React.ReactNode): React.ReactNode => {
    return React.Children.map(children, (child) => {
      if (typeof child !== "string") {
        return child;
      }

      const parts: (string | React.ReactElement)[] = [];
      let lastIndex = 0;
      const regex = /\[Source:\s*([^,]+),\s*Time:\s*(\d+:\d+)\]/g;
      let match;
      let matchCount = 0;

      while ((match = regex.exec(child)) !== null) {
        if (match.index > lastIndex) {
          parts.push(child.slice(lastIndex, match.index));
        }

        const source = match[1].trim();
        const timeStr = match[2];
        // Try to find recording by ID first, then Path
        const recording = getRecordingById(source) || getRecordingByPath(source);

        if (recording) {
          parts.push(
            <button
              key={`inline-cite-${matchCount}-${lastIndex}`}
              className={styles.inlineCitation}
              onClick={() => handleInlineSourceClick(source, timeStr)}
              title={`Source: ${recording.title} (Time: ${timeStr})`}
              aria-label={`Source: ${recording.title} at ${timeStr}`}
            >
              🔗
            </button>
          );
        } else {
          parts.push(match[0]);
        }

        matchCount++;
        lastIndex = regex.lastIndex;
      }

      if (lastIndex < child.length) {
        parts.push(child.slice(lastIndex));
      }

      return parts.length > 0 ? parts : child;
    });
  };

  const components = {
    p: ({ children, ...props }: React.HTMLAttributes<HTMLParagraphElement>) => (
      <p {...props}>{processCitationText(children)}</p>
    ),
    li: ({ children, ...props }: React.LiHTMLAttributes<HTMLLIElement>) => (
      <li {...props}>{processCitationText(children)}</li>
    ),
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
                  updateStreamingMessage(accumulatedText, accumulatedThinking);
                } else if (data.type === "thinking" && data.content) {
                  accumulatedThinking += data.content;
                  updateStreamingMessage(accumulatedText, accumulatedThinking);
                } else if (data.type === "citations" && data.citations) {
                  citations = data.citations;
                  updateStreamingMessage(accumulatedText, accumulatedThinking, citations);
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
            <span className={styles.headerIcon}>🤖</span>
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
          {messages.length === 0 && (
            <div className={styles.welcomeMessage}>
              <div className={styles.welcomeHeader}>
                <span className={styles.welcomeIcon}>🤖</span>
                <h3>Welcome to LHA-GPT</h3>
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
                  <li>&quot;What work did he do?&quot;</li>
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
                          {expandedThinking.has(idx) ? "▼" : "▶"} Thinking process
                        </button>
                        {expandedThinking.has(idx) && (
                          <div className={styles.thinkingContent}>{msg.thinking}</div>
                        )}
                      </div>
                    )}
                    <div className={styles.markdown}>
                      <ReactMarkdown components={components}>{msg.content}</ReactMarkdown>
                      {msg.isStreaming && <span className={styles.cursor}>▌</span>}
                    </div>
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
            {isLoading ? "..." : "→"}
          </button>
        </div>
      </div>
    </div>
  );
};

export default LhaGpt;
