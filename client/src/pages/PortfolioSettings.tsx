import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useAppStore } from '../store'
import {
  getPortfolios, createPortfolio, updatePortfolio, deletePortfolio,
  getPortfolioMembers, inviteMember, updateMemberRole, removeMember,
} from '../api/portfolio'
import type { Portfolio, PortfolioMember } from '../types'
import clsx from 'clsx'

const INPUT = 'w-full px-3 py-2 text-[13px] border border-gray-200 rounded-lg focus:outline-none focus:border-teal-400 bg-white text-gray-800'
const BTN_PRIMARY = 'px-4 py-2 text-[13px] font-medium bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:opacity-40 transition-colors'
const BTN_GHOST = 'px-4 py-2 text-[13px] font-medium text-gray-600 rounded-lg hover:bg-gray-100 transition-colors'

type Tab = 'general' | 'members'

export default function PortfolioSettings() {
  const { t } = useTranslation('settings')
  const [activeTab, setActiveTab] = useState<Tab>('general')

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      <h1 className="text-[22px] font-semibold text-gray-900 mb-6">{t('title')}</h1>

      <div className="flex gap-1 p-1 bg-gray-100 rounded-xl mb-8 w-fit">
        {(['general', 'members'] as Tab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={clsx(
              'px-5 py-2 rounded-lg text-[13px] font-medium transition-colors',
              activeTab === tab
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700',
            )}
          >
            {t(`tabs.${tab}`)}
          </button>
        ))}
      </div>

      {activeTab === 'general' ? <GeneralTab /> : <MembersTab />}
    </div>
  )
}

// ─── General Tab ──────────────────────────────────────────────────────────────

function GeneralTab() {
  const { t } = useTranslation('settings')
  const { t: tc } = useTranslation('common')
  const qc = useQueryClient()
  const activeId = useAppStore((s) => s.activePortfolioId)
  const setActivePortfolioId = useAppStore((s) => s.setActivePortfolioId)

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [showNewForm, setShowNewForm] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<Portfolio | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const { data: portfolios = [] } = useQuery({
    queryKey: ['portfolios'],
    queryFn: getPortfolios,
  })

  const selected = portfolios.find((p) => p.id === selectedId) ?? null

  const createMutation = useMutation({
    mutationFn: createPortfolio,
    onSuccess: (newP) => {
      qc.invalidateQueries({ queryKey: ['portfolios'] })
      setShowNewForm(false)
      setSelectedId(newP.id)
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof updatePortfolio>[1] }) =>
      updatePortfolio(id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portfolios'] }),
  })

  const deleteMutation = useMutation({
    mutationFn: deletePortfolio,
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ['portfolios'] })
      setDeleteTarget(null)
      setDeleteError(null)
      if (selectedId === id) setSelectedId(null)
      if (activeId === id) {
        const next = portfolios.find((p) => p.id !== id)
        if (next) {
          setActivePortfolioId(next.id)
          localStorage.setItem('last_portfolio_id', next.id)
        }
      }
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setDeleteError(msg ?? tc('errors.generic'))
    },
  })

  return (
    <div className="space-y-6">
      {/* Portfolio list */}
      <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <p className="text-[13px] font-semibold text-gray-700">{t('portfolio.my_portfolios')}</p>
          <button
            onClick={() => { setShowNewForm(true); setSelectedId(null) }}
            className="text-[12px] font-medium text-teal-600 hover:text-teal-700 transition-colors"
          >
            {t('portfolio.new_portfolio')}
          </button>
        </div>

        {portfolios.length === 0 ? (
          <p className="px-5 py-6 text-[13px] text-gray-400 text-center">{t('portfolio.no_portfolios')}</p>
        ) : (
          <ul>
            {portfolios.map((p) => (
              <li
                key={p.id}
                className={clsx(
                  'flex items-center gap-3 px-5 py-3.5 border-b border-gray-50 last:border-0 cursor-pointer transition-colors',
                  selectedId === p.id ? 'bg-teal-50' : 'hover:bg-gray-50',
                )}
                onClick={() => { setSelectedId(p.id); setShowNewForm(false) }}
              >
                <span className={clsx(
                  'w-3.5 h-3.5 rounded-full border-2 flex-shrink-0 transition-colors',
                  selectedId === p.id ? 'border-teal-500 bg-teal-500' : 'border-gray-300',
                )} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[13px] font-medium text-gray-800 truncate">{p.name}</span>
                    <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">
                      {p.base_currency}
                    </span>
                    {p.owner_id && (
                      <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-teal-50 text-teal-600">
                        {t('portfolio.owner_badge')}
                      </span>
                    )}
                  </div>
                  {p.description && (
                    <p className="text-[11px] text-gray-400 truncate mt-0.5">{p.description}</p>
                  )}
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); setDeleteTarget(p); setDeleteError(null); deleteMutation.reset() }}
                  className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors flex-shrink-0"
                >
                  <IconTrash />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* New portfolio form */}
      {showNewForm && (
        <NewPortfolioForm
          onSubmit={(payload) => createMutation.mutate(payload)}
          onCancel={() => setShowNewForm(false)}
          isPending={createMutation.isPending}
        />
      )}

      {/* Edit form */}
      {selected && !showNewForm && (
        <EditPortfolioForm
          key={selected.id}
          portfolio={selected}
          onSubmit={(payload) => updateMutation.mutate({ id: selected.id, payload })}
          isPending={updateMutation.isPending}
          isSuccess={updateMutation.isSuccess}
        />
      )}

      {!selected && !showNewForm && portfolios.length > 0 && (
        <p className="text-[12px] text-gray-400 text-center py-2">{t('portfolio.select_to_edit')}</p>
      )}

      {/* Delete confirmation */}
      {deleteTarget && (
        <ConfirmDialog
          title={t('portfolio.delete_confirm_title')}
          message={deleteError ?? t('portfolio.delete_confirm', { name: deleteTarget.name })}
          isDestructive={!deleteError}
          isPending={deleteMutation.isPending}
          onConfirm={deleteError ? undefined : () => deleteMutation.mutate(deleteTarget.id)}
          onCancel={() => { setDeleteTarget(null); setDeleteError(null); deleteMutation.reset() }}
          confirmLabel={t('portfolio.delete')}
        />
      )}
    </div>
  )
}

function NewPortfolioForm({
  onSubmit,
  onCancel,
  isPending,
}: {
  onSubmit: (p: { name: string; base_currency: string; description?: string }) => void
  onCancel: () => void
  isPending: boolean
}) {
  const { t } = useTranslation('settings')
  const { t: tc } = useTranslation('common')
  const [name, setName] = useState('')
  const [currency, setCurrency] = useState('ILS')
  const [description, setDescription] = useState('')

  return (
    <div className="bg-white border border-teal-200 rounded-2xl p-5 space-y-4">
      <p className="text-[13px] font-semibold text-gray-700">{t('portfolio.new_portfolio')}</p>
      <FormField label={t('portfolio.name')} required>
        <input value={name} onChange={(e) => setName(e.target.value)}
          placeholder={t('portfolio.name_placeholder')} className={INPUT} />
      </FormField>
      <FormField label={t('portfolio.currency')}>
        <CurrencySelect value={currency} onChange={setCurrency} />
      </FormField>
      <FormField label={t('portfolio.description')}>
        <input value={description} onChange={(e) => setDescription(e.target.value)}
          placeholder={t('portfolio.description_placeholder')} className={INPUT} />
      </FormField>
      <div className="flex gap-2 pt-1">
        <button disabled={!name.trim() || isPending}
          onClick={() => onSubmit({ name: name.trim(), base_currency: currency, description: description || undefined })}
          className={BTN_PRIMARY}>
          {isPending ? tc('actions.saving') : t('portfolio.create')}
        </button>
        <button onClick={onCancel} className={BTN_GHOST}>{t('portfolio.cancel')}</button>
      </div>
    </div>
  )
}

function EditPortfolioForm({
  portfolio,
  onSubmit,
  isPending,
  isSuccess,
}: {
  portfolio: Portfolio
  onSubmit: (p: { name?: string; base_currency?: string; description?: string }) => void
  isPending: boolean
  isSuccess: boolean
}) {
  const { t } = useTranslation('settings')
  const { t: tc } = useTranslation('common')
  const [name, setName] = useState(portfolio.name)
  const [currency, setCurrency] = useState(portfolio.base_currency)
  const [description, setDescription] = useState(portfolio.description ?? '')

  const dirty = name !== portfolio.name || currency !== portfolio.base_currency
    || description !== (portfolio.description ?? '')

  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-5 space-y-4">
      <p className="text-[13px] font-semibold text-gray-700">{portfolio.name}</p>
      <FormField label={t('portfolio.name')} required>
        <input value={name} onChange={(e) => setName(e.target.value)}
          placeholder={t('portfolio.name_placeholder')} className={INPUT} />
      </FormField>
      <FormField label={t('portfolio.currency')}>
        <CurrencySelect value={currency} onChange={setCurrency} />
      </FormField>
      <FormField label={t('portfolio.description')}>
        <textarea value={description} onChange={(e) => setDescription(e.target.value)}
          placeholder={t('portfolio.description_placeholder')} rows={2}
          className={`${INPUT} resize-none`} />
      </FormField>
      <div className="flex items-center gap-3 pt-1">
        <button disabled={!name.trim() || !dirty || isPending}
          onClick={() => onSubmit({ name: name.trim(), base_currency: currency, description: description || undefined })}
          className={BTN_PRIMARY}>
          {isPending ? tc('actions.saving') : t('portfolio.save')}
        </button>
        {isSuccess && !dirty && (
          <span className="text-[12px] text-teal-600">{tc('status.success')} ✓</span>
        )}
      </div>
    </div>
  )
}

// ─── Members Tab ──────────────────────────────────────────────────────────────

function MembersTab() {
  const { t } = useTranslation('settings')
  const qc = useQueryClient()
  const activeId = useAppStore((s) => s.activePortfolioId)

  const [portfolioId, setPortfolioId] = useState<string>(activeId ?? '')
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState<'viewer' | 'editor'>('viewer')
  const [inviteError, setInviteError] = useState<string | null>(null)
  const [inviteSuccess, setInviteSuccess] = useState<string | null>(null)
  const [removeTarget, setRemoveTarget] = useState<PortfolioMember | null>(null)

  const { data: portfolios = [] } = useQuery({
    queryKey: ['portfolios'],
    queryFn: getPortfolios,
  })

  const { data: members = [] } = useQuery({
    queryKey: ['portfolio-members', portfolioId],
    queryFn: () => getPortfolioMembers(portfolioId),
    enabled: !!portfolioId,
  })

  const inviteMutation = useMutation({
    mutationFn: ({ email, role }: { email: string; role: string }) =>
      inviteMember(portfolioId, email, role),
    onSuccess: (_, { email }) => {
      qc.invalidateQueries({ queryKey: ['portfolio-members', portfolioId] })
      setInviteEmail('')
      setInviteError(null)
      setInviteSuccess(t('members.invite_sent', { email }))
      setTimeout(() => setInviteSuccess(null), 4000)
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setInviteError(msg ?? 'Error sending invitation')
    },
  })

  const roleMutation = useMutation({
    mutationFn: ({ memberId, role }: { memberId: string; role: string }) =>
      updateMemberRole(portfolioId, memberId, role),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portfolio-members', portfolioId] }),
  })

  const removeMutation = useMutation({
    mutationFn: (memberId: string) => removeMember(portfolioId, memberId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portfolio-members', portfolioId] })
      setRemoveTarget(null)
    },
  })

  const selectedPortfolio = portfolios.find((p) => p.id === portfolioId)
  const isOwner = !!selectedPortfolio?.owner_id

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
          {t('members.select_portfolio')}
        </label>
        <select value={portfolioId} onChange={(e) => setPortfolioId(e.target.value)}
          className={`${INPUT} max-w-xs`}>
          {portfolios.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </div>

      {portfolioId && (
        <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100">
            <p className="text-[13px] font-semibold text-gray-700">{t('members.title')}</p>
          </div>
          {members.length === 0 ? (
            <p className="px-5 py-6 text-[13px] text-gray-400 text-center">{t('members.no_members')}</p>
          ) : (
            <ul>
              {members.map((m) => (
                <MemberRow
                  key={m.id}
                  member={m}
                  isOwner={isOwner}
                  onRoleChange={(role) => roleMutation.mutate({ memberId: m.id, role })}
                  onRemove={() => setRemoveTarget(m)}
                />
              ))}
            </ul>
          )}
        </div>
      )}

      {portfolioId && isOwner && (
        <div className="bg-white border border-gray-200 rounded-2xl p-5 space-y-4">
          <p className="text-[13px] font-semibold text-gray-700">{t('members.invite_title')}</p>
          <div className="flex gap-3 flex-wrap">
            <div className="flex-1 min-w-[200px]">
              <FormField label={t('members.email')}>
                <input type="email" value={inviteEmail}
                  onChange={(e) => { setInviteEmail(e.target.value); setInviteError(null) }}
                  placeholder={t('members.email_placeholder')} className={INPUT} />
              </FormField>
            </div>
            <div>
              <FormField label={t('members.role')}>
                <select value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as 'viewer' | 'editor')}
                  className={INPUT}>
                  <option value="viewer">{t('members.roles.viewer')}</option>
                  <option value="editor">{t('members.roles.editor')}</option>
                </select>
              </FormField>
            </div>
          </div>
          <p className="text-[11px] text-gray-400">{t(`members.role_descriptions.${inviteRole}`)}</p>
          <div className="flex items-center gap-3">
            <button
              disabled={!inviteEmail.trim() || inviteMutation.isPending}
              onClick={() => inviteMutation.mutate({ email: inviteEmail.trim(), role: inviteRole })}
              className={BTN_PRIMARY}>
              {inviteMutation.isPending ? '…' : t('members.send_invite')}
            </button>
            {inviteError && <p className="text-[12px] text-red-500">{inviteError}</p>}
            {inviteSuccess && <p className="text-[12px] text-teal-600">{inviteSuccess}</p>}
          </div>
        </div>
      )}

      {removeTarget && (
        <ConfirmDialog
          title={t('members.remove_confirm_title')}
          message={t('members.remove_confirm', { email: removeTarget.email ?? removeTarget.user_id ?? '?' })}
          isDestructive
          isPending={removeMutation.isPending}
          onConfirm={() => removeMutation.mutate(removeTarget.id)}
          onCancel={() => setRemoveTarget(null)}
          confirmLabel={t('members.remove')}
        />
      )}
    </div>
  )
}

function MemberRow({
  member,
  isOwner,
  onRoleChange,
  onRemove,
}: {
  member: PortfolioMember
  isOwner: boolean
  onRoleChange: (role: string) => void
  onRemove: () => void
}) {
  const { t } = useTranslation('settings')
  const [showActions, setShowActions] = useState(false)
  const displayName = member.email ?? member.user_id ?? '?'
  const isAccepted = !!member.accepted_at

  return (
    <li className="flex items-center gap-3 px-5 py-3.5 border-b border-gray-50 last:border-0">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[13px] text-gray-800 truncate">{displayName}</span>
          <RoleBadge role={member.role} t={t} />
          <StatusBadge accepted={isAccepted} t={t} />
        </div>
      </div>
      {isOwner && member.role !== 'owner' && (
        <div className="relative flex-shrink-0">
          <button
            onClick={() => setShowActions((v) => !v)}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors font-bold leading-none"
          >
            ⋮
          </button>
          {showActions && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setShowActions(false)} />
              <div className="absolute end-0 top-full mt-1 w-48 bg-white border border-gray-200 rounded-xl shadow-lg z-20 py-1 overflow-hidden">
                {member.role === 'editor' && (
                  <button
                    className="w-full text-start px-4 py-2.5 text-[13px] text-gray-700 hover:bg-gray-50 transition-colors"
                    onClick={() => { onRoleChange('viewer'); setShowActions(false) }}
                  >
                    {t('members.change_role')}: {t('members.roles.viewer')}
                  </button>
                )}
                {member.role === 'viewer' && (
                  <button
                    className="w-full text-start px-4 py-2.5 text-[13px] text-gray-700 hover:bg-gray-50 transition-colors"
                    onClick={() => { onRoleChange('editor'); setShowActions(false) }}
                  >
                    {t('members.change_role')}: {t('members.roles.editor')}
                  </button>
                )}
                <button
                  className="w-full text-start px-4 py-2.5 text-[13px] text-red-500 hover:bg-red-50 transition-colors"
                  onClick={() => { onRemove(); setShowActions(false) }}
                >
                  {t('members.remove')}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </li>
  )
}

function RoleBadge({ role, t }: { role: string; t: (k: string) => string }) {
  const styles: Record<string, string> = {
    owner: 'bg-purple-50 text-purple-600',
    editor: 'bg-blue-50 text-blue-600',
    viewer: 'bg-gray-100 text-gray-500',
  }
  return (
    <span className={clsx('text-[10px] font-semibold px-1.5 py-0.5 rounded', styles[role] ?? styles.viewer)}>
      {t(`members.roles.${role}`)}
    </span>
  )
}

function StatusBadge({ accepted, t }: { accepted: boolean; t: (k: string) => string }) {
  return (
    <span className={clsx(
      'text-[10px] font-medium px-1.5 py-0.5 rounded',
      accepted ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600',
    )}>
      {accepted ? t('members.active') : t('members.pending')}
    </span>
  )
}

function FormField({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
        {label}{required && <span className="text-red-400 ms-0.5">*</span>}
      </label>
      {children}
    </div>
  )
}

function CurrencySelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className={INPUT}>
      {['ILS', 'USD', 'EUR', 'GBP'].map((c) => <option key={c} value={c}>{c}</option>)}
    </select>
  )
}

function ConfirmDialog({
  title,
  message,
  isDestructive,
  isPending,
  onConfirm,
  onCancel,
  confirmLabel,
}: {
  title: string
  message: string
  isDestructive?: boolean
  isPending?: boolean
  onConfirm?: () => void
  onCancel: () => void
  confirmLabel?: string
}) {
  const { t: tc } = useTranslation('common')
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl max-w-sm w-full p-6">
        <h3 className="text-[15px] font-semibold text-gray-900 mb-2">{title}</h3>
        <p className="text-[13px] text-gray-600 mb-6">{message}</p>
        <div className="flex gap-2 justify-end">
          <button onClick={onCancel} className={BTN_GHOST}>{tc('actions.cancel')}</button>
          {onConfirm && (
            <button
              onClick={onConfirm}
              disabled={isPending}
              className={clsx(BTN_PRIMARY, isDestructive && '!bg-red-600 hover:!bg-red-700')}
            >
              {isPending ? tc('actions.saving') : (confirmLabel ?? tc('actions.confirm'))}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

function IconTrash() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <path d="M2 3.5h10M5 3.5V2.5h4v1M5.5 6v4M8.5 6v4M3 3.5l.7 8h6.6l.7-8"/>
    </svg>
  )
}
