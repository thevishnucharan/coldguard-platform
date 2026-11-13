import { Dialog, DialogPanel, DialogTitle } from '@headlessui/react'
import { X } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { cx } from '../../utils/format'

export function Modal({ open, onClose, title, description, children, footer, size = 'md' }: {
  open: boolean; onClose: () => void; title: ReactNode; description?: ReactNode; children?: ReactNode
  footer?: ReactNode; size?: 'sm' | 'md' | 'lg'
}) {
  return (
    <Dialog open={open} onClose={onClose} className="relative z-50">
      <div className="fixed inset-0 bg-navy-950/40" aria-hidden="true" />
      <div className="fixed inset-0 flex items-start sm:items-center justify-center p-4 overflow-y-auto">
        <DialogPanel className={cx('card w-full shadow-xl', { sm: 'max-w-md', md: 'max-w-lg', lg: 'max-w-3xl' }[size])}>
          <div className="flex items-start justify-between gap-3 px-5 pt-4">
            <div>
              <DialogTitle className="text-[15px] font-semibold text-ink">{title}</DialogTitle>
              {description && <p className="text-xs text-ink-3 mt-1">{description}</p>}
            </div>
            <button onClick={onClose} className="btn-ghost btn-sm -mr-2" aria-label="Close"><X size={16} /></button>
          </div>
          <div className="px-5 py-4">{children}</div>
          {footer && <div className="flex justify-end gap-2 px-5 py-3 border-t border-line bg-canvas/50 rounded-b-xl">{footer}</div>}
        </DialogPanel>
      </div>
    </Dialog>
  )
}

/** Confirmation with optional required reason text (captured into the audit trail by the API). */
export function ConfirmDialog({ open, onClose, onConfirm, title, description, confirmLabel = 'Confirm', danger,
  reasonLabel, reasonRequired, minReason = 0, typeToConfirm }: {
  open: boolean; onClose: () => void; onConfirm: (reason: string) => Promise<void> | void; title: string
  description?: ReactNode; confirmLabel?: string; danger?: boolean; reasonLabel?: string; reasonRequired?: boolean
  minReason?: number; typeToConfirm?: string
}) {
  const [reason, setReason] = useState('')
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const invalid = (reasonRequired && reason.trim().length < Math.max(1, minReason)) || (typeToConfirm && typed !== typeToConfirm)
  const close = () => { setReason(''); setTyped(''); onClose() }
  return (
    <Modal open={open} onClose={close} title={title} description={description} size="sm"
      footer={<>
        <button className="btn-secondary" onClick={close} disabled={busy}>Cancel</button>
        <button className={danger ? 'btn-danger' : 'btn-primary'} disabled={!!invalid || busy}
          onClick={async () => { setBusy(true); try { await onConfirm(reason.trim()); close() } finally { setBusy(false) } }}>
          {busy ? 'Working…' : confirmLabel}
        </button>
      </>}>
      {reasonLabel && (
        <div>
          <label className="label">{reasonLabel}{reasonRequired && ' *'}</label>
          <textarea className="input h-24 py-2" value={reason} onChange={(e) => setReason(e.target.value)} />
          {minReason > 0 && <p className="text-[11px] text-ink-3 mt-1">Minimum {minReason} characters.</p>}
        </div>
      )}
      {typeToConfirm && (
        <div className="mt-3">
          <label className="label">Type <span className="mono font-semibold">{typeToConfirm}</span> to confirm</label>
          <input className="input" value={typed} onChange={(e) => setTyped(e.target.value)} />
        </div>
      )}
    </Modal>
  )
}
