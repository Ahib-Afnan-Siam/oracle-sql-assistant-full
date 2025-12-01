import React from 'react';
import { Users, Activity, MessageSquare, Zap, Server } from 'react-feather';
import { MetricCard } from './ui';

const DashboardTest: React.FC = () => {
  // Sample metrics data
  const sampleMetrics = {
    users: { total: 1250, active: 312, trend: "+5%" },
    chats: { total: 3457, active: 42, completed: 3415, trend: "+12%" },
    messages: { total: 8921, userQueries: 4267, aiResponses: 4654, trend: "+8%" },
    performance: { 
      avgResponseTime: 420, 
      totalTokens: 1254300, 
      availableModels: 3, 
      totalQueries: 2891,
      trend: "+3%" 
    },
    systemStatus: 'Operational'
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">Dashboard Overview Test</h1>
      
      {/* Metrics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6 mb-8">
        <MetricCard 
          title="Total Users" 
          value={sampleMetrics.users.total} 
          icon={<Users className="h-6 w-6 text-purple-600" />}
          trend={sampleMetrics.users.trend}
        />
        <MetricCard 
          title="Active Users" 
          value={sampleMetrics.users.active} 
          icon={<Activity className="h-6 w-6 text-purple-600" />}
          trend={sampleMetrics.users.trend}
        />
        <MetricCard 
          title="Total Chats" 
          value={sampleMetrics.chats.total} 
          icon={<MessageSquare className="h-6 w-6 text-purple-600" />}
          trend={sampleMetrics.chats.trend}
        />
        <MetricCard 
          title="Avg Response Time" 
          value={`${sampleMetrics.performance.avgResponseTime}ms`} 
          icon={<Zap className="h-6 w-6 text-purple-600" />}
          trend={sampleMetrics.performance.trend}
        />
        <MetricCard 
          title="System Status" 
          value={sampleMetrics.systemStatus} 
          icon={<Server className="h-6 w-6 text-green-600" />}
        />
      </div>

      {/* Additional Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <MetricCard 
          title="Total Messages" 
          value={sampleMetrics.messages.total} 
          icon={<MessageSquare className="h-5 w-5 text-purple-600" />}
          trend={sampleMetrics.messages.trend}
        />
        <MetricCard 
          title="User Queries" 
          value={sampleMetrics.messages.userQueries} 
          icon={<Users className="h-5 w-5 text-purple-600" />}
          trend={sampleMetrics.messages.trend}
        />
        <MetricCard 
          title="AI Responses" 
          value={sampleMetrics.messages.aiResponses} 
          icon={<Server className="h-5 w-5 text-purple-600" />}
          trend={sampleMetrics.messages.trend}
        />
        <MetricCard 
          title="Total Tokens" 
          value={sampleMetrics.performance.totalTokens.toLocaleString()} 
          icon={<Activity className="h-5 w-5 text-purple-600" />}
          trend={sampleMetrics.performance.trend}
        />
      </div>
    </div>
  );
};

export default DashboardTest;