import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ChatError, getChat, sendChatMessage } from '../api'
import type { ChatMessage } from '../types'
import './ChatPanel.css'

interface ChatPanelProps {
  projectId: string
  open: boolean
  onClose: () => void
}

interface PendingMessage {
  content: string
  status: 'sending' | 'failed'
}

/** User Story 3's chat panel: loads the project's stored conversation once, lets the user send new
 * messages, and — per FR-013 — a failed send never discards existing history; it's shown as a
 * failed/retryable pending message instead. */
function ChatPanel({ projectId, open, onClose }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [pending, setPending] = useState<PendingMessage | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false

    getChat(projectId)
      .then((conversation) => {
        if (!cancelled) setMessages(conversation.messages)
      })
      .catch(() => {
        if (!cancelled) setLoadError('לא ניתן היה לטעון את השיחה')
      })

    return () => {
      cancelled = true
    }
  }, [projectId])

  useEffect(() => {
    if (open) {
      messagesEndRef.current?.scrollIntoView({ block: 'end' })
    }
  }, [open, messages, pending])

  async function send(content: string) {
    setPending({ content, status: 'sending' })
    try {
      const conversation = await sendChatMessage(projectId, content)
      setMessages(conversation.messages)
      setPending(null)
    } catch (error) {
      const message = error instanceof ChatError ? error.message : 'לא ניתן היה לשלוח את ההודעה'
      setPending({ content, status: 'failed' })
      setLoadError(null)
      // eslint-disable-next-line no-console
      console.error(message)
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = input.trim()
    if (!trimmed || pending?.status === 'sending') return
    setInput('')
    void send(trimmed)
  }

  function retry() {
    if (!pending) return
    void send(pending.content)
  }

  return (
    <div className={open ? 'chat-panel chat-panel--open' : 'chat-panel'} dir="rtl" aria-hidden={!open}>
      <div className="chat-panel__header">
        <h2>שיחה עם העוזר</h2>
        <button type="button" className="chat-panel__close" onClick={onClose} aria-label="סגור שיחה">
          ✕
        </button>
      </div>

      <div className="chat-panel__messages">
        {messages.length === 0 && !pending && !loadError && (
          <p className="chat-panel__empty">שאל/י את העוזר על הפרויקט שלך</p>
        )}
        {loadError && <p className="chat-panel__empty">{loadError}</p>}

        {messages.map((message, index) => (
          <div
            key={index}
            className={
              message.role === 'user'
                ? 'chat-panel__message chat-panel__message--user'
                : 'chat-panel__message chat-panel__message--assistant'
            }
          >
            {message.content}
          </div>
        ))}

        {pending && (
          <div
            className={
              pending.status === 'failed'
                ? 'chat-panel__message chat-panel__message--user chat-panel__message--failed'
                : 'chat-panel__message chat-panel__message--user chat-panel__message--pending'
            }
          >
            {pending.content}
            {pending.status === 'failed' && (
              <button type="button" className="chat-panel__retry" onClick={retry}>
                שליחה נכשלה — נסה/י שוב
              </button>
            )}
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <form className="chat-panel__form" onSubmit={handleSubmit}>
        <textarea
          className="chat-panel__input"
          rows={1}
          placeholder="כתוב/י הודעה..."
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              event.currentTarget.form?.requestSubmit()
            }
          }}
        />
        <button
          type="submit"
          className="chat-panel__send"
          disabled={!input.trim() || pending?.status === 'sending'}
        >
          שליחה
        </button>
      </form>
    </div>
  )
}

export default ChatPanel
