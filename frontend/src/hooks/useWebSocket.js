import { useEffect, useRef, useState, useCallback } from 'react';

// Auto-detect WebSocket URL based on environment
const getWsUrl = () => {
  // If VITE_WS_URL is set, use it
  if (import.meta.env.VITE_WS_URL) {
    return import.meta.env.VITE_WS_URL;
  }

  // If in production (not localhost), use same origin with wss://
  if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}/api/ws`;
  }

  // Default to localhost for development
  return 'ws://localhost:8000/api/ws';
};

const WS_URL = getWsUrl();

export const useWebSocket = (endpoint = '/dashboard') => {
  const [data, setData] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttemptsRef = useRef(0);

  const MAX_RECONNECT_ATTEMPTS = 5;
  const RECONNECT_INTERVAL = 3000;

  const connect = useCallback(() => {
    try {
      const token = localStorage.getItem('token');
      const wsUrl = `${WS_URL}${endpoint}${token ? `?token=${token}` : ''}`;

      wsRef.current = new WebSocket(wsUrl);

      wsRef.current.onopen = () => {
        console.log('✅ WebSocket connected');
        setIsConnected(true);
        setError(null);
        reconnectAttemptsRef.current = 0;
      };

      wsRef.current.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          setData(message);
        } catch (err) {
          console.error('❌ Failed to parse WebSocket message:', err);
        }
      };

      wsRef.current.onerror = (event) => {
        console.error('❌ WebSocket error:', event);
        setError('WebSocket connection error');
      };

      wsRef.current.onclose = () => {
        console.log('🔌 WebSocket disconnected');
        setIsConnected(false);

        // Attempt to reconnect
        if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log(
              `🔄 Reconnecting... (Attempt ${reconnectAttemptsRef.current + 1}/${MAX_RECONNECT_ATTEMPTS})`
            );
            reconnectAttemptsRef.current += 1;
            connect();
          }, RECONNECT_INTERVAL);
        } else {
          setError('Max reconnection attempts reached');
        }
      };
    } catch (err) {
      console.error('❌ Failed to create WebSocket:', err);
      setError(err.message);
    }
  }, [endpoint]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setIsConnected(false);
  }, []);

  const send = useCallback((message) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    } else {
      console.warn('⚠️ WebSocket is not connected');
    }
  }, []);

  useEffect(() => {
    connect();

    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  return {
    data,
    isConnected,
    error,
    send,
    reconnect: connect,
  };
};

export default useWebSocket;
