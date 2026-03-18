import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bot, LogIn } from 'lucide-react';
import { auth } from '../api/client';
import Button from '../components/ui/Button';

export default function Login() {
  const navigate = useNavigate();
  const [credentials, setCredentials] = useState({ username: '', password: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const data = await auth.login(credentials.username, credentials.password);
      localStorage.setItem('token', data.access_token);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed. Check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-dark-bg flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Branding */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-accent-blue/10 border border-accent-blue/30 mb-4">
            <Bot className="w-7 h-7 text-accent-blue" />
          </div>
          <h1 className="text-2xl font-bold text-text-primary">Cryptonita</h1>
          <p className="text-sm text-text-secondary mt-1">V4 Trading Dashboard</p>
        </div>

        {/* Login Card */}
        <div className="bg-dark-card border border-dark-border rounded-lg p-6">
          <h2 className="text-lg font-semibold text-text-primary mb-5">Sign In</h2>

          {error && (
            <div className="mb-4 p-3 bg-accent-red/10 border border-accent-red/30 rounded-md text-accent-red text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="username" className="block text-xs font-medium text-text-secondary mb-1.5">
                Username
              </label>
              <input
                id="username"
                type="text"
                value={credentials.username}
                onChange={(e) => setCredentials({ ...credentials, username: e.target.value })}
                className="w-full px-3 py-2 bg-dark-bg border border-dark-border rounded-md text-sm text-text-primary placeholder-text-secondary/50 focus:outline-none focus:border-accent-blue focus:ring-1 focus:ring-accent-blue"
                placeholder="Enter username"
                required
                autoComplete="username"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-xs font-medium text-text-secondary mb-1.5">
                Password
              </label>
              <input
                id="password"
                type="password"
                value={credentials.password}
                onChange={(e) => setCredentials({ ...credentials, password: e.target.value })}
                className="w-full px-3 py-2 bg-dark-bg border border-dark-border rounded-md text-sm text-text-primary placeholder-text-secondary/50 focus:outline-none focus:border-accent-blue focus:ring-1 focus:ring-accent-blue"
                placeholder="Enter password"
                required
                autoComplete="current-password"
              />
            </div>

            <Button
              type="submit"
              variant="primary"
              size="lg"
              icon={LogIn}
              loading={loading}
              className="w-full"
            >
              Sign In
            </Button>
          </form>
        </div>

        <p className="text-center text-xs text-text-secondary/50 mt-6">
          Cryptonita V4 — ML-Powered Trading
        </p>
      </div>
    </div>
  );
}
