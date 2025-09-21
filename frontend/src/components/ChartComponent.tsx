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
          const newInstance = new Chart(canvasRef.current, {
            type,
            data,
            options: {
              responsive: true,
              maintainAspectRatio: false,
              ...options,
            },
          });
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
