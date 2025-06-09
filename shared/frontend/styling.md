# Styling & UI/UX Guidelines

This guide covers styling best practices, design systems, and responsive design patterns for Kailash frontend applications.

## 🎨 Design System Overview

### Design Principles
1. **Clarity**: Information should be clear and easily digestible
2. **Consistency**: UI elements behave predictably across the application
3. **Efficiency**: Common tasks should be quick and intuitive
4. **Accessibility**: Design for all users, regardless of ability
5. **Feedback**: Users should always know what's happening

## 🎭 Styling Architecture

### CSS Strategy
```typescript
// Recommended approach: CSS Modules + Tailwind CSS + CSS-in-JS for dynamic styles

// 1. Global styles (src/styles/global.css)
@import 'tailwindcss/base';
@import 'tailwindcss/components';
@import 'tailwindcss/utilities';

@layer base {
  :root {
    /* Color Palette */
    --color-primary: 59 130 246; /* blue-500 */
    --color-primary-dark: 29 78 216; /* blue-700 */
    --color-secondary: 107 114 128; /* gray-500 */
    --color-success: 34 197 94; /* green-500 */
    --color-warning: 245 158 11; /* amber-500 */
    --color-error: 239 68 68; /* red-500 */

    /* Spacing */
    --spacing-unit: 0.25rem;

    /* Typography */
    --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
    --font-mono: 'JetBrains Mono', 'Fira Code', monospace;

    /* Shadows */
    --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
    --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1);
    --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1);

    /* Animations */
    --animation-fast: 150ms;
    --animation-normal: 300ms;
    --animation-slow: 500ms;
  }

  /* Dark mode variables */
  .dark {
    --color-primary: 96 165 250; /* blue-400 */
    --color-primary-dark: 147 197 253; /* blue-300 */
    /* ... other dark mode colors */
  }

  * {
    @apply border-border;
  }

  body {
    @apply bg-background text-foreground;
    font-feature-settings: "rlig" 1, "calt" 1;
  }
}

@layer components {
  /* Reusable component styles */
  .btn {
    @apply inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors
           focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2
           disabled:pointer-events-none disabled:opacity-50;
  }

  .card {
    @apply rounded-lg border bg-card text-card-foreground shadow-sm;
  }

  .input {
    @apply flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm
           ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium
           placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2
           focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50;
  }
}

@layer utilities {
  /* Custom utilities */
  .animate-in {
    animation: animateIn var(--animation-normal) ease-out;
  }

  .glass-morphism {
    @apply backdrop-blur-md bg-white/80 dark:bg-gray-900/80 border border-white/20;
  }

  .gradient-primary {
    @apply bg-gradient-to-r from-blue-500 to-purple-600;
  }
}
```

### Tailwind Configuration
```javascript
// tailwind.config.js
module.exports = {
  darkMode: 'class',
  content: [
    './src/**/*.{js,jsx,ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // Custom color palette
        primary: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
        },
        // Semantic colors
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      animation: {
        'slide-in': 'slideIn 0.3s ease-out',
        'fade-in': 'fadeIn 0.3s ease-out',
        'scale-in': 'scaleIn 0.2s ease-out',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        slideIn: {
          '0%': { transform: 'translateY(-10px)', opacity: 0 },
          '100%': { transform: 'translateY(0)', opacity: 1 },
        },
        fadeIn: {
          '0%': { opacity: 0 },
          '100%': { opacity: 1 },
        },
        scaleIn: {
          '0%': { transform: 'scale(0.95)', opacity: 0 },
          '100%': { transform: 'scale(1)', opacity: 1 },
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
    require('@tailwindcss/aspect-ratio'),
  ],
};
```

## 🎨 Component Styling Patterns

### CSS Modules for Component Styles
```scss
// src/components/WorkflowCard/WorkflowCard.module.scss
.card {
  @apply relative overflow-hidden transition-all duration-300;

  &:hover {
    @apply shadow-lg transform -translate-y-1;

    .cardOverlay {
      @apply opacity-100;
    }
  }

  &.isActive {
    @apply ring-2 ring-primary ring-offset-2;
  }

  &.isError {
    @apply border-red-500;

    .statusIndicator {
      @apply bg-red-500;
    }
  }
}

.cardHeader {
  @apply flex items-center justify-between p-4 border-b;
}

.cardBody {
  @apply p-4;
}

.cardOverlay {
  @apply absolute inset-0 bg-gradient-to-t from-black/20 to-transparent
         opacity-0 transition-opacity duration-300 pointer-events-none;
}

.statusIndicator {
  @apply w-2 h-2 rounded-full animate-pulse;

  &.running {
    @apply bg-blue-500;
  }

  &.success {
    @apply bg-green-500 animate-none;
  }

  &.error {
    @apply bg-red-500 animate-none;
  }
}

// Dark mode overrides
:global(.dark) {
  .card {
    @apply bg-gray-800 border-gray-700;

    &:hover {
      @apply bg-gray-750;
    }
  }

  .cardHeader {
    @apply border-gray-700;
  }
}
```

### Styled Components Pattern
```typescript
// src/components/styled/Button.styled.ts
import styled, { css } from 'styled-components';

interface StyledButtonProps {
  variant?: 'primary' | 'secondary' | 'danger';
  size?: 'small' | 'medium' | 'large';
  fullWidth?: boolean;
}

const variantStyles = {
  primary: css`
    background-color: var(--color-primary);
    color: white;

    &:hover:not(:disabled) {
      background-color: var(--color-primary-dark);
    }
  `,
  secondary: css`
    background-color: transparent;
    color: var(--color-primary);
    border: 1px solid var(--color-primary);

    &:hover:not(:disabled) {
      background-color: var(--color-primary);
      color: white;
    }
  `,
  danger: css`
    background-color: var(--color-error);
    color: white;

    &:hover:not(:disabled) {
      background-color: var(--color-error-dark);
    }
  `,
};

const sizeStyles = {
  small: css`
    padding: 0.25rem 0.75rem;
    font-size: 0.875rem;
  `,
  medium: css`
    padding: 0.5rem 1rem;
    font-size: 1rem;
  `,
  large: css`
    padding: 0.75rem 1.5rem;
    font-size: 1.125rem;
  `,
};

export const StyledButton = styled.button<StyledButtonProps>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 0.375rem;
  font-weight: 500;
  transition: all 150ms ease;
  cursor: pointer;
  outline: none;
  border: none;

  ${({ variant = 'primary' }) => variantStyles[variant]}
  ${({ size = 'medium' }) => sizeStyles[size]}
  ${({ fullWidth }) => fullWidth && css`width: 100%;`}

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  &:focus-visible {
    box-shadow: 0 0 0 2px var(--color-background),
                0 0 0 4px var(--color-primary);
  }
`;
```

## 🌓 Dark Mode Implementation

### Theme Provider
```typescript
// src/contexts/ThemeContext.tsx
import React, { createContext, useContext, useEffect, useState } from 'react';

type Theme = 'light' | 'dark' | 'system';

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  resolvedTheme: 'light' | 'dark';
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setThemeState] = useState<Theme>(() => {
    return (localStorage.getItem('theme') as Theme) || 'system';
  });

  const [resolvedTheme, setResolvedTheme] = useState<'light' | 'dark'>('light');

  useEffect(() => {
    const root = window.document.documentElement;

    const applyTheme = (theme: Theme) => {
      if (theme === 'system') {
        const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches
          ? 'dark'
          : 'light';
        root.classList.remove('light', 'dark');
        root.classList.add(systemTheme);
        setResolvedTheme(systemTheme);
      } else {
        root.classList.remove('light', 'dark');
        root.classList.add(theme);
        setResolvedTheme(theme);
      }
    };

    applyTheme(theme);

    // Listen for system theme changes
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = () => {
      if (theme === 'system') {
        applyTheme('system');
      }
    };

    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, [theme]);

  const setTheme = (newTheme: Theme) => {
    setThemeState(newTheme);
    localStorage.setItem('theme', newTheme);
  };

  return (
    <ThemeContext.Provider value={{ theme, setTheme, resolvedTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider');
  }
  return context;
};

// Theme Toggle Component
export const ThemeToggle: React.FC = () => {
  const { theme, setTheme, resolvedTheme } = useTheme();

  return (
    <button
      onClick={() => {
        const nextTheme = theme === 'light' ? 'dark' : theme === 'dark' ? 'system' : 'light';
        setTheme(nextTheme);
      }}
      className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800"
      aria-label="Toggle theme"
    >
      {resolvedTheme === 'light' ? (
        <SunIcon className="w-5 h-5" />
      ) : (
        <MoonIcon className="w-5 h-5" />
      )}
    </button>
  );
};
```

### Dark Mode Styles
```scss
// src/styles/themes/_dark.scss
.dark {
  // Colors
  --color-background: 17 24 39; /* gray-900 */
  --color-foreground: 243 244 246; /* gray-100 */
  --color-card: 31 41 55; /* gray-800 */
  --color-card-foreground: 243 244 246; /* gray-100 */

  // Borders
  --color-border: 55 65 81; /* gray-700 */

  // Interactive elements
  --color-primary: 96 165 250; /* blue-400 */
  --color-primary-foreground: 17 24 39; /* gray-900 */

  // Syntax highlighting for code
  .code-block {
    background-color: rgb(31 41 55); /* gray-800 */

    .token {
      &.comment { color: rgb(107 114 128); }
      &.string { color: rgb(134 239 172); }
      &.keyword { color: rgb(147 197 253); }
      &.function { color: rgb(196 181 253); }
      &.number { color: rgb(251 207 232); }
    }
  }
}
```

## 📱 Responsive Design

### Breakpoint System
```typescript
// src/hooks/useBreakpoint.ts
export const breakpoints = {
  xs: 0,
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
  '2xl': 1536,
} as const;

export const useBreakpoint = () => {
  const [currentBreakpoint, setCurrentBreakpoint] = useState<keyof typeof breakpoints>('xs');

  useEffect(() => {
    const getBreakpoint = (width: number): keyof typeof breakpoints => {
      if (width >= breakpoints['2xl']) return '2xl';
      if (width >= breakpoints.xl) return 'xl';
      if (width >= breakpoints.lg) return 'lg';
      if (width >= breakpoints.md) return 'md';
      if (width >= breakpoints.sm) return 'sm';
      return 'xs';
    };

    const handleResize = () => {
      setCurrentBreakpoint(getBreakpoint(window.innerWidth));
    };

    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const isBreakpoint = (breakpoint: keyof typeof breakpoints) => {
    const currentWidth = breakpoints[currentBreakpoint];
    const targetWidth = breakpoints[breakpoint];
    return currentWidth >= targetWidth;
  };

  return { currentBreakpoint, isBreakpoint };
};
```

### Responsive Component Examples
```typescript
// src/components/layout/ResponsiveGrid/ResponsiveGrid.tsx
interface ResponsiveGridProps {
  children: React.ReactNode;
  cols?: {
    xs?: number;
    sm?: number;
    md?: number;
    lg?: number;
    xl?: number;
    '2xl'?: number;
  };
  gap?: number;
}

export const ResponsiveGrid: React.FC<ResponsiveGridProps> = ({
  children,
  cols = { xs: 1, sm: 2, md: 3, lg: 4 },
  gap = 4,
}) => {
  const gridCols = [
    cols.xs && `grid-cols-${cols.xs}`,
    cols.sm && `sm:grid-cols-${cols.sm}`,
    cols.md && `md:grid-cols-${cols.md}`,
    cols.lg && `lg:grid-cols-${cols.lg}`,
    cols.xl && `xl:grid-cols-${cols.xl}`,
    cols['2xl'] && `2xl:grid-cols-${cols['2xl']}`,
  ].filter(Boolean).join(' ');

  return (
    <div className={cn('grid', gridCols, `gap-${gap}`)}>
      {children}
    </div>
  );
};

// Responsive Navigation
export const ResponsiveNav: React.FC = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { isBreakpoint } = useBreakpoint();

  return (
    <nav className="bg-white dark:bg-gray-900 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          {/* Logo */}
          <div className="flex-shrink-0 flex items-center">
            <Logo />
          </div>

          {/* Desktop Navigation */}
          <div className="hidden md:flex md:items-center md:space-x-8">
            <NavLink href="/workflows">Workflows</NavLink>
            <NavLink href="/nodes">Nodes</NavLink>
            <NavLink href="/monitoring">Monitoring</NavLink>
          </div>

          {/* Mobile menu button */}
          <div className="flex items-center md:hidden">
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-2 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              {mobileMenuOpen ? <XIcon /> : <MenuIcon />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Navigation */}
      <AnimatePresence>
        {mobileMenuOpen && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: 'auto' }}
            exit={{ height: 0 }}
            className="md:hidden overflow-hidden"
          >
            <div className="px-2 pt-2 pb-3 space-y-1">
              <MobileNavLink href="/workflows">Workflows</MobileNavLink>
              <MobileNavLink href="/nodes">Nodes</MobileNavLink>
              <MobileNavLink href="/monitoring">Monitoring</MobileNavLink>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  );
};
```

## 🎭 Animation & Transitions

### Framer Motion Integration
```typescript
// src/components/animations/AnimatedCard.tsx
import { motion } from 'framer-motion';

interface AnimatedCardProps {
  children: React.ReactNode;
  delay?: number;
}

export const AnimatedCard: React.FC<AnimatedCardProps> = ({ children, delay = 0 }) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{
        duration: 0.3,
        delay,
        ease: [0.4, 0, 0.2, 1],
      }}
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
    >
      {children}
    </motion.div>
  );
};

// Stagger Children Animation
export const StaggeredList: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const container = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
      },
    },
  };

  const item = {
    hidden: { opacity: 0, x: -20 },
    show: { opacity: 1, x: 0 },
  };

  return (
    <motion.ul variants={container} initial="hidden" animate="show">
      {React.Children.map(children, (child, index) => (
        <motion.li key={index} variants={item}>
          {child}
        </motion.li>
      ))}
    </motion.ul>
  );
};

// Page Transitions
export const PageTransition: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      transition={{ duration: 0.3 }}
    >
      {children}
    </motion.div>
  );
};
```

### CSS Animations
```scss
// src/styles/animations.scss
@keyframes shimmer {
  0% {
    background-position: -1000px 0;
  }
  100% {
    background-position: 1000px 0;
  }
}

.skeleton {
  background: linear-gradient(
    90deg,
    theme('colors.gray.200') 0%,
    theme('colors.gray.100') 50%,
    theme('colors.gray.200') 100%
  );
  background-size: 1000px 100%;
  animation: shimmer 2s infinite;
}

.dark .skeleton {
  background: linear-gradient(
    90deg,
    theme('colors.gray.700') 0%,
    theme('colors.gray.600') 50%,
    theme('colors.gray.700') 100%
  );
}

// Pulse animation for loading states
@keyframes pulse-ring {
  0% {
    transform: scale(0.8);
    opacity: 1;
  }
  50% {
    transform: scale(1);
    opacity: 0.5;
  }
  100% {
    transform: scale(1.2);
    opacity: 0;
  }
}

.pulse-ring {
  position: relative;

  &::before {
    content: '';
    position: absolute;
    inset: -4px;
    border-radius: inherit;
    border: 2px solid currentColor;
    animation: pulse-ring 1.5s ease-out infinite;
  }
}
```

## 🎨 UI Component Library

### Form Styling
```typescript
// src/components/forms/FormField/FormField.tsx
interface FormFieldProps {
  label: string;
  error?: string;
  required?: boolean;
  children: React.ReactNode;
  helpText?: string;
}

export const FormField: React.FC<FormFieldProps> = ({
  label,
  error,
  required,
  children,
  helpText,
}) => {
  return (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-200">
        {label}
        {required && <span className="text-red-500 ml-1">*</span>}
      </label>

      {children}

      {helpText && !error && (
        <p className="text-sm text-gray-500 dark:text-gray-400">{helpText}</p>
      )}

      {error && (
        <motion.p
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-sm text-red-600 dark:text-red-400"
        >
          {error}
        </motion.p>
      )}
    </div>
  );
};

// Custom styled input
export const StyledInput: React.FC<InputProps> = (props) => {
  return (
    <input
      className={cn(
        'block w-full rounded-md',
        'border-gray-300 dark:border-gray-600',
        'bg-white dark:bg-gray-800',
        'text-gray-900 dark:text-gray-100',
        'shadow-sm',
        'focus:border-primary-500 focus:ring-primary-500',
        'disabled:bg-gray-50 dark:disabled:bg-gray-900',
        'disabled:text-gray-500 dark:disabled:text-gray-400',
        'placeholder-gray-400 dark:placeholder-gray-500',
        'transition-colors duration-200',
        props.error && 'border-red-500 focus:border-red-500 focus:ring-red-500',
        props.className
      )}
      {...props}
    />
  );
};
```

### Data Display Components
```typescript
// src/components/data/DataTable/DataTable.tsx
interface DataTableProps<T> {
  data: T[];
  columns: Column<T>[];
  onRowClick?: (row: T) => void;
  loading?: boolean;
  emptyMessage?: string;
}

export function DataTable<T>({
  data,
  columns,
  onRowClick,
  loading,
  emptyMessage = 'No data available',
}: DataTableProps<T>) {
  if (loading) {
    return <DataTableSkeleton columns={columns.length} rows={5} />;
  }

  if (data.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500 dark:text-gray-400">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden shadow ring-1 ring-black ring-opacity-5 md:rounded-lg">
      <table className="min-w-full divide-y divide-gray-300 dark:divide-gray-700">
        <thead className="bg-gray-50 dark:bg-gray-800">
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                className="px-6 py-3 text-left text-xs font-medium text-gray-500
                          dark:text-gray-400 uppercase tracking-wider"
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-800">
          {data.map((row, rowIndex) => (
            <motion.tr
              key={rowIndex}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: rowIndex * 0.05 }}
              onClick={() => onRowClick?.(row)}
              className={cn(
                'hover:bg-gray-50 dark:hover:bg-gray-800',
                'transition-colors duration-150',
                onRowClick && 'cursor-pointer'
              )}
            >
              {columns.map((column) => (
                <td
                  key={column.key}
                  className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-gray-100"
                >
                  {column.render ? column.render(row) : row[column.key]}
                </td>
              ))}
            </motion.tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

## 🎯 Accessibility Styling

### Focus Management
```scss
// src/styles/accessibility.scss
// Focus visible styles
.focus-ring {
  @apply focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2
         focus-visible:ring-primary-500 dark:focus-visible:ring-primary-400;
}

// Skip to content link
.skip-to-content {
  @apply absolute top-0 left-0 bg-primary-600 text-white p-2 rounded-md
         transform -translate-y-full focus:translate-y-0 transition-transform
         duration-200 z-50;
}

// Screen reader only text
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}

// High contrast mode support
@media (prefers-contrast: high) {
  .card {
    border-width: 2px;
  }

  .btn {
    border: 2px solid currentColor;
  }
}

// Reduced motion
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

### ARIA Styling Helpers
```typescript
// src/components/a11y/AriaLive.tsx
interface AriaLiveProps {
  message: string;
  priority?: 'polite' | 'assertive';
}

export const AriaLive: React.FC<AriaLiveProps> = ({ message, priority = 'polite' }) => {
  return (
    <div
      role="status"
      aria-live={priority}
      aria-atomic="true"
      className="sr-only"
    >
      {message}
    </div>
  );
};

// Loading spinner with proper ARIA
export const AccessibleSpinner: React.FC<{ label?: string }> = ({ label = 'Loading' }) => {
  return (
    <div role="status" aria-label={label}>
      <svg
        className="animate-spin h-5 w-5 text-primary-600"
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <circle
          className="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="4"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
        />
      </svg>
      <span className="sr-only">{label}</span>
    </div>
  );
};
```

## 📐 Design Tokens

### Token System
```typescript
// src/styles/tokens.ts
export const tokens = {
  colors: {
    // Base colors
    white: '#FFFFFF',
    black: '#000000',

    // Gray scale
    gray: {
      50: '#F9FAFB',
      100: '#F3F4F6',
      200: '#E5E7EB',
      300: '#D1D5DB',
      400: '#9CA3AF',
      500: '#6B7280',
      600: '#4B5563',
      700: '#374151',
      800: '#1F2937',
      900: '#111827',
    },

    // Brand colors
    primary: {
      50: '#EFF6FF',
      // ... rest of primary scale
    },

    // Semantic colors
    success: {
      light: '#D1FAE5',
      DEFAULT: '#10B981',
      dark: '#059669',
    },
    warning: {
      light: '#FEF3C7',
      DEFAULT: '#F59E0B',
      dark: '#D97706',
    },
    error: {
      light: '#FEE2E2',
      DEFAULT: '#EF4444',
      dark: '#DC2626',
    },
  },

  spacing: {
    px: '1px',
    0: '0',
    0.5: '0.125rem',
    1: '0.25rem',
    2: '0.5rem',
    3: '0.75rem',
    4: '1rem',
    5: '1.25rem',
    6: '1.5rem',
    8: '2rem',
    10: '2.5rem',
    12: '3rem',
    16: '4rem',
    20: '5rem',
    24: '6rem',
  },

  typography: {
    fontFamily: {
      sans: ['Inter', 'system-ui', 'sans-serif'],
      mono: ['JetBrains Mono', 'monospace'],
    },
    fontSize: {
      xs: ['0.75rem', { lineHeight: '1rem' }],
      sm: ['0.875rem', { lineHeight: '1.25rem' }],
      base: ['1rem', { lineHeight: '1.5rem' }],
      lg: ['1.125rem', { lineHeight: '1.75rem' }],
      xl: ['1.25rem', { lineHeight: '1.75rem' }],
      '2xl': ['1.5rem', { lineHeight: '2rem' }],
      '3xl': ['1.875rem', { lineHeight: '2.25rem' }],
      '4xl': ['2.25rem', { lineHeight: '2.5rem' }],
    },
    fontWeight: {
      thin: '100',
      light: '300',
      normal: '400',
      medium: '500',
      semibold: '600',
      bold: '700',
      extrabold: '800',
    },
  },

  shadows: {
    sm: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
    DEFAULT: '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)',
    md: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
    lg: '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
    xl: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
  },

  animation: {
    duration: {
      fast: '150ms',
      normal: '300ms',
      slow: '500ms',
    },
    easing: {
      linear: 'linear',
      in: 'cubic-bezier(0.4, 0, 1, 1)',
      out: 'cubic-bezier(0, 0, 0.2, 1)',
      inOut: 'cubic-bezier(0.4, 0, 0.2, 1)',
    },
  },
};
```

## 🎯 Best Practices

### 1. Component Styling
- Use CSS Modules for component-specific styles
- Leverage Tailwind for utility classes
- Create reusable style compositions
- Maintain consistent naming conventions

### 2. Theme Management
- Implement proper dark mode support
- Use CSS variables for dynamic theming
- Provide theme context for components
- Test all color combinations for contrast

### 3. Responsive Design
- Mobile-first approach
- Use flexible grid systems
- Test on multiple devices
- Implement touch-friendly interfaces

### 4. Performance
- Minimize CSS bundle size
- Use CSS containment where appropriate
- Optimize animations for 60fps
- Lazy load heavy stylesheets

### 5. Accessibility
- Ensure proper color contrast (WCAG AA)
- Provide focus indicators
- Support keyboard navigation
- Test with screen readers

### 6. Consistency
- Follow design system strictly
- Document component variations
- Maintain style guide
- Regular design reviews
