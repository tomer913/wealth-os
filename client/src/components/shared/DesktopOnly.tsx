import type { ReactNode } from 'react'

export function DesktopOnly({ children }: { children: ReactNode }) {
  return (
    <>
      <div className="hidden md:block">{children}</div>
      <div className="md:hidden flex flex-col items-center justify-center h-64 px-8 text-center pb-20">
        <div className="w-14 h-14 bg-gray-100 rounded-full flex items-center justify-center mb-4">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="1.5" strokeLinecap="round">
            <rect x="2" y="4" width="20" height="13" rx="2"/>
            <path d="M8 21h8M12 17v4"/>
          </svg>
        </div>
        <p className="text-[15px] font-semibold text-gray-700 mb-1">Desktop only</p>
        <p className="text-[13px] text-gray-400 leading-relaxed">
          This page is designed for larger screens. Open it on a desktop or tablet.
        </p>
      </div>
    </>
  )
}
