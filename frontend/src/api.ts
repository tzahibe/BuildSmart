import type { Conversation, Project, ProjectCreatePayload } from './types'

/** Thrown by parseRequirements/generateDesign when the pipeline step fails — carries a user-facing
 * Hebrew message so the loading screen can show it directly (see design/LoadingScreen.tsx). */
export class PipelineStepError extends Error {}

/** Thrown by sendChatMessage when the request fails — carries a user-facing Hebrew message so
 * ChatPanel can show a per-message retry state without losing the rest of the conversation
 * (contracts/chat-api.md: nothing is persisted server-side on failure either). */
export class ChatError extends Error {}

/** Raw `POST /projects` call — status-code handling (201/422/other) stays in App.tsx, which already has
 * the field-level Hebrew error-message logic for this specific endpoint. */
export function createProject(payload: ProjectCreatePayload): Promise<Response> {
  return fetch('/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function parseRequirements(projectId: string): Promise<Project> {
  const response = await fetch(`/projects/${projectId}/requirements`, { method: 'POST' })
  if (!response.ok) {
    throw new PipelineStepError('לא ניתן היה לנתח את דרישות הפרויקט')
  }
  return (await response.json()) as Project
}

export async function generateDesign(projectId: string): Promise<Project> {
  const response = await fetch(`/projects/${projectId}/design`, { method: 'POST' })
  if (!response.ok) {
    throw new PipelineStepError('לא ניתן היה ליצור סקיצה עבור הפרויקט')
  }
  return (await response.json()) as Project
}

export async function getChat(projectId: string): Promise<Conversation> {
  const response = await fetch(`/projects/${projectId}/chat`)
  if (!response.ok) {
    throw new ChatError('לא ניתן היה לטעון את השיחה')
  }
  return (await response.json()) as Conversation
}

export async function sendChatMessage(projectId: string, content: string): Promise<Conversation> {
  const response = await fetch(`/projects/${projectId}/chat/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  if (!response.ok) {
    const message =
      response.status === 502
        ? 'העוזר אינו זמין כרגע, נסה/י שוב'
        : 'לא ניתן היה לשלוח את ההודעה'
    throw new ChatError(message)
  }
  return (await response.json()) as Conversation
}
