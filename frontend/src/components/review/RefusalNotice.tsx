import './RefusalNotice.css'

/** A REFUSAL, SHOWN AS ONE (Issue #63). `code` and `message` are exactly what
 * `DemoPipelineError` carries from the backend (`api.ts`) — the machine code a support
 * conversation can look up, and the human sentence written for whoever asked for the house. This
 * replaces a generic "something went wrong" with the backend's own, specific answer. */
function RefusalNotice({ code, message, detail }: { code: string; message: string; detail?: string }) {
  return (
    <div className="refusal-notice" role="alert">
      <strong className="refusal-notice-message">{message}</strong>
      <span className="refusal-notice-code">קוד: {code}</span>
      {detail ? <span className="refusal-notice-detail">{detail}</span> : null}
    </div>
  )
}

export default RefusalNotice
