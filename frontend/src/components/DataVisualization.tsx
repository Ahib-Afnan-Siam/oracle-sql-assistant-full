import React, { useState, useEffect } from 'react';
import ChartComponent from './ChartComponent';
import { determineChartType, formatChartData } from '../utils/chartUtils';

interface DataVisualizationProps {
  columns: string[];
  rows: any[] | (string | number | null)[][];
  onBackToTable: () => void;
}

const DataVisualization: React.FC<DataVisualizationProps> = ({ 
  columns, 
  rows, 
  onBackToTable 
}) => {
  // Add debugging
  useEffect(() => {
    console.log('DataVisualization component rendered');
    console.log('Columns:', columns);
    console.log('Rows:', rows);
  }, [columns, rows]);

  // Convert array data to object format if needed
  const normalizedRows = Array.isArray(rows[0]) 
    ? (rows as (string | number | null)[][]).map(row => {
        const obj: any = {};
        columns.forEach((col, index) => {
          obj[col] = row[index];
        });
        return obj;
      })
    : (rows as any[]);

  // Add debugging for normalized data
  useEffect(() => {
    console.log('Normalized rows:', normalizedRows);
  }, [normalizedRows]);

  // Auto-determine chart type based on data structure
  const [chartType, setChartType] = useState<'bar' | 'line' | 'pie' | 'doughnut'>(
    determineChartType(columns, normalizedRows)
  );
  
  // Add debugging for chart type
  useEffect(() => {
    console.log('Chart type:', chartType);
  }, [chartType]);

  // Format data for Chart.js
  const chartData = formatChartData(columns, normalizedRows, chartType);
  
  // Add debugging for chart data
  useEffect(() => {
    console.log('Chart data:', chartData);
  }, [chartData]);

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-medium">Data Visualization</h3>
        <div className="flex space-x-2">
          <select 
            value={chartType}
            onChange={(e) => setChartType(e.target.value as any)}
            className="px-3 py-1 border border-gray-300 rounded text-sm"
          >
            <option value="bar">Bar Chart</option>
            <option value="line">Line Chart</option>
            <option value="pie">Pie Chart</option>
            <option value="doughnut">Doughnut Chart</option>
          </select>
          <button 
            onClick={onBackToTable}
            className="px-3 py-1 bg-gray-200 hover:bg-gray-300 rounded text-sm"
          >
            Back to Table
          </button>
        </div>
      </div>
      
      <div className="chart-container" style={{ height: '400px' }}>
        <ChartComponent 
          type={chartType} 
          data={chartData} 
          options={{
            plugins: {
              legend: {
                position: 'top',
              },
              title: {
                display: true,
                text: `${columns.join(', ')} Data Visualization`
              }
            }
          }} 
        />
      </div>
    </div>
  );
};

export default DataVisualization;