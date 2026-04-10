import { BrowserRouter, Routes, Route } from 'react-router-dom'
import AppShell from './components/layout/AppShell'
import DashboardPage from './pages/DashboardPage'
import AccountsPage from './pages/AccountsPage'
import AssetsPage from './pages/AssetsPage'
import {
  TransactionsPage,
  ValuationsPage,
  FXRatesPage,
  ReportsPage,
} from './pages/PlaceholderPages'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* All pages share the AppShell layout (sidebar + topbar + filter) */}
        <Route element={<AppShell />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/assets" element={<AssetsPage />} />
          <Route path="/accounts" element={<AccountsPage />} />
          <Route path="/transactions" element={<TransactionsPage />} />
          <Route path="/valuations" element={<ValuationsPage />} />
          <Route path="/fx-rates" element={<FXRatesPage />} />
          <Route path="/reports" element={<ReportsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
