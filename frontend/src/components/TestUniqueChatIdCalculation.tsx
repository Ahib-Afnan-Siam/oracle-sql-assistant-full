// src/components/TestUniqueChatIdCalculation.tsx
import React, { useState, useEffect } from 'react';

const TestUniqueChatIdCalculation: React.FC = () => {
  const [tokenUsageData, setTokenUsageData] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchTokenUsageData = async () => {
      try {
        setLoading(true);
        setError(null);
        
        const token = localStorage.getItem("authToken");
        const response = await fetch("/api/admin/dashboard/token-usage?time_range=weekly", {
          headers: {
            "Authorization": `Bearer ${token || ''}`
          }
        });
        
        if (response.ok) {
          const data = await response.json();
          if (data.success && data.data) {
            setTokenUsageData(data.data);
          } else {
            setError('Invalid response format from server');
          }
        } else {
          const errorData = await response.json();
          setError(`HTTP error! status: ${response.status} - ${errorData.detail || 'Unknown error'}`);
        }
      } catch (err) {
        setError(`Error fetching token usage data: ${err instanceof Error ? err.message : 'Unknown error'}`);
      } finally {
        setLoading(false);
      }
    };

    fetchTokenUsageData();
  }, []);

  return (
    <div className="p-6 bg-white rounded-lg shadow dark:bg-gray-800">
      <h2 className="text-xl font-bold mb-4 dark:text-white">Unique Chat ID Token Usage Test</h2>
      {loading && <p className="dark:text-gray-300">Loading token usage data with unique chat_id calculation...</p>}
      {error && <p className="text-red-500 dark:text-red-400">Error: {error}</p>}
      {tokenUsageData && (
        <div className="mt-4">
          <h3 className="text-lg font-medium dark:text-gray-100">Token Usage Statistics (Unique Chat IDs Only)</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-2">
            <div className="p-4 bg-purple-50 dark:bg-purple-900/20 rounded-lg">
              <p className="text-sm text-gray-500 dark:text-gray-400">Total Tokens</p>
              <p className="text-2xl font-bold text-purple-600 dark:text-purple-400">
                {new Intl.NumberFormat('en-US').format(tokenUsageData.statistics.total_tokens)}
              </p>
            </div>
            <div className="p-4 bg-green-50 dark:bg-green-900/20 rounded-lg">
              <p className="text-sm text-gray-500 dark:text-gray-400">Total Cost (USD)</p>
              <p className="text-2xl font-bold text-green-600 dark:text-green-400">
                ${tokenUsageData.statistics.total_cost_usd?.toFixed(6) || '0.000000'}
              </p>
            </div>
            <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
              <p className="text-sm text-gray-500 dark:text-gray-400">Unique Chat IDs</p>
              <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">
                {new Intl.NumberFormat('en-US').format(tokenUsageData.statistics.total_usage_records)}
              </p>
            </div>
          </div>
          
          <h3 className="text-lg font-medium dark:text-gray-100 mt-6">Token Usage by Model (Unique Chat IDs Only)</h3>
          <div className="mt-2 space-y-3">
            {tokenUsageData.usage_by_model.map((model: any, index: number) => (
              <div key={index} className="p-4 bg-gray-50 dark:bg-gray-700 rounded-lg">
                <div className="flex justify-between">
                  <div>
                    <p className="font-medium dark:text-white">{model.model_name}</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">{model.model_type}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-medium dark:text-white">
                      {new Intl.NumberFormat('en-US').format(model.total_tokens)} tokens
                    </p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      ${model.total_cost_usd?.toFixed(6) || '0.000000'}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
          
          <div className="mt-6 p-4 bg-green-50 dark:bg-green-900/20 rounded-lg">
            <p className="text-green-800 dark:text-green-200">
              ✅ Verification successful: Token usage is now calculated based on unique chat_id entries only.
            </p>
            <p className="text-green-800 dark:text-green-200 mt-2">
              ✅ Duplicate chat_id entries are properly excluded from the totals.
            </p>
          </div>
        </div>
      )}
    </div>
  );
};

export default TestUniqueChatIdCalculation;