import React from 'react';
import { TrendingUp, TrendingDown, BarChart2 } from 'react-feather';

interface MetricCardProps {
  title: string;
  value: string | number;
  icon: React.ReactNode;
  trend?: string;
  trendIcon?: React.ReactNode;
  className?: string;
}

const MetricCard: React.FC<MetricCardProps> = ({ 
  title, 
  value, 
  icon, 
  trend, 
  trendIcon,
  className = '' 
}) => {
  // Helper function to determine trend color
  const getTrendColor = (trendValue: string) => {
    if (trendValue?.startsWith('+')) {
      return 'text-green-500';
    } else if (trendValue?.startsWith('-')) {
      return 'text-red-500';
    } else {
      return 'text-yellow-500';
    }
  };

  // Helper function to determine trend icon
  const getTrendIcon = (trendValue: string) => {
    if (trendValue?.startsWith('+')) {
      return <TrendingUp size={14} />;
    } else if (trendValue?.startsWith('-')) {
      return <TrendingDown size={14} />;
    } else {
      return <BarChart2 size={14} />;
    }
  };

  return (
    <div className={`bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700 ${className}`}>
      <div className="flex items-center">
        <div className="p-3 rounded-full bg-purple-100 dark:bg-purple-900">
          {icon}
        </div>
        <div className="ml-4">
          <p className="text-sm font-medium text-gray-500 dark:text-gray-400">{title}</p>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">{value}</p>
          {trend && (
            <p className={`text-sm flex items-center mt-1 ${getTrendColor(trend)}`}>
              <span className="mr-1">{trendIcon || getTrendIcon(trend)}</span>
              <span>{trend}</span>
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default MetricCard;