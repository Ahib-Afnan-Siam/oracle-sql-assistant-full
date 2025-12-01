import React, { useState, useEffect } from 'react';
import { 
  BarChart3, 
  LineChart, 
  PieChart, 
  Calendar, 
  TrendingUp, 
  Users, 
  MessageSquare, 
  Database,
  AlertTriangle
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
}

interface ChartData {
  labels: string[];
  datasets: ChartDataset[];
}

interface AnalyticsData {
  userGrowth: ChartData;
  chatVolume: ChartData;
  tokenUsage: ChartData;
  feedbackDistribution: ChartData;
  queryPerformance: ChartData;
  responseTime: ChartData;
  hourlyTokenUsage: ChartData;
  userAccess: {
    totalUsers: number;
    activeUsers: number;
    pendingRequests: number;
  };
}

const AnalyticsDashboard: React.FC = () => {
  const [timeRange, setTimeRange] = useState<'daily' | 'weekly' | 'monthly'>('weekly');
  const [analyticsData, setAnalyticsData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [totalChats, setTotalChats] = useState<number>(3457); // Default value

  const timeRanges: TimeRange[] = [
    { value: 'daily', label: 'Daily' },
    { value: 'weekly', label: 'Weekly' },
    { value: 'monthly', label: 'Monthly' }
  ];

  // Fetch total chats count
  const fetchTotalChats = async () => {
    try {
      const token = localStorage.getItem("authToken");
      const response = await fetch("/api/admin/dashboard/total-chats", {
        headers: {
          "Authorization": `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.success && data.total_chats !== undefined) {
          setTotalChats(data.total_chats);
        }
      } else {
        console.error("Failed to fetch total chats. Status:", response.status);
      }
    } catch (err) {
      console.error('Error fetching total chats:', err);
    }
  };

  // Fetch analytics data
  useEffect(() => {
    const fetchAnalyticsData = async () => {
      try {
        setLoading(true);
        setError(null);
        
        const token = localStorage.getItem("authToken");
        
        // Fetch total chats first
        await fetchTotalChats();
        
        // Fetch both analytics data and time series data
        const [analyticsResponse, timeSeriesResponse] = await Promise.all([
          fetch("/api/admin/dashboard/analytics", {
            headers: {
              "Authorization": `Bearer ${token}`
            }
          }),
          fetch(`/api/admin/dashboard/analytics/time-series?time_range=${timeRange}`, {
            headers: {
              "Authorization": `Bearer ${token}`
            }
          })
        ]);
        
        if (analyticsResponse.ok && timeSeriesResponse.ok) {
          const analyticsData = await analyticsResponse.json();
          const timeSeriesData = await timeSeriesResponse.json();
          
          console.log("Analytics data:", analyticsData);
          console.log("Time series data:", timeSeriesData);
          
          if (analyticsData.success && analyticsData.data && timeSeriesData.success && timeSeriesData.data) {
            // Transform the data for charts
            const transformedData = transformAnalyticsData(
              analyticsData.data.analytics, 
              timeSeriesData.data, 
              timeRange
            );
            setAnalyticsData(transformedData);
          }
        } else {
          console.error("Failed to fetch analytics data. Status:", analyticsResponse.status, timeSeriesResponse.status);
          setError('Failed to load analytics data. Please try again later.');
        }
      } catch (err) {
        console.error('Error fetching analytics data:', err);
        setError('Failed to load analytics data. Please try again later.');
      } finally {
        setLoading(false);
      }
    };

    fetchAnalyticsData();
  }, [timeRange]);

  // Transform analytics data for charts
  const transformAnalyticsData = (analytics: any, timeSeries: any, range: 'daily' | 'weekly' | 'monthly'): AnalyticsData => {
    // Transform time series data for charts
    const userGrowthData = timeSeries.user_growth || [];
    const chatVolumeData = timeSeries.chat_volume || [];
    const tokenUsageData = timeSeries.token_usage || [];
    const responseTimeData = timeSeries.response_time || [];
    const hourlyTokenUsageData = timeSeries.hourly_token_usage || [];
    const userAccessGrowthData = timeSeries.user_access_growth || [];
    
    // Create labels based on the time range
    const createUserGrowthLabels = () => {
      return userGrowthData.map((item: any) => {
        // Handle both old 'date' and new 'creation_date' column names
        const dateValue = item.date || item.creation_date;
        const date = new Date(dateValue);
        if (range === 'daily') return date.toLocaleDateString();
        if (range === 'weekly') return `Week of ${date.toLocaleDateString()}`;
        return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
      });
    };
    
    const createChatVolumeLabels = () => {
      return chatVolumeData.map((item: any) => {
        // Handle both old 'date' and new 'chat_date' column names
        const dateValue = item.date || item.chat_date;
        const date = new Date(dateValue);
        if (range === 'daily') return date.toLocaleDateString();
        if (range === 'weekly') return `Week of ${date.toLocaleDateString()}`;
        return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
      });
    };
    
    const createTokenUsageLabels = () => {
      return tokenUsageData.map((item: any) => {
        // Handle both old 'date' and new 'usage_date' column names
        const dateValue = item.date || item.usage_date;
        const date = new Date(dateValue);
        if (range === 'daily') return date.toLocaleDateString();
        if (range === 'weekly') return `Week of ${date.toLocaleDateString()}`;
        return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
      });
    };
    
    const createResponseTimeLabels = () => {
      return responseTimeData.map((item: any) => {
        // Handle both old 'date' and new 'chat_date' column names
        const dateValue = item.date || item.chat_date;
        const date = new Date(dateValue);
        if (range === 'daily') return date.toLocaleDateString();
        if (range === 'weekly') return `Week of ${date.toLocaleDateString()}`;
        return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
      });
    };
    
    const createHourlyTokenUsageLabels = () => {
      return hourlyTokenUsageData.map((item: any) => {
        const date = new Date(item.hour);
        return date.toLocaleString('en-US', { 
          month: 'short', 
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit'
        });
      });
    };
    
    // Create user access growth labels
    const createUserAccessGrowthLabels = () => {
      return userAccessGrowthData.map((item: any) => {
        const dateValue = item.creation_date;
        const date = new Date(dateValue);
        if (range === 'daily') return date.toLocaleDateString();
        if (range === 'weekly') return `Week of ${date.toLocaleDateString()}`;
        return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
      });
    };

    // Feedback Distribution Data (from feedback in analytics)
    const feedbackData = {
      good: analytics.feedback?.good_feedback || 0,
      wrong: analytics.feedback?.wrong_feedback || 0,
      needsImprovement: analytics.feedback?.needs_improvement_feedback || 0
    };

    // Query Performance Data (from queries in analytics)
    const querySuccess = analytics.queries?.successful_queries || 0;
    const queryError = analytics.queries?.error_queries || 0;
    const queryTimeout = analytics.queries?.timeout_queries || 0;

    // User Access Data
    const userAccessData = {
      totalUsers: analytics.user_access?.total_users || 0,
      activeUsers: analytics.user_access?.active_users || 0,
      pendingRequests: analytics.user_access?.pending_requests || 0
    };

    // Determine performance color based on response time (in seconds)
    const getPerformanceColor = (responseTime: number) => {
      if (responseTime < 1) return 'rgba(16, 185, 129, 0.7)'; // Green - Good performance
      if (responseTime < 3) return 'rgba(245, 158, 11, 0.7)'; // Yellow - Moderate latency
      return 'rgba(239, 68, 68, 0.7)'; // Red - High latency
    };

    return {
      userGrowth: {
        labels: createUserGrowthLabels(),
        datasets: [
          {
            label: 'New Users',
            data: userGrowthData.map((item: any) => item.new_users || 0),
            backgroundColor: 'rgba(139, 92, 246, 0.7)',
            borderColor: 'rgba(139, 92, 246, 1)',
            borderWidth: 2
          }
        ]
      },
      chatVolume: {
        labels: createChatVolumeLabels(),
        datasets: [
          {
            label: 'Chat Sessions',
            data: chatVolumeData.map((item: any) => item.chat_count || 0),
            backgroundColor: 'rgba(59, 130, 246, 0.7)',
            borderColor: 'rgba(59, 130, 246, 1)',
            borderWidth: 2
          }
        ]
      },
      tokenUsage: {
        labels: createTokenUsageLabels(),
        datasets: [
          {
            label: 'Tokens Consumed',
            data: tokenUsageData.map((item: any) => item.total_tokens || 0),
            backgroundColor: 'rgba(16, 185, 129, 0.7)',
            borderColor: 'rgba(16, 185, 129, 1)',
            borderWidth: 2
          }
        ]
      },
      feedbackDistribution: {
        labels: ['Good', 'Wrong', 'Needs Improvement'],
        datasets: [
          {
            label: 'Feedback Distribution',
            data: [feedbackData.good, feedbackData.wrong, feedbackData.needsImprovement],
            backgroundColor: [
              'rgba(16, 185, 129, 0.7)',
              'rgba(239, 68, 68, 0.7)',
              'rgba(245, 158, 11, 0.7)'
            ],
            borderColor: [
              'rgba(16, 185, 129, 1)',
              'rgba(239, 68, 68, 1)',
              'rgba(245, 158, 11, 1)'
            ],
            borderWidth: 2
          }
        ]
      },
      queryPerformance: {
        labels: ['Success', 'Error', 'Timeout'],
        datasets: [
          {
            label: 'Query Performance',
            data: [querySuccess, queryError, queryTimeout],
            backgroundColor: [
              'rgba(16, 185, 129, 0.7)',
              'rgba(239, 68, 68, 0.7)',
              'rgba(156, 163, 175, 0.7)'
            ],
            borderColor: [
              'rgba(16, 185, 129, 1)',
              'rgba(239, 68, 68, 1)',
              'rgba(156, 163, 175, 1)'
            ],
            borderWidth: 2
          }
        ]
      },
      responseTime: {
        labels: createResponseTimeLabels(),
        datasets: [
          {
            label: 'Average Response Time (seconds)',
            data: responseTimeData.map((item: any) => {
              const avgTime = item.avg_response_time || 0;
              return parseFloat(avgTime.toFixed(2));
            }),
            backgroundColor: responseTimeData.map((item: any) => 
              getPerformanceColor(item.avg_response_time || 0)
            ),
            borderColor: responseTimeData.map((item: any) => 
              getPerformanceColor(item.avg_response_time || 0).replace('0.7', '1')
            ),
            borderWidth: 2
          }
        ]
      },
      hourlyTokenUsage: {
        labels: createHourlyTokenUsageLabels(),
        datasets: [
          {
            label: 'Tokens Consumed',
            data: hourlyTokenUsageData.map((item: any) => item.total_tokens || 0),
            backgroundColor: 'rgba(16, 185, 129, 0.7)',
            borderColor: 'rgba(16, 185, 129, 1)',
            borderWidth: 2
          },
          {
            label: 'Estimated Cost (USD)',
            data: hourlyTokenUsageData.map((item: any) => {
              const cost = item.total_cost || 0;
              return parseFloat(cost.toFixed(4));
            }),
            backgroundColor: 'rgba(59, 130, 246, 0.7)',
            borderColor: 'rgba(59, 130, 246, 1)',
            borderWidth: 2,
            yAxisID: 'y1'
          }
        ]
      },
      userAccess: userAccessData
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
                } else if (title.includes('Response Time')) {
                  // For response time, show in seconds with appropriate units
                  label += context.parsed.y.toFixed(2) + ' seconds';
                } else if (title.includes('Tokens')) {
                  // For token counts, show with commas
                  label += new Intl.NumberFormat('en-US').format(context.parsed.y);
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
              if (title.includes('Response Time')) {
                return value + 's';
              } else if (title.includes('Tokens')) {
                return new Intl.NumberFormat('en-US').format(value);
              } else if (title.includes('Cost')) {
                return '$' + value.toFixed(2);
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
              if (title.includes('Response Time')) {
                return value + 's';
              } else if (title.includes('Tokens')) {
                return new Intl.NumberFormat('en-US').format(value);
              } else if (title.includes('Cost')) {
                return '$' + value.toFixed(2);
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
          <h3 className="text-lg font-medium dark:text-gray-100">Analytics Dashboard</h3>
        </div>
        
        <div className="bg-red-50 border-l-4 border-red-400 p-4 dark:bg-red-900/20 dark:border-red-600">
          <div className="flex">
            <div className="flex-shrink-0">
              <AlertTriangle className="h-5 w-5 text-red-400 dark:text-red-500" />
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
      {/* Time Range Selector */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white">Analytics & Insights</h2>
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
      </div>

      {/* Key Metrics Summary */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="bg-white rounded-lg shadow p-6 border border-gray-200 dark:bg-gray-800 dark:border-gray-700">
          <div className="flex items-center">
            <div className="p-3 rounded-full bg-purple-100 dark:bg-purple-900">
              <Users className="h-6 w-6 text-purple-600 dark:text-purple-400" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Users</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {analyticsData?.userAccess?.totalUsers?.toLocaleString() || '0'}
              </p>
              <p className="text-sm text-green-500 flex items-center">
                <TrendingUp className="h-4 w-4 mr-1" />
                <span>+12% from last period</span>
              </p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6 border border-gray-200 dark:bg-gray-800 dark:border-gray-700">
          <div className="flex items-center">
            <div className="p-3 rounded-full bg-blue-100 dark:bg-blue-900">
              <MessageSquare className="h-6 w-6 text-blue-600 dark:text-blue-400" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Chats</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{totalChats.toLocaleString()}</p>
              <p className="text-sm text-green-500 flex items-center">
                <TrendingUp className="h-4 w-4 mr-1" />
                <span>+8% from last period</span>
              </p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6 border border-gray-200 dark:bg-gray-800 dark:border-gray-700">
          <div className="flex items-center">
            <div className="p-3 rounded-full bg-green-100 dark:bg-green-900">
              <Database className="h-6 w-6 text-green-600 dark:text-green-400" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Tokens Used</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {analyticsData?.tokenUsage?.datasets?.[0]?.data?.reduce((a: number, b: number) => a + b, 0)?.toLocaleString() || '0'}
              </p>
              <p className="text-sm text-red-500 flex items-center">
                <TrendingUp className="h-4 w-4 mr-1 rotate-180" />
                <span>+3% from last period</span>
              </p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6 border border-gray-200 dark:bg-gray-800 dark:border-gray-700">
          <div className="flex items-center">
            <div className="p-3 rounded-full bg-amber-100 dark:bg-amber-900">
              <PieChart className="h-6 w-6 text-amber-600 dark:text-amber-400" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Avg. Response Time</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">420ms</p>
              <p className="text-sm text-green-500 flex items-center">
                <TrendingUp className="h-4 w-4 mr-1 rotate-180" />
                <span>-5% from last period</span>
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* User Growth Chart */}
        <motion.div 
          className="bg-white rounded-lg shadow p-6 border border-gray-200 dark:bg-gray-800 dark:border-gray-700"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
        >
          <div className="flex items-center mb-4">
            <LineChart className="h-5 w-5 text-purple-600 dark:text-purple-400 mr-2" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white">User Growth</h3>
          </div>
          <div className="h-80">
            <AnimatePresence mode="wait">
              <motion.div
                key={`${timeRange}-user-growth`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="w-full h-full"
              >
                {analyticsData?.userGrowth && (
                  <ChartComponent
                    type="line"
                    data={analyticsData.userGrowth}
                    options={getChartOptions('New Users Over Time')}
                    height={300}
                  />
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        </motion.div>

        {/* Chat Volume Chart */}
        <motion.div 
          className="bg-white rounded-lg shadow p-6 border border-gray-200 dark:bg-gray-800 dark:border-gray-700"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.1 }}
        >
          <div className="flex items-center mb-4">
            <BarChart3 className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-2" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white">Chat Volume</h3>
          </div>
          <div className="h-80">
            <AnimatePresence mode="wait">
              <motion.div
                key={`${timeRange}-chat-volume`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="w-full h-full"
              >
                {analyticsData?.chatVolume && (
                  <ChartComponent
                    type="bar"
                    data={analyticsData.chatVolume}
                    options={getChartOptions('Chat Sessions Over Time')}
                    height={300}
                  />
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        </motion.div>

        {/* Token Usage Chart */}
        <motion.div 
          className="bg-white rounded-lg shadow p-6 border border-gray-200 dark:bg-gray-800 dark:border-gray-700"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.2 }}
        >
          <div className="flex items-center mb-4">
            <Database className="h-5 w-5 text-green-600 dark:text-green-400 mr-2" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white">Token Usage</h3>
          </div>
          <div className="h-80">
            <AnimatePresence mode="wait">
              <motion.div
                key={`${timeRange}-token-usage`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="w-full h-full"
              >
                {analyticsData?.tokenUsage && (
                  <ChartComponent
                    type="line"
                    data={analyticsData.tokenUsage}
                    options={getChartOptions('Tokens Consumed Over Time')}
                    height={300}
                  />
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        </motion.div>

        {/* Response Time Analysis Chart */}
        <motion.div 
          className="bg-white rounded-lg shadow p-6 border border-gray-200 dark:bg-gray-800 dark:border-gray-700"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.3 }}
        >
          <div className="flex items-center mb-4">
            <TrendingUp className="h-5 w-5 text-indigo-600 dark:text-indigo-400 mr-2" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white">Response Time Analysis</h3>
          </div>
          <div className="h-80">
            <AnimatePresence mode="wait">
              <motion.div
                key={`${timeRange}-response-time`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="w-full h-full"
              >
                {analyticsData?.responseTime && (
                  <ChartComponent
                    type="bar"
                    data={analyticsData.responseTime}
                    options={getChartOptions('Average Response Time (seconds)')}
                    height={300}
                  />
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        </motion.div>

        {/* Hourly Token Usage Chart */}
        <motion.div 
          className="bg-white rounded-lg shadow p-6 border border-gray-200 dark:bg-gray-800 dark:border-gray-700 lg:col-span-2"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.4 }}
        >
          <div className="flex items-center mb-4">
            <Database className="h-5 w-5 text-green-600 dark:text-green-400 mr-2" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white">Hourly Token Usage & Cost</h3>
          </div>
          <div className="h-80">
            <AnimatePresence mode="wait">
              <motion.div
                key={`${timeRange}-hourly-token-usage`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="w-full h-full"
              >
                {analyticsData?.hourlyTokenUsage && (
                  <ChartComponent
                    type="line"
                    data={analyticsData.hourlyTokenUsage}
                    options={getChartOptions('Hourly Token Usage & Cost', true)}
                    height={300}
                  />
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        </motion.div>
      </div>

      {/* Additional Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Feedback Distribution Chart */}
        <motion.div 
          className="bg-white rounded-lg shadow p-6 border border-gray-200 dark:bg-gray-800 dark:border-gray-700"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.5 }}
        >
          <div className="flex items-center mb-4">
            <PieChart className="h-5 w-5 text-amber-600 dark:text-amber-400 mr-2" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white">Feedback Distribution</h3>
          </div>
          <div className="h-80">
            <AnimatePresence mode="wait">
              <motion.div
                key={`${timeRange}-feedback`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="w-full h-full"
              >
                {analyticsData?.feedbackDistribution && (
                  <ChartComponent
                    type="doughnut"
                    data={analyticsData.feedbackDistribution}
                    options={getChartOptions('User Feedback')}
                    height={300}
                  />
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        </motion.div>

        {/* Query Performance Chart */}
        <motion.div 
          className="bg-white rounded-lg shadow p-6 border border-gray-200 dark:bg-gray-800 dark:border-gray-700"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.6 }}
        >
          <div className="flex items-center mb-4">
            <BarChart3 className="h-5 w-5 text-indigo-600 dark:text-indigo-400 mr-2" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white">Query Performance</h3>
          </div>
          <div className="h-80">
            <AnimatePresence mode="wait">
              <motion.div
                key={`${timeRange}-query-performance`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="w-full h-full"
              >
                {analyticsData?.queryPerformance && (
                  <ChartComponent
                    type="bar"
                    data={analyticsData.queryPerformance}
                    options={getChartOptions('Query Execution Status')}
                    height={300}
                  />
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        </motion.div>
        
        {/* User Access Growth Chart */}
        <motion.div 
          className="bg-white rounded-lg shadow p-6 border border-gray-200 dark:bg-gray-800 dark:border-gray-700 lg:col-span-2"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.7 }}
        >
          <div className="flex items-center mb-4">
            <Users className="h-5 w-5 text-purple-600 dark:text-purple-400 mr-2" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white">User Access Growth</h3>
          </div>
          <div className="h-80">
            <AnimatePresence mode="wait">
              <motion.div
                key={`${timeRange}-user-access-growth`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="w-full h-full"
              >
                {analyticsData?.userGrowth && (
                  <ChartComponent
                    type="line"
                    data={analyticsData.userGrowth}
                    options={getChartOptions('User Access Growth Over Time')}
                    height={300}
                  />
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        </motion.div>
      </div>
    </motion.div>
  );
};

export default AnalyticsDashboard;