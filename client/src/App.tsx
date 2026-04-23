import { Routes, Route } from 'react-router-dom'
import AppShell from './components/layout/AppShell'
import { DesktopOnly } from './components/shared/DesktopOnly'
import { ProtectedRoute } from './components/auth/ProtectedRoute'
import DashboardPage from './pages/DashboardPage'
import AccountsPage from './pages/AccountsPage'
import AssetsPage from './pages/AssetsPage'
import TransactionsPage from './pages/TransactionsPage'
import ValuationsPage from './pages/ValuationsPage'
import {
  FXRatesPage,
  ReportsPage,
} from './pages/PlaceholderPages'
import ConnectorsPage from './pages/ConnectorsPage'
import BudgetRulesPage from './pages/BudgetRulesPage'
import BudgetDashboardPage from './pages/BudgetDashboardPage'
import BudgetManagementPage from './pages/BudgetManagementPage'
import PipelineStatusPage from './pages/PipelineStatusPage'
import SignInPage from './pages/SignInPage'
import SetupPage from './pages/SetupPage'


export default function App() {
  return (
    <Routes>
        {/* Public routes */}
        <Route path="/sign-in/*" element={<SignInPage />} />
        <Route path="/sign-up/*" element={<SignInPage />} />

        {/* New-user setup (protected but outside AppShell) */}
        <Route
          path="/setup"
          element={
            <ProtectedRoute>
              <SetupPage />
            </ProtectedRoute>
          }
        />

        {/* All protected pages share the AppShell layout */}
        <Route
          element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          }
        >
          <Route path="/" element={<DashboardPage />} />
          <Route path="/assets" element={<AssetsPage />} />
          <Route path="/accounts" element={<AccountsPage />} />
          <Route path="/transactions" element={<TransactionsPage />} />
          <Route path="/valuations" element={<ValuationsPage />} />
          <Route path="/fx-rates" element={<FXRatesPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/connectors" element={<DesktopOnly><ConnectorsPage /></DesktopOnly>} />
          {/* Budget */}
          <Route path="/budget" element={<BudgetDashboardPage />} />
          <Route path="/budget/manage" element={<DesktopOnly><BudgetManagementPage /></DesktopOnly>} />
          <Route path="/budget/rules" element={<DesktopOnly><BudgetRulesPage /></DesktopOnly>} />
          {/* System */}
          <Route path="/pipeline" element={<DesktopOnly><PipelineStatusPage /></DesktopOnly>} />
        </Route>
    </Routes>
  )
}
