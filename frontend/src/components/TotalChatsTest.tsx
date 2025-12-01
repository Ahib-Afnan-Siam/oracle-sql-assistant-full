// src/components/TotalChatsTest.tsx
import React, { useState, useEffect } from 'react';

const TotalChatsTest: React.FC = () => {
  const [totalChats, setTotalChats] = useState<number | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchTotalChats = async () => {
      try {
        setLoading(true);
        setError(null);
        
        const token = localStorage.getItem("authToken");
        const response = await fetch("/api/admin/dashboard/total-chats", {
          headers: {
            "Authorization": `Bearer ${token || ''}`
          }
        });
        
        if (response.ok) {
          const data = await response.json();
          if (data.success && data.total_chats !== undefined) {
            setTotalChats(data.total_chats);
          } else {
            setError('Invalid response format');
          }
        } else {
          setError(`HTTP error! status: ${response.status}`);
        }
      } catch (err) {
        setError(`Error fetching total chats: ${err instanceof Error ? err.message : 'Unknown error'}`);
      } finally {
        setLoading(false);
      }
    };

    fetchTotalChats();
  }, []);

  return (
    <div className="p-6 bg-white rounded-lg shadow dark:bg-gray-800">
      <h2 className="text-xl font-bold mb-4 dark:text-white">Total Chats Test</h2>
      {loading && <p className="dark:text-gray-300">Loading...</p>}
      {error && <p className="text-red-500 dark:text-red-400">Error: {error}</p>}
      {totalChats !== null && (
        <div className="mt-4">
          <p className="text-lg dark:text-gray-300">
            Total Chats: <span className="font-bold text-purple-600 dark:text-purple-400">{totalChats.toLocaleString()}</span>
          </p>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
            This count is fetched directly from the DASHBOARD_CHATS table using SELECT COUNT(*).
          </p>
        </div>
      )}
    </div>
  );
};

export default TotalChatsTest;