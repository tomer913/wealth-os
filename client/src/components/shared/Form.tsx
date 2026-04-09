import clsx from 'clsx'

interface FieldProps {
  label: string
  required?: boolean
  error?: string
  children: React.ReactNode
  hint?: string
}

export function Field({ label, required, error, hint, children }: FieldProps) {
  return (
    <div className="space-y-1.5">
      <label className="block text-[12px] font-medium text-gray-700">
        {label}
        {required && <span className="text-rose-500 ml-0.5">*</span>}
      </label>
      {children}
      {hint && !error && <p className="text-[11px] text-gray-400">{hint}</p>}
      {error && <p className="text-[11px] text-rose-500">{error}</p>}
    </div>
  )
}

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  error?: boolean
}

export function Input({ error, className, ...props }: InputProps) {
  return (
    <input
      {...props}
      className={clsx(
        'w-full px-3 py-2 text-[13px] border rounded-lg focus:outline-none focus:ring-1 transition-colors',
        error
          ? 'border-rose-300 focus:border-rose-400 focus:ring-rose-100'
          : 'border-gray-200 focus:border-teal-400 focus:ring-teal-50',
        'placeholder:text-gray-300',
        className,
      )}
    />
  )
}

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  error?: boolean
}

export function Select({ error, className, children, ...props }: SelectProps) {
  return (
    <select
      {...props}
      className={clsx(
        'w-full px-3 py-2 text-[13px] border rounded-lg focus:outline-none focus:ring-1 transition-colors appearance-none bg-white',
        error
          ? 'border-rose-300 focus:border-rose-400 focus:ring-rose-100'
          : 'border-gray-200 focus:border-teal-400 focus:ring-teal-50',
        className,
      )}
    >
      {children}
    </select>
  )
}

export function Textarea({ error, className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { error?: boolean }) {
  return (
    <textarea
      {...props}
      className={clsx(
        'w-full px-3 py-2 text-[13px] border rounded-lg focus:outline-none focus:ring-1 transition-colors resize-none',
        error
          ? 'border-rose-300 focus:border-rose-400 focus:ring-rose-100'
          : 'border-gray-200 focus:border-teal-400 focus:ring-teal-50',
        'placeholder:text-gray-300',
        className,
      )}
    />
  )
}

export function FormGrid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-2 gap-4">{children}</div>
}

export function FormSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-3">
      <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">{title}</p>
      {children}
    </div>
  )
}

export function Divider() {
  return <hr className="border-gray-100" />
}
