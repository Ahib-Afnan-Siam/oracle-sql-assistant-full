import React from 'react';

interface PanelProps {
  title?: string;
  children: React.ReactNode;
  className?: string;
  headerActions?: React.ReactNode;
  footer?: React.ReactNode;
}

const Panel: React.FC<PanelProps> = ({ title, children, className = '', headerActions, footer }) => {
  return (
    <div className={`bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700 ${className}`}>
      {(title || headerActions) && (
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
          {title && <h3 className="text-lg font-medium text-gray-900 dark:text-white">{title}</h3>}
          {headerActions && <div>{headerActions}</div>}
        </div>
      )}
      <div className="p-6">{children}</div>
      {footer && (
        <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/50">
          {footer}
        </div>
      )}
    </div>
  );
};

export default Panel;