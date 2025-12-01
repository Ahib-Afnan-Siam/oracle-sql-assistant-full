import React from 'react';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  fullWidth?: boolean;
  icon?: React.ReactNode;
}

const Input: React.FC<InputProps> = ({
  label,
  error,
  fullWidth = false,
  icon,
  className = '',
  ...props
}) => {
  const baseClasses = 'block w-full rounded-lg border shadow-sm focus:ring-2 focus:ring-offset-2 dark:focus:ring-offset-gray-900 sm:text-sm';
  
  const normalClasses = 'border-gray-300 focus:ring-purple-500 focus:border-purple-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white';
  const errorClasses = 'border-red-300 text-red-900 placeholder-red-300 focus:ring-red-500 focus:border-red-500 dark:border-red-600 dark:text-red-300 dark:placeholder-red-400';
  
  const classes = [
    baseClasses,
    error ? errorClasses : normalClasses,
    fullWidth ? 'w-full' : '',
    className
  ].join(' ');
  
  return (
    <div className={fullWidth ? 'w-full' : ''}>
      {label && (
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          {label}
        </label>
      )}
      <div className="relative rounded-md shadow-sm">
        {icon && (
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            {icon}
          </div>
        )}
        <input
          className={`${classes} ${icon ? 'pl-10' : ''}`}
          {...props}
        />
      </div>
      {error && (
        <p className="mt-1 text-sm text-red-600 dark:text-red-400">{error}</p>
      )}
    </div>
  );
};

export default Input;