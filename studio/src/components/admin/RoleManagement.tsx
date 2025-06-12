import React, { useState, useEffect, useCallback } from 'react';
import { Shield, Plus, Edit2, Trash2, Users, ChevronRight, Lock } from 'lucide-react';
import { useWorkflowApi } from '../../hooks/useWorkflowApi';

interface Role {
  role_id: string;
  name: string;
  description: string;
  permissions: string[];
  parent_role_id?: string;
  attributes: Record<string, any>;
  is_system: boolean;
  created_at: string;
}

interface RoleHierarchy extends Role {
  children?: RoleHierarchy[];
}

export const RoleManagement: React.FC = () => {
  const { executeWorkflow } = useWorkflowApi();
  const [roles, setRoles] = useState<Role[]>([]);
  const [roleHierarchy, setRoleHierarchy] = useState<RoleHierarchy[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [expandedRoles, setExpandedRoles] = useState<Set<string>>(new Set());

  // Fetch roles
  const fetchRoles = useCallback(async () => {
    setLoading(true);
    try {
      const result = await executeWorkflow('admin_list_roles', {
        include_system: true
      });

      setRoles(result.roles || []);

      // Build hierarchy
      const hierarchy = buildRoleHierarchy(result.roles || []);
      setRoleHierarchy(hierarchy);
    } catch (error) {
      console.error('Failed to fetch roles:', error);
    } finally {
      setLoading(false);
    }
  }, [executeWorkflow]);

  useEffect(() => {
    fetchRoles();
  }, [fetchRoles]);

  // Build role hierarchy
  const buildRoleHierarchy = (roles: Role[]): RoleHierarchy[] => {
    const roleMap = new Map<string, RoleHierarchy>();
    const rootRoles: RoleHierarchy[] = [];

    // Create map of all roles
    roles.forEach(role => {
      roleMap.set(role.role_id, { ...role, children: [] });
    });

    // Build hierarchy
    roles.forEach(role => {
      const roleNode = roleMap.get(role.role_id)!;
      if (role.parent_role_id) {
        const parent = roleMap.get(role.parent_role_id);
        if (parent) {
          parent.children = parent.children || [];
          parent.children.push(roleNode);
        } else {
          rootRoles.push(roleNode);
        }
      } else {
        rootRoles.push(roleNode);
      }
    });

    return rootRoles;
  };

  // Create role
  const handleCreateRole = async (roleData: Partial<Role>) => {
    try {
      await executeWorkflow('admin_create_role', {
        role_data: roleData
      });
      setShowCreateModal(false);
      fetchRoles();
    } catch (error) {
      console.error('Failed to create role:', error);
    }
  };

  // Update role
  const handleUpdateRole = async (roleId: string, updates: Partial<Role>) => {
    try {
      await executeWorkflow('admin_update_role', {
        role_id: roleId,
        updates
      });
      fetchRoles();
    } catch (error) {
      console.error('Failed to update role:', error);
    }
  };

  // Delete role
  const handleDeleteRole = async (roleId: string) => {
    if (!confirm('Are you sure you want to delete this role? All users with this role will be affected.')) return;

    try {
      await executeWorkflow('admin_delete_role', {
        role_id: roleId
      });
      fetchRoles();
    } catch (error) {
      console.error('Failed to delete role:', error);
    }
  };

  // Toggle role expansion
  const toggleRoleExpansion = (roleId: string) => {
    const newExpanded = new Set(expandedRoles);
    if (newExpanded.has(roleId)) {
      newExpanded.delete(roleId);
    } else {
      newExpanded.add(roleId);
    }
    setExpandedRoles(newExpanded);
  };

  // Render role hierarchy
  const renderRoleHierarchy = (role: RoleHierarchy, level = 0) => {
    const hasChildren = role.children && role.children.length > 0;
    const isExpanded = expandedRoles.has(role.role_id);

    return (
      <div key={role.role_id} className="mb-2">
        <div
          className={`flex items-center p-3 rounded-lg hover:bg-gray-50 ${
            level > 0 ? 'ml-' + (level * 8) : ''
          }`}
          style={{ marginLeft: level * 32 + 'px' }}
        >
          {hasChildren && (
            <button
              onClick={() => toggleRoleExpansion(role.role_id)}
              className="mr-2"
            >
              <ChevronRight
                className={`h-4 w-4 text-gray-400 transition-transform ${
                  isExpanded ? 'transform rotate-90' : ''
                }`}
              />
            </button>
          )}

          <div className="flex-1 flex items-center">
            <Shield className="h-5 w-5 text-gray-400 mr-3" />
            <div className="flex-1">
              <div className="flex items-center">
                <h3 className="text-sm font-medium text-gray-900">{role.name}</h3>
                {role.is_system && (
                  <Lock className="h-4 w-4 text-gray-400 ml-2" title="System role" />
                )}
              </div>
              <p className="text-xs text-gray-500">{role.description}</p>
              <div className="mt-1 flex flex-wrap gap-1">
                {role.permissions.slice(0, 3).map((perm) => (
                  <span
                    key={perm}
                    className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700"
                  >
                    {perm}
                  </span>
                ))}
                {role.permissions.length > 3 && (
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700">
                    +{role.permissions.length - 3} more
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 ml-4">
            <button
              onClick={() => setSelectedRole(role)}
              className="p-1 text-blue-600 hover:text-blue-900"
              disabled={role.is_system}
            >
              <Edit2 className="h-4 w-4" />
            </button>
            <button
              onClick={() => handleDeleteRole(role.role_id)}
              className="p-1 text-red-600 hover:text-red-900"
              disabled={role.is_system}
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        </div>

        {hasChildren && isExpanded && (
          <div>
            {role.children!.map((child) => renderRoleHierarchy(child, level + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Role Management</h1>
        <p className="text-gray-600">Define roles and permissions for your organization</p>
      </div>

      {/* Actions */}
      <div className="mb-6 flex justify-between items-center">
        <div className="text-sm text-gray-600">
          {roles.length} roles defined
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2"
        >
          <Plus className="h-5 w-5" />
          Create Role
        </button>
      </div>

      {/* Role Hierarchy */}
      <div className="bg-white rounded-lg shadow">
        <div className="p-4 border-b border-gray-200">
          <h2 className="text-lg font-medium text-gray-900">Role Hierarchy</h2>
        </div>

        <div className="p-4">
          {loading ? (
            <div className="flex justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            </div>
          ) : roleHierarchy.length === 0 ? (
            <p className="text-center text-gray-500 py-8">No roles defined yet</p>
          ) : (
            <div>
              {roleHierarchy.map((role) => renderRoleHierarchy(role))}
            </div>
          )}
        </div>
      </div>

      {/* Create/Edit Modal */}
      {(showCreateModal || selectedRole) && (
        <RoleFormModal
          role={selectedRole}
          roles={roles}
          onClose={() => {
            setShowCreateModal(false);
            setSelectedRole(null);
          }}
          onSubmit={selectedRole ?
            (data) => handleUpdateRole(selectedRole.role_id, data) :
            handleCreateRole
          }
        />
      )}
    </div>
  );
};

// Role Form Modal Component
interface RoleFormModalProps {
  role?: Role | null;
  roles: Role[];
  onClose: () => void;
  onSubmit: (data: Partial<Role>) => Promise<void>;
}

const RoleFormModal: React.FC<RoleFormModalProps> = ({ role, roles, onClose, onSubmit }) => {
  const [formData, setFormData] = useState({
    name: role?.name || '',
    description: role?.description || '',
    parent_role_id: role?.parent_role_id || '',
    permissions: role?.permissions || [],
    attributes: role?.attributes || {}
  });

  const [newPermission, setNewPermission] = useState('');

  const availablePermissions = [
    'users:read', 'users:create', 'users:update', 'users:delete',
    'roles:read', 'roles:create', 'roles:update', 'roles:delete',
    'audit:read', 'audit:export',
    'security:read', 'security:manage',
    'system:read', 'system:configure',
    'reports:read', 'reports:create'
  ];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await onSubmit(formData);
    onClose();
  };

  const addPermission = () => {
    if (newPermission && !formData.permissions.includes(newPermission)) {
      setFormData({
        ...formData,
        permissions: [...formData.permissions, newPermission]
      });
      setNewPermission('');
    }
  };

  const removePermission = (permission: string) => {
    setFormData({
      ...formData,
      permissions: formData.permissions.filter(p => p !== permission)
    });
  };

  return (
    <div className="fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full p-6 max-h-[90vh] overflow-y-auto">
        <h2 className="text-xl font-bold mb-4">
          {role ? 'Edit Role' : 'Create New Role'}
        </h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Role Name
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
              rows={3}
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Parent Role (Optional)
            </label>
            <select
              value={formData.parent_role_id}
              onChange={(e) => setFormData({ ...formData, parent_role_id: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              <option value="">No parent role</option>
              {roles
                .filter(r => r.role_id !== role?.role_id)
                .map(r => (
                  <option key={r.role_id} value={r.role_id}>
                    {r.name}
                  </option>
                ))
              }
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Permissions
            </label>

            <div className="flex gap-2 mb-2">
              <select
                value={newPermission}
                onChange={(e) => setNewPermission(e.target.value)}
                className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Select permission...</option>
                {availablePermissions
                  .filter(p => !formData.permissions.includes(p))
                  .map(p => (
                    <option key={p} value={p}>{p}</option>
                  ))
                }
              </select>
              <button
                type="button"
                onClick={addPermission}
                className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300"
              >
                Add
              </button>
            </div>

            <div className="space-y-2">
              {formData.permissions.map((permission) => (
                <div
                  key={permission}
                  className="flex items-center justify-between p-2 bg-gray-50 rounded"
                >
                  <span className="text-sm font-medium">{permission}</span>
                  <button
                    type="button"
                    onClick={() => removePermission(permission)}
                    className="text-red-600 hover:text-red-800"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div className="flex justify-end gap-3 mt-6">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              {role ? 'Update' : 'Create'} Role
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
