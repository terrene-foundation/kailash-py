import React from 'react';
import { cn } from '../../utils/cn';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  variant?: 'default' | 'bordered' | 'elevated';
  padding?: 'none' | 'sm' | 'md' | 'lg';
}

export const Card: React.FC<CardProps> & {
  Header: React.FC<{ children: React.ReactNode; className?: string }>;
  Body: React.FC<{ children: React.ReactNode; className?: string }>;
  Footer: React.FC<{ children: React.ReactNode; className?: string }>;
} = ({ children, className, variant = 'default', padding = 'md' }) => {
  const variantClasses = {
    default: 'bg-white',
    bordered: 'bg-white border border-gray-200',
    elevated: 'bg-white shadow-md',
  };

  const paddingClasses = {
    none: '',
    sm: 'p-3',
    md: 'p-6',
    lg: 'p-8',
  };

  return (
    <div
      className={cn(
        'rounded-lg',
        variantClasses[variant],
        paddingClasses[padding],
        className
      )}
    >
      {children}
    </div>
  );
};

Card.Header = ({ children, className }) => (
  <div className={cn('pb-4 border-b border-gray-200', className)}>
    {children}
  </div>
);

Card.Body = ({ children, className }) => (
  <div className={cn('py-4', className)}>{children}</div>
);

Card.Footer = ({ children, className }) => (
  <div className={cn('pt-4 border-t border-gray-200', className)}>
    {children}
  </div>
);
