import { useEffect, useRef, useState, type FormEvent } from 'react'
import { cancelProposal, ChatError, confirmProposal, getChat, ProposalError, sendChatMessage } from '../api'
import type { ChatMessage, Project } from '../types'
import './ChatPanel.css'

interface ChatPanelProps {
  projectId: string
  open: boolean
  onClose: () => void
  // Called with the FULL updated Project after a confirmed proposal actually mutates it — the caller
  // (DesignPage -> App) replaces its Project wholesale, exactly like SettingsPage's onUpdated. This is
  // what keeps Settings and the design view in sync with whatever Chat just did, with no separate
  // frontend copy of project state anywhere.
  onProjectUpdated: (project: Project) => void
}

interface PendingMessage {
  content: string
  status: 'sending' | 'failed'
}

/** User Story 3's chat panel: loads the project's stored conversation once, lets the user send new
 * messages, and — per FR-013 — a failed send never discards existing history; it's shown as a
 * failed/retryable pending message instead. */
function ChatPanel({ projectId, open, onClose, onProjectUpdated }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [pending, setPending] = useState<PendingMessage | null>(null)
  const [proposalError, setProposalError] = useState<string | null>(null)
  const [resolvingProposal, setResolvingProposal] = useState(false)
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

  async function resolveProposal(proposalId: string, action: 'confirm' | 'cancel') {
    setResolvingProposal(true)
    setProposalError(null)
    try {
      const result = action === 'confirm' ? await confirmProposal(projectId, proposalId) : await cancelProposal(projectId, proposalId)
      setMessages(result.conversation.messages)
      if (result.project) {
        onProjectUpdated(result.project)
      }
    } catch (error) {
      setProposalError(error instanceof ProposalError ? error.message : 'לא ניתן היה לעדכן את ההצעה')
    } finally {
      setResolvingProposal(false)
    }
  }

  // Only the LAST message can ever be an actionable pending proposal — confirming/canceling always
  // appends a new outcome message with no `proposal`, and a newer proposal always supersedes an older
  // one server-side, so there is nothing to track beyond "is the most recent message one?" (checked
  // per-message below via `isLast`).

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

        {messages.map((message, index) => {
          const isLast = index === messages.length - 1
          const showProposalActions = isLast && message.proposal !== null
          return (
            <div
              key={index}
              className={
                message.role === 'user'
                  ? 'chat-panel__message chat-panel__message--user'
                  : 'chat-panel__message chat-panel__message--assistant'
              }
            >
              {message.content}
              {showProposalActions && message.proposal && (
                <div className="chat-panel__proposal-actions">
                  <button
                    type="button"
                    className="chat-panel__proposal-confirm"
                    disabled={resolvingProposal}
                    onClick={() => void resolveProposal(message.proposal!.proposal_id, 'confirm')}
                  >
                    אישור
                  </button>
                  <button
                    type="button"
                    className="chat-panel__proposal-cancel"
                    disabled={resolvingProposal}
                    onClick={() => void resolveProposal(message.proposal!.proposal_id, 'cancel')}
                  >
                    ביטול
                  </button>
                </div>
              )}
            </div>
          )
        })}

        {proposalError && <p className="chat-panel__proposal-error">{proposalError}</p>}

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
