import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TooltipProvider } from '@/components/ui/tooltip';
import { AuthProvider } from '@/contexts/AuthProvider';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import DashboardLayout from '@/layouts/DashboardLayout';
import Login from '@/pages/Login';
import Register from '@/pages/Register';
import Dashboard from '@/pages/Dashboard';
import ApiMonitor from '@/pages/ApiMonitor';
import TestCases from '@/pages/TestCases';
import TestProjects from '@/pages/TestProjects';
import Coverage from '@/pages/Coverage';
import JiraSettings from '@/pages/JiraSettings';
import Members from '@/pages/Members';
import Join from '@/pages/Join';
import Upgrade from '@/pages/Upgrade';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <TooltipProvider>
            <Routes>
              {/* Public routes */}
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/join" element={<Join />} />
              <Route path="/upgrade" element={<Upgrade />} />

              {/* Protected routes with dashboard layout */}
              <Route
                element={
                  <ProtectedRoute>
                    <DashboardLayout />
                  </ProtectedRoute>
                }
              >
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/api-monitor" element={<ApiMonitor />} />
                <Route path="/test-cases" element={<TestCases />} />
                <Route path="/test-projects" element={<TestProjects />} />
                <Route path="/coverage" element={<Coverage />} />
                <Route path="/jira" element={<JiraSettings />} />
                <Route path="/members" element={<Members />} />
              </Route>

              {/* Redirect root to dashboard */}
              <Route path="/" element={<Navigate to="/dashboard" replace />} />

              {/* Catch-all redirect */}
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </TooltipProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
