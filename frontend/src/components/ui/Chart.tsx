import React from 'react';
import ChartComponent from '../ChartComponent';
import type { ChartComponentHandle } from '../ChartComponent';

interface ChartProps {
  title?: string;
  type: "bar" | "line" | "pie" | "doughnut";
  data: {
    labels: string[];
    datasets: {
      label: string;
      data: number[];
      backgroundColor?: string | string[];
      borderColor?: string | string[];
      borderWidth?: number;
    }[];
  };
  options?: any;
  height?: number;
  className?: string;
}

const Chart: React.FC<ChartProps> = ({ 
  title, 
  type, 
  data, 
  options = {}, 
  height = 400,
  className = '' 
}) => {
  return (
    <div className={`bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700 ${className}`}>
      {title && (
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">{title}</h3>
      )}
      <div className="h-64 flex items-center justify-center">
        {data.labels.length > 0 ? (
          <ChartComponent
            type={type}
            data={data}
            options={options}
            height={height}
          />
        ) : (
          <div className="text-center">
            <div className="text-gray-500 dark:text-gray-400">No data available</div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Chart;