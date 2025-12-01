import React from 'react';

interface GridProps {
  children: React.ReactNode;
  className?: string;
  gap?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
  cols?: {
    xs?: number;
    sm?: number;
    md?: number;
    lg?: number;
    xl?: number;
  };
  minChildWidth?: string;
  autoFit?: boolean;
}

interface GridItemProps {
  children: React.ReactNode;
  className?: string;
  colSpan?: number;
  xs?: number;
  sm?: number;
  md?: number;
  lg?: number;
  xl?: number;
}

const GridItem: React.FC<GridItemProps> = ({ 
  children, 
  className = '',
  colSpan = 1,
  xs,
  sm,
  md,
  lg,
  xl
}) => {
  const getResponsiveClasses = () => {
    const classes = [];
    
    // Handle colSpan for backward compatibility
    if (colSpan > 1 && !md) {
      classes.push(`md:col-span-${colSpan}`);
    }
    
    // Handle responsive column spans
    if (xs) classes.push(`col-span-${xs}`);
    if (sm) classes.push(`sm:col-span-${sm}`);
    if (md) classes.push(`md:col-span-${md}`);
    if (lg) classes.push(`lg:col-span-${lg}`);
    if (xl) classes.push(`xl:col-span-${xl}`);
    
    return classes.join(' ');
  };
  
  return (
    <div className={`${getResponsiveClasses()} ${className}`}>
      {children}
    </div>
  );
};

const Grid: React.FC<GridProps> & { Item: React.FC<GridItemProps> } = ({
  children,
  className = '',
  gap = 'md',
  cols = { xs: 1, sm: 1, md: 2, lg: 3, xl: 4 },
  minChildWidth,
  autoFit = false
}) => {
  const gapClasses = {
    xs: 'gap-2',
    sm: 'gap-4',
    md: 'gap-6',
    lg: 'gap-8',
    xl: 'gap-10'
  };
  
  // Generate responsive grid column classes
  const getGridColsClasses = () => {
    if (autoFit && minChildWidth) {
      // Auto-fit grid with minmax
      return `grid-cols-[repeat(auto-fit,minmax(${minChildWidth},1fr))]`;
    }
    
    const colClasses = [
      cols.xs ? `grid-cols-${cols.xs}` : 'grid-cols-1',
      cols.sm ? `sm:grid-cols-${cols.sm}` : 'sm:grid-cols-1',
      cols.md ? `md:grid-cols-${cols.md}` : 'md:grid-cols-2',
      cols.lg ? `lg:grid-cols-${cols.lg}` : 'lg:grid-cols-3',
      cols.xl ? `xl:grid-cols-${cols.xl}` : 'xl:grid-cols-4'
    ];
    
    return colClasses.join(' ');
  };
  
  return (
    <div className={`grid ${getGridColsClasses()} ${gapClasses[gap]} ${className}`}>
      {children}
    </div>
  );
};

Grid.Item = GridItem;

export default Grid;