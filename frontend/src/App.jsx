import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { auth } from './api/client';
import { DashboardProvider } from './context/DashboardContext';
import Layout from './components/layout/Layout';
import Login from './pages/Login';
import Overview from './pages/Overview';
import Positions from './pages/Positions';
import Signals from './pages/Signals';
import Trades from './pages/Trades';
import Training from './pages/Training';
import Settings from './pages/Settings';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 10000,
    },
  },
});

function ProtectedRoute({ children }) {
  if (!auth.isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <DashboardProvider>
                  <Layout />
                </DashboardProvider>
              </ProtectedRoute>
            }
          >
            <Route index element={<Overview />} />
            <Route path="positions" element={<Positions />} />
            <Route path="signals" element={<Signals />} />
            <Route path="trades" element={<Trades />} />
            <Route path="training" element={<Training />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
