import { Navigate, Route, Routes } from 'react-router-dom';
import { ReactNode } from 'react';
import { getToken } from './api/client';
import Layout from './components/Layout';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import CheckDetailPage from './pages/CheckDetailPage';
import GroupPage from './pages/GroupPage';
import MaintenancePage from './pages/MaintenancePage';
import MailboxPage from './pages/MailboxPage';
import DemoPage from './pages/DemoPage';
import PublicStatusPage from './pages/PublicStatusPage';

function RequireAuth({ children }: { children: ReactNode }) {
  if (!getToken()) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/status/:slug" element={<PublicStatusPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<DashboardPage />} />
        <Route path="/checks/:id" element={<CheckDetailPage />} />
        <Route path="/groups/:id" element={<GroupPage />} />
        <Route path="/maintenance" element={<MaintenancePage />} />
        <Route path="/mailbox" element={<MailboxPage />} />
        <Route path="/demo" element={<DemoPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
