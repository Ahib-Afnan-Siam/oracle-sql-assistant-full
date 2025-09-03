// src/components/HybridMetadataDisplay.tsx
import React, { useState } from "react";
import { Brain, Clock, TrendingUp, ChevronDown, ChevronUp, Info } from "lucide-react";

type HybridMetadata = {
  processing_mode?: string;
  model_used?: string;
  selection_reasoning?: string;
  processing_time?: number;
  local_confidence?: number;
  api_confidence?: number;
};

interface Props {
  metadata: HybridMetadata;
  responseTime?: number;
  compact?: boolean;
}

const HybridMetadataDisplay: React.FC<Props> = ({ metadata, responseTime, compact = false }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!metadata || Object.keys(metadata).length === 0) {
    return null;
  }

  const getModelDisplayName = (modelName?: string) => {
    if (!modelName) return "Unknown";
    if (modelName.includes("deepseek")) return "DeepSeek API";
    if (modelName.includes("llama")) return "Llama 3.1 (Local)";
    if (modelName.includes("local")) return "Local Model";
    if (modelName.includes("api")) return "API Model";
    return modelName;
  };

  const getProcessingModeDisplay = (mode?: string) => {
    switch (mode) {
      case "hybrid_parallel": return "Hybrid (Both Models)";
      case "api_preferred": return "API Preferred";
      case "local_only": return "Local Only";
      case "api_only": return "API Only";
      case "forced_hybrid": return "Forced Hybrid";
      default: return mode || "Standard";
    }
  };

  const getConfidenceColor = (confidence?: number) => {
    if (!confidence) return "text-gray-500";
    if (confidence >= 0.8) return "text-green-600";
    if (confidence >= 0.6) return "text-yellow-600";
    return "text-red-600";
  };

  const formatTime = (timeMs?: number) => {
    if (!timeMs) return "—";
    if (timeMs < 1000) return `${timeMs}ms`;
    return `${(timeMs / 1000).toFixed(1)}s`;
  };

  if (compact) {
    return (
      <div className="bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 text-xs">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Brain size={12} className="text-blue-600" />
            <span className="text-blue-800 font-medium">
              {getModelDisplayName(metadata.model_used)}
            </span>
            {metadata.processing_mode && (
              <span className="text-blue-600">
                ({getProcessingModeDisplay(metadata.processing_mode)})
              </span>
            )}
          </div>
          {responseTime && (
            <div className="flex items-center gap-1 text-blue-700">
              <Clock size={12} />
              <span>{formatTime(responseTime)}</span>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg overflow-hidden">
      {/* Header - Always Visible */}
      <div 
        className="px-3 py-2 cursor-pointer hover:bg-blue-100 transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Brain size={14} className="text-blue-600" />
            <span className="text-blue-800 font-medium text-sm">
              Hybrid AI Response
            </span>
            <span className="text-blue-600 text-xs">
              via {getModelDisplayName(metadata.model_used)}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {responseTime && (
              <div className="flex items-center gap-1 text-blue-700 text-xs">
                <Clock size={12} />
                <span>{formatTime(responseTime)}</span>
              </div>
            )}
            {isExpanded ? (
              <ChevronUp size={14} className="text-blue-600" />
            ) : (
              <ChevronDown size={14} className="text-blue-600" />
            )}
          </div>
        </div>
      </div>

      {/* Expanded Details */}
      {isExpanded && (
        <div className="px-3 pb-3 border-t border-blue-200 bg-blue-25">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3 text-xs">
            {/* Processing Mode */}
            {metadata.processing_mode && (
              <div className="flex items-center justify-between">
                <span className="text-gray-600">Processing Mode:</span>
                <span className="font-medium text-blue-800">
                  {getProcessingModeDisplay(metadata.processing_mode)}
                </span>
              </div>
            )}

            {/* Model Used */}
            <div className="flex items-center justify-between">
              <span className="text-gray-600">Model Used:</span>
              <span className="font-medium text-blue-800">
                {getModelDisplayName(metadata.model_used)}
              </span>
            </div>

            {/* Processing Time */}
            {metadata.processing_time && (
              <div className="flex items-center justify-between">
                <span className="text-gray-600">AI Processing:</span>
                <span className="font-medium text-blue-800">
                  {formatTime(metadata.processing_time * 1000)}
                </span>
              </div>
            )}

            {/* Confidence Scores */}
            {(metadata.local_confidence !== undefined || metadata.api_confidence !== undefined) && (
              <div className="md:col-span-2">
                <div className="text-gray-600 mb-1">Confidence Scores:</div>
                <div className="flex gap-4">
                  {metadata.local_confidence !== undefined && (
                    <div className="flex items-center gap-1">
                      <span className="text-gray-500">Local:</span>
                      <span className={`font-medium ${getConfidenceColor(metadata.local_confidence)}`}>
                        {(metadata.local_confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  )}
                  {metadata.api_confidence !== undefined && (
                    <div className="flex items-center gap-1">
                      <span className="text-gray-500">API:</span>
                      <span className={`font-medium ${getConfidenceColor(metadata.api_confidence)}`}>
                        {(metadata.api_confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Selection Reasoning */}
            {metadata.selection_reasoning && (
              <div className="md:col-span-2">
                <div className="text-gray-600 mb-1">Selection Reasoning:</div>
                <div className="text-gray-800 bg-white p-2 rounded border text-xs leading-relaxed">
                  {metadata.selection_reasoning}
                </div>
              </div>
            )}
          </div>

          {/* Performance Indicator */}
          <div className="flex items-center gap-1 mt-3 pt-2 border-t border-blue-150">
            <TrendingUp size={12} className="text-green-600" />
            <span className="text-green-700 text-xs font-medium">
              Enhanced with AI-powered response selection
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

export default HybridMetadataDisplay;