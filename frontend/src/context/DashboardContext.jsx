import { createContext, useContext } from 'react';
import { useQuery } from '@tanstack/react-query';
import { dashboard, controls } from '../api/client';
import { useWebSocket } from '../hooks/useWebSocket';

const DashboardContext = createContext(null);

export function DashboardProvider({ children }) {
  const ws = useWebSocket('/dashboard');

  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: dashboard.getStats,
    refetchInterval: 15000,
  });

  const { data: botStatus } = useQuery({
    queryKey: ['botStatus'],
    queryFn: dashboard.getBotStatus,
    refetchInterval: 10000,
  });

  const { data: positions } = useQuery({
    queryKey: ['positions'],
    queryFn: dashboard.getPositions,
    refetchInterval: 15000,
  });

  const { data: performance } = useQuery({
    queryKey: ['performance'],
    queryFn: () => dashboard.getPerformance(30),
    refetchInterval: 60000,
  });

  const { data: trainingStatus } = useQuery({
    queryKey: ['trainingStatus'],
    queryFn: controls.getTrainingStatus,
    refetchInterval: 30000,
  });

  const value = {
    stats: ws.data?.stats || stats,
    botStatus: ws.data?.bot_status || botStatus,
    positions: ws.data?.positions || positions,
    performance,
    trainingStatus,
    wsConnected: ws.isConnected,
  };

  return (
    <DashboardContext.Provider value={value}>
      {children}
    </DashboardContext.Provider>
  );
}

export function useDashboard() {
  const context = useContext(DashboardContext);
  if (!context) {
    throw new Error('useDashboard must be used within DashboardProvider');
  }
  return context;
}
