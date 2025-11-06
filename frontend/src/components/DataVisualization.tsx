// src/components/DataVisualization.tsx
import React, {
  useState,
  useMemo,
  useRef,
  useCallback,
  forwardRef,
  useImperativeHandle,
} from "react";
import ChartComponent from "./ChartComponent";
import type { ChartComponentHandle } from "./ChartComponent";
import { determineChartType, formatChartData } from "../utils/chartUtils";
import { BarChart, LineChart, PieChart, Donut, AlertTriangle } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

// Public handle exposed to parent (DataTable)
export type DataVisualizationHandle = {
  isReady: () => boolean; // chart canvas mounted?
  getChartDataUrl: (
    type?: "image/png" | "image/jpeg",
    quality?: number
  ) => string | null;     // snapshot of what's visible
  getCanvas: () => HTMLCanvasElement | null; // optional low-level access
};

interface DataVisualizationProps {
  columns: string[];
  rows: any[] | (string | number | null)[][];
}

const DataVisualization = forwardRef<DataVisualizationHandle, DataVisualizationProps>(
  ({ columns, rows }, ref) => {
    // Normalize rows to objects
    const normalizedRows = useMemo(() => {
      if (Array.isArray(rows[0])) {
        const arr = (rows as (string | number | null)[][]).map((row) => {
          const obj: Record<string, any> = {};
          columns.forEach((col, idx) => {
            obj[col] = row[idx];
          });
          return obj;
        });
        return arr;
      }
      return rows as any[];
    }, [rows, columns]);

    // Check if dataset is too large for visualization
    const isLargeDataset = normalizedRows.length > 50000;
    
    // Initial chart type
    const [chartType, setChartType] = useState<"bar" | "line" | "pie" | "doughnut">(
      determineChartType(columns, normalizedRows)
    );

    // Chart data for selected type
    const chartData = useMemo(
      () => formatChartData(columns, normalizedRows, chartType),
      [columns, normalizedRows, chartType]
    );

    // Chart ref
    const chartRef = useRef<ChartComponentHandle>(null);

    /** Legend toggle (stable reference) */
    const handleLegendClick = useCallback((_: any, legendItem: any, legend: any) => {
      const idx = legendItem.datasetIndex;
      if (idx === undefined) return;
      const ci = legend.chart;
      const meta = ci.getDatasetMeta(idx);
      meta.hidden = meta.hidden === null ? !ci.data.datasets[idx].hidden : null;
      ci.update();
    }, []);

    /** Memoized options so the chart isn't recreated on every render */
    const chartOptions = useMemo(
      () => ({
        plugins: {
          legend: {
            position: "top" as const,
            labels: { 
              usePointStyle: true,
              color: document.documentElement.classList.contains('dark') ? '#f9fafb' : '#374151'
            },
            onClick: handleLegendClick,
          },
          title: {
            display: true,
            text: `${columns.join(", ")} Data Visualization`,
            color: document.documentElement.classList.contains('dark') ? '#f9fafb' : '#374151'
          },
        },
        responsive: true,
        maintainAspectRatio: false,
        scales: document.documentElement.classList.contains('dark') ? {
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
              color: '#d1d5db'
            },
            grid: {
              color: '#374151'
            }
          }
        } : {}
      }),
      [handleLegendClick, columns]
    );

    // ---- Expose minimal API to the parent (DataTable) ----
    useImperativeHandle(ref, () => ({
      isReady: () => !!chartRef.current?.getCanvas(),
      getChartDataUrl: (type = "image/png", quality = 0.95) =>
        chartRef.current?.getImageDataUrl?.(type, quality) ?? null,
      getCanvas: () => chartRef.current?.getCanvas() ?? null,
    }));

    // For very large datasets, show a warning and option to proceed
    const [showLargeDatasetWarning, setShowLargeDatasetWarning] = useState(isLargeDataset);
    const [forceRenderChart, setForceRenderChart] = useState(false);

    if (isLargeDataset && showLargeDatasetWarning && !forceRenderChart) {
      return (
        <motion.div 
          className="bg-white rounded-lg shadow p-4 dark:bg-gray-800"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
        >
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-medium dark:text-gray-100">Data Visualization</h3>
          </div>
          
          <div className="bg-yellow-50 border-l-4 border-yellow-400 p-4 dark:bg-yellow-900/20 dark:border-yellow-600">
            <div className="flex">
              <div className="flex-shrink-0">
                <AlertTriangle className="h-5 w-5 text-yellow-400 dark:text-yellow-500" />
              </div>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-yellow-800 dark:text-yellow-200">
                  Large Dataset Detected
                </h3>
                <div className="mt-2 text-sm text-yellow-700 dark:text-yellow-300">
                  <p>
                    This dataset contains {normalizedRows.length.toLocaleString()} rows, which may cause performance issues when visualizing.
                    We'll automatically sample the data for better performance, showing approximately 1,000 data points.
                  </p>
                </div>
                <div className="mt-4">
                  <div className="flex space-x-3">
                    <button
                      type="button"
                      onClick={() => {
                        setShowLargeDatasetWarning(false);
                        setForceRenderChart(true);
                      }}
                      className="inline-flex items-center px-3 py-2 border border-transparent text-sm leading-4 font-medium rounded-md shadow-sm text-white bg-yellow-600 hover:bg-yellow-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-yellow-500 dark:bg-yellow-700 dark:hover:bg-yellow-800"
                    >
                      Visualize with Sampling
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowLargeDatasetWarning(false)}
                      className="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-yellow-500 dark:bg-gray-700 dark:text-gray-100 dark:border-gray-600 dark:hover:bg-gray-600"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </motion.div>
      );
    }

    return (
      <motion.div 
        className="bg-white rounded-lg shadow p-4 dark:bg-gray-800 w-full max-w-2xl md:max-w-3xl lg:max-w-4xl xl:max-w-5xl 2xl:max-w-6xl mx-auto"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <div className="flex justify-between items-center mb-4 flex-wrap gap-2">
          <h3 className="text-lg font-medium dark:text-gray-100">Data Visualization</h3>
          {/* Chart type select with icons */}
          <div className="relative">
            <select
              value={chartType}
              onChange={(e) => setChartType(e.target.value as any)}
              className="appearance-none pl-10 pr-8 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-purple-500 focus:border-primary-purple-500 bg-white shadow-sm dark:bg-gray-700 dark:border-gray-600 dark:text-gray-100"
            >
              <option value="bar" className="dark:bg-gray-700 dark:text-gray-100">Bar Chart</option>
              <option value="line" className="dark:bg-gray-700 dark:text-gray-100">Line Chart</option>
              <option value="pie" className="dark:bg-gray-700 dark:text-gray-100">Pie Chart</option>
              <option value="doughnut" className="dark:bg-gray-700 dark:text-gray-100">Doughnut Chart</option>
            </select>
            <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center px-2 text-gray-700 dark:text-gray-300">
              {chartType === "bar" && <BarChart size={18} className="text-primary-purple-600" />}
              {chartType === "line" && <LineChart size={18} className="text-primary-purple-600" />}
              {chartType === "pie" && <PieChart size={18} className="text-primary-purple-600" />}
              {chartType === "doughnut" && <Donut size={18} className="text-primary-purple-600" />}
            </div>
          </div>
        </div>

        {/* Info banner for large datasets */}
        {isLargeDataset && (
          <div className="mb-4 p-3 bg-blue-50 rounded-lg text-sm text-blue-800 dark:bg-blue-900/20 dark:text-blue-200">
            <div className="flex items-start">
              <AlertTriangle className="h-5 w-5 text-blue-500 mr-2 flex-shrink-0 mt-0.5 dark:text-blue-400" />
              <div>
                <p className="font-medium">Large Dataset Visualization</p>
                <p>
                  Showing sampled data ({chartData.labels.length.toLocaleString()} points) from {normalizedRows.length.toLocaleString()} total rows for performance.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Chart with smooth transition */}
        <div className="chart-container" style={{ height: "400px" }}>
          <AnimatePresence mode="wait">
            <motion.div
              key={chartType}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
              className="w-full h-full"
            >
              <ChartComponent
                ref={chartRef}
                type={chartType}
                data={chartData}
                options={chartOptions}
              />
            </motion.div>
          </AnimatePresence>
        </div>
      </motion.div>
    );
  }
);

export default DataVisualization;