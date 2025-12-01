import React, { useState, useEffect } from 'react';
import { 
  Database, 
  TrendingUp, 
  Calendar, 
  Filter, 
  Download,
  BarChart3,
  LineChart,
  PieChart
} from 'lucide-react';
import ChartComponent from './ChartComponent';
import { motion, AnimatePresence } from 'framer-motion';

interface TimeRange {
  value: 'daily' | 'weekly' | 'monthly';
  label: string;
}

interface ChartDataset {
  label: string;
  data: number[];
  backgroundColor?: string | string[];
  borderColor?: string | string[];
  borderWidth?: number;
  yAxisID?: string;
  borderDash?: number[];
}

interface ChartData {
  labels: string[];
  datasets: ChartDataset[];
}

interface TokenUsageData {
  statistics: {
    total_usage_records: number;
    total_prompt_tokens: number;
    total_completion_tokens: number;
    total_tokens: number;
    total_cost_usd: number;
    avg_prompt_tokens: number;
    avg_completion_tokens: number;
    avg_total_tokens: number;
    avg_cost_usd: number;
  };
  usage_by_model: {
    model_name: string;
    model_type: string;
    usage_count: number;
    total_prompt_tokens: number;
    total_completion_tokens: number;
    total_tokens: number;
    total_cost_usd: number;
    avg_prompt_tokens: number;
    avg_completion_tokens: number;
    avg_total_tokens: number;
    avg_cost_usd: number;
  }[];
  usage_over_time: {
    usage_date: string;
    total_tokens: number;
  }[];
  hourly_usage: {
    hour: string;
    total_tokens: number;
    total_cost: number;
  }[];
  usage_forecast: {
    usage_date: string;
    total_tokens: number;
    forecast: boolean;
  }[];
  cost_forecast: {
    usage_date: string;
    total_cost: number;
    forecast: boolean;
  }[];
  cost_over_time: {
    usage_date: string;
    total_cost: number;
  }[];
}

const TokenUsageDashboard: React.FC = () => {
  const [timeRange, setTimeRange] = useState<'daily' | 'weekly' | 'monthly'>('weekly');
  const [modelFilter, setModelFilter] = useState<string>('all');
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [tokenUsageData, setTokenUsageData] = useState<TokenUsageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [models, setModels] = useState<{model_name: string}[]>([]);

  const timeRanges: TimeRange[] = [
    { value: 'daily', label: 'Daily' },
    { value: 'weekly', label: 'Weekly' },
    { value: 'monthly', label: 'Monthly' }
  ];

  // Fetch token usage data
  useEffect(() => {
    const fetchTokenUsageData = async () => {
      try {
        setLoading(true);
        setError(null);
        
        const token = localStorage.getItem("authToken");
        
        // Build query parameters
        const queryParams = new URLSearchParams();
        queryParams.append('time_range', timeRange);
        
        if (modelFilter !== 'all') {
          queryParams.append('model_name', modelFilter);
        }
        
        if (startDate) {
          queryParams.append('start_date', startDate);
        }
        
        if (endDate) {
          queryParams.append('end_date', endDate);
        }
        
        const response = await fetch(`/api/admin/dashboard/token-usage?${queryParams.toString()}`, {
          headers: {
            "Authorization": `Bearer ${token}`
          }
        });
        
        if (response.ok) {
          const data = await response.json();
          
          if (data.success && data.data) {
            setTokenUsageData(data.data);
            
            // Extract unique models for filter dropdown
            const uniqueModels = Array.from(
              new Set(data.data.usage_by_model.map((item: any) => item.model_name))
            ).map(model_name => ({ model_name }));
            setModels(uniqueModels);
          }
        } else {
          console.error("Failed to fetch token usage data. Status:", response.status);
          setError('Failed to load token usage data. Please try again later.');
        }
      } catch (err) {
        console.error('Error fetching token usage data:', err);
        setError('Failed to load token usage data. Please try again later.');
      } finally {
        setLoading(false);
      }
    };

    fetchTokenUsageData();
  }, [timeRange, modelFilter, startDate, endDate]);

  // Transform data for charts
  const transformChartData = (): {
    usageOverTime: ChartData;
    hourlyUsage: ChartData;
    usageByModel: ChartData;
    usageForecast: ChartData;
    costForecast: ChartData;
    costOverTime: ChartData;
  } => {
    if (!tokenUsageData) {
      return {
        usageOverTime: { labels: [], datasets: [] },
        hourlyUsage: { labels: [], datasets: [] },
        usageByModel: { labels: [], datasets: [] },
        usageForecast: { labels: [], datasets: [] },
        costForecast: { labels: [], datasets: [] },
        costOverTime: { labels: [], datasets: [] }
      };
    }

    // Transform usage over time data
    const usageOverTimeLabels = tokenUsageData.usage_over_time.map(item => {
      const date = new Date(item.usage_date);
      if (timeRange === 'daily') return date.toLocaleDateString();
      if (timeRange === 'weekly') return `Week of ${date.toLocaleDateString()}`;
      return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
    });
    
    const usageOverTimeData = {
      labels: usageOverTimeLabels,
      datasets: [
        {
          label: 'Tokens Consumed',
          data: tokenUsageData.usage_over_time.map(item => item.total_tokens || 0),
          backgroundColor: 'rgba(16, 185, 129, 0.7)',
          borderColor: 'rgba(16, 185, 129, 1)',
          borderWidth: 2
        }
      ]
    };

    // Transform hourly usage data
    const hourlyUsageLabels = tokenUsageData.hourly_usage.map(item => {
      const date = new Date(item.hour);
      return date.toLocaleString('en-US', { 
        month: 'short', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    });
    
    const hourlyUsageData = {
      labels: hourlyUsageLabels,
      datasets: [
        {
          label: 'Tokens Consumed',
          data: tokenUsageData.hourly_usage.map(item => item.total_tokens || 0),
          backgroundColor: 'rgba(16, 185, 129, 0.7)',
          borderColor: 'rgba(16, 185, 129, 1)',
          borderWidth: 2
        },
        {
          label: 'Estimated Cost (USD)',
          data: tokenUsageData.hourly_usage.map(item => {
            const cost = item.total_cost || 0;
            return parseFloat(cost.toFixed(4));
          }),
          backgroundColor: 'rgba(59, 130, 246, 0.7)',
          borderColor: 'rgba(59, 130, 246, 1)',
          borderWidth: 2,
          yAxisID: 'y1'
        }
      ]
    };

    // Transform usage by model data
    const usageByModelLabels = tokenUsageData.usage_by_model.map(item => item.model_name);
    const usageByModelData = {
      labels: usageByModelLabels,
      datasets: [
        {
          label: 'Total Tokens',
          data: tokenUsageData.usage_by_model.map(item => item.total_tokens || 0),
          backgroundColor: [
            'rgba(139, 92, 246, 0.7)',
            'rgba(59, 130, 246, 0.7)',
            'rgba(16, 185, 129, 0.7)',
            'rgba(245, 158, 11, 0.7)',
            'rgba(239, 68, 68, 0.7)'
          ],
          borderColor: [
            'rgba(139, 92, 246, 1)',
            'rgba(59, 130, 246, 1)',
            'rgba(16, 185, 129, 1)',
            'rgba(245, 158, 11, 1)',
            'rgba(239, 68, 68, 1)'
          ],
          borderWidth: 2
        }
      ]
    };

    // Transform usage forecast data
    const forecastLabels = [
      ...tokenUsageData.usage_over_time.map(item => {
        const date = new Date(item.usage_date);
        return date.toLocaleDateString();
      }),
      ...tokenUsageData.usage_forecast.map(item => {
        const date = new Date(item.usage_date);
        return date.toLocaleDateString();
      })
    ];
    
    const historicalTokens = tokenUsageData.usage_over_time.map(item => item.total_tokens || 0);
    const forecastTokens = tokenUsageData.usage_forecast.map(item => item.total_tokens || 0);
    
    const usageForecastData = {
      labels: forecastLabels,
      datasets: [
        {
          label: 'Historical Usage',
          data: [...historicalTokens, ...Array(forecastTokens.length).fill(null)],
          backgroundColor: 'rgba(16, 185, 129, 0.7)',
          borderColor: 'rgba(16, 185, 129, 1)',
          borderWidth: 2
        },
        {
          label: 'Forecasted Usage',
          data: [...Array(historicalTokens.length).fill(null), ...forecastTokens],
          backgroundColor: 'rgba(59, 130, 246, 0.7)',
          borderColor: 'rgba(59, 130, 246, 1)',
          borderWidth: 2,
          borderDash: [5, 5]
        }
      ]
    };

    // Transform cost forecast data
    const costForecastLabels = [
      ...tokenUsageData.cost_over_time.map(item => {
        const date = new Date(item.usage_date);
        return date.toLocaleDateString();
      }),
      ...tokenUsageData.cost_forecast.map(item => {
        const date = new Date(item.usage_date);
        return date.toLocaleDateString();
      })
    ];
    
    const historicalCosts = tokenUsageData.cost_over_time.map(item => parseFloat((item.total_cost || 0).toFixed(6)));
    const forecastCosts = tokenUsageData.cost_forecast.map(item => parseFloat((item.total_cost || 0).toFixed(6)));
    
    const costForecastData = {
      labels: costForecastLabels,
      datasets: [
        {
          label: 'Historical Cost',
          data: [...historicalCosts, ...Array(forecastCosts.length).fill(null)],
          backgroundColor: 'rgba(16, 185, 129, 0.7)',
          borderColor: 'rgba(16, 185, 129, 1)',
          borderWidth: 2
        },
        {
          label: 'Forecasted Cost',
          data: [...Array(historicalCosts.length).fill(null), ...forecastCosts],
          backgroundColor: 'rgba(59, 130, 246, 0.7)',
          borderColor: 'rgba(59, 130, 246, 1)',
          borderWidth: 2,
          borderDash: [5, 5]
        }
      ]
    };

    // Transform cost over time data
    const costOverTimeLabels = tokenUsageData.cost_over_time.map(item => {
      const date = new Date(item.usage_date);
      if (timeRange === 'daily') return date.toLocaleDateString();
      if (timeRange === 'weekly') return `Week of ${date.toLocaleDateString()}`;
      return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
    });
    
    const costOverTimeData = {
      labels: costOverTimeLabels,
      datasets: [
        {
          label: 'Cost (USD)',
          data: tokenUsageData.cost_over_time.map(item => parseFloat((item.total_cost || 0).toFixed(6))),
          backgroundColor: 'rgba(16, 185, 129, 0.7)',
          borderColor: 'rgba(16, 185, 129, 1)',
          borderWidth: 2
        }
      ]
    };

    return {
      usageOverTime: usageOverTimeData,
      hourlyUsage: hourlyUsageData,
      usageByModel: usageByModelData,
      usageForecast: usageForecastData,
      costForecast: costForecastData,
      costOverTime: costOverTimeData
    };
  };

  // Chart options with theme support
  const getChartOptions = (title: string, hasDualYAxis: boolean = false) => {
    const isDarkMode = document.documentElement.classList.contains('dark');
    
    const baseOptions = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'top' as const,
          labels: {
            color: isDarkMode ? '#f9fafb' : '#374151',
            usePointStyle: true
          }
        },
        title: {
          display: true,
          text: title,
          color: isDarkMode ? '#f9fafb' : '#374151',
          font: {
            size: 14
          }
        },
        tooltip: {
          mode: 'index' as const,
          intersect: false,
          backgroundColor: isDarkMode ? 'rgba(31, 41, 55, 0.9)' : 'rgba(255, 255, 255, 0.9)',
          titleColor: isDarkMode ? '#f9fafb' : '#1f2937',
          bodyColor: isDarkMode ? '#d1d5db' : '#4b5563',
          borderColor: isDarkMode ? '#4b5563' : '#e5e7eb',
          borderWidth: 1,
          padding: 12,
          usePointStyle: true,
          callbacks: {
            label: function(context: any) {
              let label = context.dataset.label || '';
              if (label) {
                label += ': ';
              }
              if (context.parsed.y !== null) {
                // Format numbers appropriately
                if (context.dataset.yAxisID === 'y1') {
                  // For cost data, show with more decimal places
                  label += new Intl.NumberFormat('en-US', { 
                    style: 'currency', 
                    currency: 'USD',
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 6
                  }).format(context.parsed.y);
                } else if (title.includes('Tokens')) {
                  // For token counts, show with commas
                  label += new Intl.NumberFormat('en-US').format(context.parsed.y);
                } else if (title.includes('Cost')) {
                  label += new Intl.NumberFormat('en-US', { 
                    style: 'currency', 
                    currency: 'USD',
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 6
                  }).format(context.parsed.y);
                } else {
                  label += context.parsed.y;
                }
              }
              return label;
            }
          }
        }
      },
      interaction: {
        mode: 'index' as const,
        intersect: false
      },
      scales: isDarkMode ? {
        x: {
          ticks: {
            color: '#d1d5db'
          },
          grid: {
            color: '#374151'
          }
        },
        y: {
          ticks: {
            color: '#d1d5db',
            callback: function(value: any) {
              if (title.includes('Tokens')) {
                return new Intl.NumberFormat('en-US').format(value);
              } else if (title.includes('Cost')) {
                return '$' + value.toFixed(4);
              }
              return value;
            }
          },
          grid: {
            color: '#374151'
          }
        }
      } : {
        x: {
          ticks: {
            color: '#6b7280'
          },
          grid: {
            color: '#e5e7eb'
          }
        },
        y: {
          ticks: {
            color: '#6b7280',
            callback: function(value: any) {
              if (title.includes('Tokens')) {
                return new Intl.NumberFormat('en-US').format(value);
              } else if (title.includes('Cost')) {
                return '$' + value.toFixed(4);
              }
              return value;
            }
          },
          grid: {
            color: '#e5e7eb'
          }
        }
      }
    };

    // Add secondary y-axis for dual-axis charts
    if (hasDualYAxis) {
      const dualAxisOptions = {
        ...baseOptions,
        scales: {
          ...baseOptions.scales,
          y1: {
            position: 'right' as const,
            ticks: {
              color: isDarkMode ? '#d1d5db' : '#6b7280',
              callback: function(value: any) {
                return '$' + value.toFixed(4);
              }
            },
            grid: {
              drawOnChartArea: false,
              color: isDarkMode ? '#374151' : '#e5e7eb'
            }
          }
        }
      };
      return dualAxisOptions;
    }

    return baseOptions;
  };

  // Handle form submission for date filtering
  const handleDateFilterSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // The useEffect will automatically refetch data when startDate or endDate changes
  };

  // Reset date filters
  const resetDateFilters = () => {
    setStartDate('');
    setEndDate('');
  };

  const chartData = transformChartData();

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-purple-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <motion.div 
        className="bg-white rounded-lg shadow p-6 dark:bg-gray-800"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-medium dark:text-gray-100">Token Usage Dashboard</h3>
        </div>
        
        <div className="bg-red-50 border-l-4 border-red-400 p-4 dark:bg-red-900/20 dark:border-red-600">
          <div className="flex">
            <div className="flex-shrink-0">
              <Database className="h-5 w-5 text-red-400 dark:text-red-500" />
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800 dark:text-red-200">
                Error Loading Data
              </h3>
              <div className="mt-2 text-sm text-red-700 dark:text-red-300">
                <p>{error}</p>
              </div>
              <div className="mt-4">
                <button
                  type="button"
                  onClick={() => window.location.reload()}
                  className="inline-flex items-center px-3 py-2 border border-transparent text-sm leading-4 font-medium rounded-md shadow-sm text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 dark:bg-red-700 dark:hover:bg-red-800"
                >
                  Retry
                </button>
              </div>
            </div>
          </div>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div 
      className="space-y-6"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5 }}
    >
      {/* Header and Filters */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Token Usage Dashboard</h2>
        <div className="flex flex-wrap items-center gap-4">
          {/* Time Range Selector */}
          <div className="flex items-center space-x-2">
            <Calendar className="h-5 w-5 text-gray-500 dark:text-gray-400" />
            <div className="flex rounded-md shadow-sm">
              {timeRanges.map((range) => (
                <button
                  key={range.value}
                  type="button"
                  className={`px-4 py-2 text-sm font-medium rounded-md ${
                    timeRange === range.value
                      ? 'bg-purple-600 text-white'
                      : 'bg-white text-gray-700 hover:bg-gray-50 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600'
                  } ${range.value === 'daily' ? 'rounded-l-md' : ''} ${
                    range.value === 'monthly' ? 'rounded-r-md' : ''
                  }`}
                  onClick={() => setTimeRange(range.value)}
                >
                  {range.label}
                </button>
              ))}
            </div>
          </div>
          
          {/* Model Filter */}
          <div className="flex items-center space-x-2">
            <Filter className="h-5 w-5 text-gray-500 dark:text-gray-400" />
            <select
              value={modelFilter}
              onChange={(e) => setModelFilter(e.target.value)}
              className="bg-white border border-gray-300 rounded-md shadow-sm py-2 px-3 text-sm dark:bg-gray-700 dark:border-gray-600 dark:text-white"
            >
              <option value="all">All Models</option>
              {models.map((model) => (
                <option key={model.model_name} value={model.model_name}>
                  {model.model_name}
                </option>
              ))}
            </select>
          </div>
          
          {/* Date Range Filter */}
          <form onSubmit={handleDateFilterSubmit} className="flex items-center space-x-2">
            <div className="flex space-x-2">
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="bg-white border border-gray-300 rounded-md shadow-sm py-2 px-3 text-sm dark:bg-gray-700 dark:border-gray-600 dark:text-white"
              />
              <span className="self-center text-gray-500 dark:text-gray-400">to</span>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="bg-white border border-gray-300 rounded-md shadow-sm py-2 px-3 text-sm dark:bg-gray-700 dark:border-gray-600 dark:text-white"
              />
            </div>
            <button
              type="button"
              onClick={resetDateFilters}
              className="text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
            >
              Reset
            </button>
          </form>
          
          {/* Export Button */}
          <button className="flex items-center px-4 py-2 bg-white border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 hover:bg-gray-50 dark:bg-gray-700 dark:border-gray-600 dark:text-white dark:hover:bg-gray-600">
            <Download className="h-4 w-4 mr-2" />
            Export
          </button>
        </div>
      </div>

      {/* Key Metrics Summary */}
      {tokenUsageData && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <div className="bg-white rounded-lg shadow p-6 border border-gray-200 dark:bg-gray-800 dark:border-gray-700">
            <div className="flex items-center">
              <div className="p-3 rounded-full bg-purple-100 dark:bg-purple-900">
                <Database className="h-6 w-6 text-purple-600 dark:text-purple-400" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Tokens</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">
                  {new Intl.NumberFormat('en-US').format(tokenUsageData.statistics.total_tokens)}
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {new Intl.NumberFormat('en-US').format(tokenUsageData.statistics.total_usage_records)} records
                </p>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow p-6 border border-gray-200 dark:bg-gray-800 dark:border-gray-700">
            <div className="flex items-center">
              <div className="p-3 rounded-full bg-green-100 dark:bg-green-900">
                <PieChart className="h-6 w-6 text-green-600 dark:text-green-400" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Avg. Tokens/Request</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">
                  {new Intl.NumberFormat('en-US').format(Math.round(tokenUsageData.statistics.avg_total_tokens))}
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Prompt: {new Intl.NumberFormat('en-US').format(Math.round(tokenUsageData.statistics.avg_prompt_tokens))}
                </p>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow p-6 border border-gray-200 dark:bg-gray-800 dark:border-gray-700">
            <div className="flex items-center">
              <div className="p-3 rounded-full bg-blue-100 dark:bg-blue-900">
                <LineChart className="h-6 w-6 text-blue-600 dark:text-blue-400" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Cost (USD)</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">
                  {new Intl.NumberFormat('en-US', { 
                    style: 'currency', 
                    currency: 'USD',
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 6
                  }).format(tokenUsageData.statistics.total_cost_usd)}
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Avg: {new Intl.NumberFormat('en-US', { 
                    style: 'currency', 
                    currency: 'USD',
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 6
                  }).format(tokenUsageData.statistics.avg_cost_usd)}
                </p>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow p-6 border border-gray-200 dark:bg-gray-800 dark:border-gray-700">
            <div className="flex items-center">
              <div className="p-3 rounded-full bg-amber-100 dark:bg-amber-900">
                <BarChart3 className="h-6 w-6 text-amber-600 dark:text-amber-400" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Models Used</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">
                  {tokenUsageData.usage_by_model.length}
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {tokenUsageData.usage_by_model.filter(m => m.model_type === 'api').length} API, 
                  {tokenUsageData.usage_by_model.filter(m => m.model_type === 'local').length} Local
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Token Usage Over Time */}
        <motion.div 
          className="bg-white rounded-lg shadow p-6 border border-gray-200 dark:bg-gray-800 dark:border-gray-700"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
        >
          <div className="flex items-center mb-4">
            <LineChart className="h-5 w-5 text-purple-600 dark:text-purple-400 mr-2" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white">Token Usage Over Time</h3>
          </div>
          <div className="h-80">
            <AnimatePresence mode="wait">
              <motion.div
                key={`${timeRange}-usage-over-time`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="w-full h-full"
              >
                <ChartComponent
                  type="line"
                  data={chartData.usageOverTime}
                  options={getChartOptions('Tokens Consumed Over Time')}
                  height={300}
                />
              </motion.div>
            </AnimatePresence>
          </div>
        </motion.div>

        {/* Hourly Token Usage & Cost */}
        <motion.div 
          className="bg-white rounded-lg shadow p-6 border border-gray-200 dark:bg-gray-800 dark:border-gray-700"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.1 }}
        >
          <div className="flex items-center mb-4">
            <Database className="h-5 w-5 text-green-600 dark:text-green-400 mr-2" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white">Hourly Token Usage & Cost</h3>
          </div>
          <div className="h-80">
            <AnimatePresence mode="wait">
              <motion.div
                key={`${timeRange}-hourly-usage`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="w-full h-full"
              >
                <ChartComponent
                  type="line"
                  data={chartData.hourlyUsage}
                  options={getChartOptions('Hourly Token Usage & Cost', true)}
                  height={300}
                />
              </motion.div>
            </AnimatePresence>
          </div>
        </motion.div>

        {/* Token Usage by Model */}
        <motion.div 
          className="bg-white rounded-lg shadow p-6 border border-gray-200 dark:bg-gray-800 dark:border-gray-700"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.2 }}
        >
          <div className="flex items-center mb-4">
            <PieChart className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-2" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white">Token Usage by Model</h3>
          </div>
          <div className="h-80">
            <AnimatePresence mode="wait">
              <motion.div
                key={`${timeRange}-usage-by-model`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="w-full h-full"
              >
                <ChartComponent
                  type="doughnut"
                  data={chartData.usageByModel}
                  options={getChartOptions('Token Usage by Model')}
                  height={300}
                />
              </motion.div>
            </AnimatePresence>
          </div>
        </motion.div>

        {/* Usage Forecast */}
        <motion.div 
          className="bg-white rounded-lg shadow p-6 border border-gray-200 dark:bg-gray-800 dark:border-gray-700"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.3 }}
        >
          <div className="flex items-center mb-4">
            <TrendingUp className="h-5 w-5 text-indigo-600 dark:text-indigo-400 mr-2" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white">Token Usage Forecast</h3>
          </div>
          <div className="h-80">
            <AnimatePresence mode="wait">
              <motion.div
                key={`${timeRange}-usage-forecast`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="w-full h-full"
              >
                <ChartComponent
                  type="line"
                  data={chartData.usageForecast}
                  options={getChartOptions('Token Usage Forecast')}
                  height={300}
                />
              </motion.div>
            </AnimatePresence>
          </div>
        </motion.div>

        {/* Cost Forecast */}
        <motion.div 
          className="bg-white rounded-lg shadow p-6 border border-gray-200 dark:bg-gray-800 dark:border-gray-700 lg:col-span-2"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.4 }}
        >
          <div className="flex items-center mb-4">
            <TrendingUp className="h-5 w-5 text-amber-600 dark:text-amber-400 mr-2" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white">Cost Forecast</h3>
          </div>
          <div className="h-80">
            <AnimatePresence mode="wait">
              <motion.div
                key={`${timeRange}-cost-forecast`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="w-full h-full"
              >
                <ChartComponent
                  type="line"
                  data={chartData.costForecast}
                  options={getChartOptions('Cost Forecast (USD)')}
                  height={300}
                />
              </motion.div>
            </AnimatePresence>
          </div>
        </motion.div>
      </div>
    </motion.div>
  );
};

export default TokenUsageDashboard;