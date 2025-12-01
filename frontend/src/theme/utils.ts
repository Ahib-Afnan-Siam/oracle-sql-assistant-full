import { theme } from './index';

// Utility functions for consistent styling
export const cn = (...classes: (string | undefined | null | false)[]): string => {
  return classes.filter(Boolean).join(' ');
};

// Get color classes for consistent styling
export const getColorClass = (color: string, shade: number | string = 500): string => {
  return `text-${color}-${shade} dark:text-${color}-${shade}`;
};

// Get background color classes
export const getBgClass = (color: string, shade: number | string = 500): string => {
  return `bg-${color}-${shade} dark:bg-${color}-${shade}`;
};

// Get border color classes
export const getBorderClass = (color: string, shade: number | string = 300): string => {
  return `border-${color}-${shade} dark:border-${color}-${shade}`;
};

// Get shadow classes
export const getShadowClass = (size: keyof typeof theme.shadows): string => {
  return `shadow-${size}`;
};

// Get spacing classes
export const getSpacingClass = (type: 'p' | 'm', size: keyof typeof theme.spacing): string => {
  return `${type}-${size}`;
};

// Get responsive grid classes
export const getGridClass = (cols: { xs?: number; sm?: number; md?: number; lg?: number; xl?: number }): string => {
  const classes = [];
  if (cols.xs) classes.push(`grid-cols-${cols.xs}`);
  if (cols.sm) classes.push(`sm:grid-cols-${cols.sm}`);
  if (cols.md) classes.push(`md:grid-cols-${cols.md}`);
  if (cols.lg) classes.push(`lg:grid-cols-${cols.lg}`);
  if (cols.xl) classes.push(`xl:grid-cols-${cols.xl}`);
  return classes.join(' ');
};

// Get responsive flex classes
export const getFlexClass = (direction: 'row' | 'col' = 'row', wrap: boolean = false): string => {
  const classes = [`flex-${direction}`];
  if (wrap) classes.push('flex-wrap');
  return classes.join(' ');
};

// Get rounded classes
export const getRoundedClass = (size: keyof typeof theme.borderRadius): string => {
  return `rounded-${size}`;
};

// Get font classes
export const getFontClass = (size: keyof typeof theme.typography.fontSize, weight: keyof typeof theme.typography.fontWeight = 'normal'): string => {
  return `text-${size} font-${weight}`;
};

// Get button classes with consistent styling
export const getButtonClass = (variant: 'primary' | 'secondary' | 'success' | 'warning' | 'danger' | 'outline' = 'primary', size: 'sm' | 'md' | 'lg' = 'md'): string => {
  const baseClasses = 'inline-flex items-center justify-center rounded-md font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 dark:focus:ring-offset-gray-900';
  
  const variantClasses = {
    primary: 'bg-purple-600 text-white hover:bg-purple-700 focus:ring-purple-500 dark:bg-purple-600 dark:hover:bg-purple-700 dark:focus:ring-purple-500',
    secondary: 'bg-gray-100 text-gray-900 hover:bg-gray-200 focus:ring-gray-500 dark:bg-gray-700 dark:text-white dark:hover:bg-gray-600 dark:focus:ring-gray-500',
    success: 'bg-green-600 text-white hover:bg-green-700 focus:ring-green-500 dark:bg-green-600 dark:hover:bg-green-700 dark:focus:ring-green-500',
    warning: 'bg-yellow-600 text-white hover:bg-yellow-700 focus:ring-yellow-500 dark:bg-yellow-600 dark:hover:bg-yellow-700 dark:focus:ring-yellow-500',
    danger: 'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500 dark:bg-red-600 dark:hover:bg-red-700 dark:focus:ring-red-500',
    outline: 'border border-gray-300 bg-transparent text-gray-700 hover:bg-gray-50 focus:ring-gray-500 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700 dark:focus:ring-gray-500'
  };
  
  const sizeClasses = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2 text-sm',
    lg: 'px-6 py-3 text-base'
  };
  
  return `${baseClasses} ${variantClasses[variant]} ${sizeClasses[size]}`;
};

// Get card classes with consistent styling
export const getCardClass = (): string => {
  return 'bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700';
};

// Get panel classes with consistent styling
export const getPanelClass = (): string => {
  return 'bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700';
};

export default {
  cn,
  getColorClass,
  getBgClass,
  getBorderClass,
  getShadowClass,
  getSpacingClass,
  getGridClass,
  getFlexClass,
  getRoundedClass,
  getFontClass,
  getButtonClass,
  getCardClass,
  getPanelClass
};