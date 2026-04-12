import { BrowserRouter, Routes, Route } from 'react-router-dom'
import AppShell from './components/layout/AppShell'
import DashboardPage from './pages/DashboardPage'
import AccountsPage from './pages/AccountsPage'
import AssetsPage from './pages/AssetsPage'
import TransactionsPage from './pages/TransactionsPage'
import ValuationsPage from './pages/ValuationsPage'
import {
  FXRatesPage,
  ReportsPage,
} from './pages/PlaceholderPages'
import ConnectorsPage from './pages/ConnectorsPage';
import BudgetRulesPage from './pages/BudgetRulesPage';


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
          <Route path="/connectors" element={<ConnectorsPage />} />
          <Route path="/budget/rules" element={<BudgetRulesPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
