// src/components/ChartComponent.tsx
import React, {
  useRef,
  useEffect,
  useState,
  forwardRef,
  useImperativeHandle,
} from "react";
import Chart from "chart.js/auto";

export type ChartComponentHandle = {
  getImageDataUrl: (
    type?: "image/png" | "image/jpeg",
    quality?: number
  ) => string | null;
  getChart: () => Chart | null;
  getCanvas: () => HTMLCanvasElement | null;
};

interface ChartComponentProps {
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
  width?: number;
}

const ChartComponent = forwardRef<ChartComponentHandle, ChartComponentProps>(
  ({ type, data, options = {}, height = 400, width = 600 }, ref) => {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const [chartInstance, setChartInstance] = useState<Chart | null>(null);

    // Expose live getters to parent
    useImperativeHandle(ref, () => ({
      getImageDataUrl: (imgType = "image/png", quality = 0.92) => {
        if (!canvasRef.current) return null;
        return canvasRef.current.toDataURL(imgType, quality);
      },
      getChart: () => chartInstance,
      getCanvas: () => canvasRef.current,
    }));

    useEffect(() => {
      if (chartInstance) {
        chartInstance.destroy();
      }

      if (canvasRef.current) {
        try {
          // OPTIMIZATION: Configure Chart.js for better performance with large datasets
          const chartConfig = {
            type,
            data,
            options: {
              responsive: true,
              maintainAspectRatio: false,
              // Performance optimizations
              animation: {
                duration: 0 // Disable animations for large datasets
              },
              hover: {
                animationDuration: 0 // Disable hover animations
              },
              responsiveAnimationDuration: 0, // Disable resize animations
              // Reduce the number of ticks for better performance
              scales: {
                ...options.scales,
                x: {
                  ...options.scales?.x,
                  // For bar and line charts with many data points, limit the number of ticks
                  ticks: {
                    ...options.scales?.x?.ticks,
                    maxTicksLimit: 20, // Limit x-axis ticks
                    autoSkip: true,
                    autoSkipPadding: 10
                  }
                },
                y: {
                  ...options.scales?.y,
                  // For y-axis, also limit ticks
                  ticks: {
                    ...options.scales?.y?.ticks,
                    maxTicksLimit: 15, // Limit y-axis ticks
                    autoSkip: true
                  }
                }
              },
              plugins: {
                ...options.plugins,
                // Optimize legend for performance
                legend: {
                  ...options.plugins?.legend,
                  labels: {
                    ...options.plugins?.legend?.labels,
                    usePointStyle: true,
                    // Reduce legend item rendering for large datasets
                    filter: (item: any, chart: any) => {
                      // For very large datasets, only show first few legend items
                      if (data.labels.length > 1000) {
                        return chart.data.datasets.findIndex((d: any) => d.label === item.text) < 3;
                      }
                      return true;
                    }
                  }
                }
              },
              // For pie/doughnut charts with many segments, group small values
              ...(type === 'pie' || type === 'doughnut') && data.labels.length > 50 && {
                plugins: {
                  ...options.plugins,
                  tooltip: {
                    ...options.plugins?.tooltip,
                    callbacks: {
                      label: function(context: any) {
                        return `${context.label}: ${context.parsed}`;
                      }
                    }
                  }
                }
              }
            },
          };

          const newInstance = new Chart(canvasRef.current, chartConfig);
          setChartInstance(newInstance);
        } catch (e) {
          console.error("Chart init error:", e);
        }
      }

      return () => {
        chartInstance?.destroy();
      };
    }, [type, data, options]);

    return (
      <div
        style={{
          height: `${height}px`,
          width: "100%",
          maxWidth: `${width}px`,
          margin: "0 auto",
        }}
      >
        <canvas ref={canvasRef} />
      </div>
    );
  }
);

export default ChartComponent;