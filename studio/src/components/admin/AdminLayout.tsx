import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import {
  Users,
  Shield,
  FileText,
  Building2,
  Lock,
  LayoutDashboard,
  ChevronLeft
} from 'lucide-react';

interface AdminLayoutProps {
  onBackToStudio?: () => void;
}

export const AdminLayout: React.FC<AdminLayoutProps> = ({ onBackToStudio }) => {
  const navItems = [
    {
      path: '/admin',
      label: 'Security Dashboard',
      icon: LayoutDashboard,
      exact: true
    },
    {
      path: '/admin/users',
      label: 'User Management',
      icon: Users
    },
    {
      path: '/admin/roles',
      label: 'Role Management',
      icon: Shield
    },
    {
      path: '/admin/permissions',
      label: 'Permission Matrix',
      icon: Lock
    },
    {
      path: '/admin/audit',
      label: 'Audit Logs',
      icon: FileText
    },
    {
      path: '/admin/tenants',
      label: 'Tenant Management',
      icon: Building2
    }
  ];

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <div className="w-64 bg-white shadow-md">
        <div className="p-4 border-b">
          <h2 className="text-xl font-bold text-gray-900">Admin Tools</h2>
          {onBackToStudio && (
            <button
              onClick={onBackToStudio}
              className="mt-2 text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1"
            >
              <ChevronLeft className="h-4 w-4" />
              Back to Studio
            </button>
          )}
        </div>

        <nav className="p-4">
          <ul className="space-y-2">
            {navItems.map((item) => (
              <li key={item.path}>
                <NavLink
                  to={item.path}
                  end={item.exact}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-4 py-2 rounded-lg transition-colors ${
                      isActive
                        ? 'bg-blue-50 text-blue-600'
                        : 'text-gray-700 hover:bg-gray-100'
                    }`
                  }
                >
                  <item.icon className="h-5 w-5" />
                  <span>{item.label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-auto">
        <Outlet />
      </div>
    </div>
  );
};
