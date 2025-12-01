import React from 'react';

interface CardProps {
  title?: string;
  children: React.ReactNode;
  className?: string;
  actions?: React.ReactNode;
}

const Card: React.FC<CardProps> = ({ title, children, className = '', actions }) => {
  return (
    <div className={`bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700 ${className}`}>
      {title && (
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h2>
          {actions && <div>{actions}</div>}
        </div>
      )}
      <div>{children}</div>
    </div>
  );
};

export default Card;