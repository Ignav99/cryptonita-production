import { Outlet, useLocation } from 'react-router-dom';
import Sidebar from './Sidebar';
import Header from './Header';
import { useDashboard } from '../../context/DashboardContext';

const pageTitles = {
  '/': 'Overview',
  '/positions': 'Positions',
  '/signals': 'Signals',
  '/trades': 'Trades',
  '/training': 'Training',
  '/settings': 'Settings',
};

export default function Layout() {
  const { pathname } = useLocation();
  const { botStatus, stats } = useDashboard();

  const title = pageTitles[pathname] || 'Dashboard';
  const statusStr = botStatus?.status || 'stopped';
  const btcPrice = stats?.btc_price;

  return (
    <div className="min-h-screen bg-dark-bg">
      <Sidebar botStatus={statusStr} />
      <div className="ml-56">
        <Header title={title} botStatus={statusStr} btcPrice={btcPrice} />
        <main className="p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
