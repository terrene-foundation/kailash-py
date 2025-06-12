import React from 'react';
import { cn } from '../../utils/cn';

interface GridProps {
  children: React.ReactNode;
  cols?: 1 | 2 | 3 | 4 | 6 | 12;
  gap?: 'none' | 'sm' | 'md' | 'lg';
  className?: string;
}

export const Grid: React.FC<GridProps> = ({
  children,
  cols = 1,
  gap = 'md',
  className,
}) => {
  const colClasses = {
    1: 'grid-cols-1',
    2: 'grid-cols-1 md:grid-cols-2',
    3: 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3',
    4: 'grid-cols-1 md:grid-cols-2 lg:grid-cols-4',
    6: 'grid-cols-2 md:grid-cols-3 lg:grid-cols-6',
    12: 'grid-cols-3 md:grid-cols-6 lg:grid-cols-12',
  };

  const gapClasses = {
    none: 'gap-0',
    sm: 'gap-2',
    md: 'gap-4',
    lg: 'gap-6',
  };

  return (
    <div
      className={cn('grid', colClasses[cols], gapClasses[gap], className)}
    >
      {children}
    </div>
  );
};