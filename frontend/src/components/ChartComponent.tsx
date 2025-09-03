import React, { useRef, useEffect, useState } from 'react';
import Chart from 'chart.js/auto';

interface ChartComponentProps {
  type: 'bar' | 'line' | 'pie' | 'doughnut';
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
  width?: number;
}

const ChartComponent: React.FC<ChartComponentProps> = ({ 
  type, 
  data, 
  options = {}, 
  height = 400, 
  width = 600 
}) => {
  const chartRef = useRef<HTMLCanvasElement>(null);
  const [chartInstance, setChartInstance] = useState<Chart | null>(null);

  useEffect(() => {
    console.log('ChartComponent - Props:', { type, data, options });
    
    // Destroy previous chart instance if it exists
    if (chartInstance) {
      console.log('ChartComponent - Destroying previous chart instance');
      chartInstance.destroy();
    }

    // Create new chart instance
    if (chartRef.current) {
      console.log('ChartComponent - Creating new chart instance');
      console.log('ChartComponent - Canvas element:', chartRef.current);
      
      try {
        const newChartInstance = new Chart(chartRef.current, {
          type,
          data,
          options: {
            responsive: true,
            maintainAspectRatio: false,
            ...options
          }
        });
        
        console.log('ChartComponent - Chart instance created:', newChartInstance);
        setChartInstance(newChartInstance);
      } catch (error) {
        console.error('ChartComponent - Error creating chart:', error);
      }
    } else {
      console.log('ChartComponent - No canvas element found');
    }

    // Cleanup function
    return () => {
      if (chartInstance) {
        console.log('ChartComponent - Cleaning up chart instance');
        chartInstance.destroy();
      }
    };
  }, [type, data, options]);

  return (
    <div style={{ height: `${height}px`, width: '100%', maxWidth: `${width}px`, margin: '0 auto' }}>
      <canvas ref={chartRef}></canvas>
    </div>
  );
};

export default ChartComponent;