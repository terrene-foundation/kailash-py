import React, { useState, useEffect, useCallback } from 'react';
import { Check, X, Minus, ChevronDown, ChevronRight, Shield, Users, Key } from 'lucide-react';
import { useWorkflowApi } from '../../hooks/useWorkflowApi';

interface Permission {
  permission_id: string;
  name: string;
  resource: string;
  action: string;
  description?: string;
}

interface Role {
  role_id: string;
  name: string;
  description: string;
  is_system: boolean;
}

interface RolePermissionMatrix {
  roles: Role[];
  permissions: Permission[];
  matrix: Record<string, Record<string, boolean>>; // role_id -> permission_id -> granted
}

export const PermissionMatrix: React.FC = () => {
  const { executeWorkflow } = useWorkflowApi();
  const [matrixData, setMatrixData] = useState<RolePermissionMatrix | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedResources, setExpandedResources] = useState<Set<string>>(new Set());
  const [selectedRole, setSelectedRole] = useState<string | null>(null);
  const [hasChanges, setHasChanges] = useState(false);
  const [pendingChanges, setPendingChanges] = useState<Record<string, Record<string, boolean>>>({});

  // Fetch permission matrix
  const fetchMatrix = useCallback(async () => {
    setLoading(true);
    try {
      const result = await executeWorkflow('admin_permission_matrix', {
        include_system_roles: true
      });
      setMatrixData(result);
      setPendingChanges({});
      setHasChanges(false);
    } catch (error) {
      console.error('Failed to fetch permission matrix:', error);
    } finally {
      setLoading(false);
    }
  }, [executeWorkflow]);

  useEffect(() => {
    fetchMatrix();
  }, [fetchMatrix]);

  // Group permissions by resource
  const groupedPermissions = React.useMemo(() => {
    if (!matrixData) return {};

    const groups: Record<string, Permission[]> = {};
    matrixData.permissions.forEach(permission => {
      if (!groups[permission.resource]) {
        groups[permission.resource] = [];
      }
      groups[permission.resource].push(permission);
    });
    return groups;
  }, [matrixData]);

  // Toggle permission
  const togglePermission = (roleId: string, permissionId: string) => {
    if (!matrixData) return;

    const role = matrixData.roles.find(r => r.role_id === roleId);
    if (role?.is_system) return; // Don't allow editing system roles

    const currentValue = pendingChanges[roleId]?.[permissionId] ??
                        matrixData.matrix[roleId]?.[permissionId] ??
                        false;

    setPendingChanges(prev => ({
      ...prev,
      [roleId]: {
        ...prev[roleId],
        [permissionId]: !currentValue
      }
    }));
    setHasChanges(true);
  };

  // Save changes
  const saveChanges = async () => {
    if (!hasChanges) return;

    try {
      await executeWorkflow('admin_update_permissions', {
        changes: pendingChanges
      });
      await fetchMatrix();
    } catch (error) {
      console.error('Failed to save permission changes:', error);
    }
  };

  // Reset changes
  const resetChanges = () => {
    setPendingChanges({});
    setHasChanges(false);
  };

  // Toggle resource expansion
  const toggleResource = (resource: string) => {
    const newExpanded = new Set(expandedResources);
    if (newExpanded.has(resource)) {
      newExpanded.delete(resource);
    } else {
      newExpanded.add(resource);
    }
    setExpandedResources(newExpanded);
  };

  // Get permission value (with pending changes)
  const getPermissionValue = (roleId: string, permissionId: string): boolean | 'inherited' => {
    if (pendingChanges[roleId]?.hasOwnProperty(permissionId)) {
      return pendingChanges[roleId][permissionId];
    }
    return matrixData?.matrix[roleId]?.[permissionId] ?? false;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!matrixData) {
    return (
      <div className="p-6 text-center text-gray-500">
        Failed to load permission matrix
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Permission Matrix</h1>
        <p className="text-gray-600">Manage role permissions across resources</p>
      </div>

      {/* Actions */}
      {hasChanges && (
        <div className="mb-4 p-4 bg-yellow-50 border border-yellow-200 rounded-lg flex items-center justify-between">
          <p className="text-sm text-yellow-800">You have unsaved changes</p>
          <div className="flex gap-2">
            <button
              onClick={resetChanges}
              className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
            >
              Reset
            </button>
            <button
              onClick={saveChanges}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Save Changes
            </button>
          </div>
        </div>
      )}

      {/* Matrix Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="sticky left-0 z-10 bg-gray-50 px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Resource / Permission
                </th>
                {matrixData.roles.map((role) => (
                  <th
                    key={role.role_id}
                    className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                    onClick={() => setSelectedRole(role.role_id === selectedRole ? null : role.role_id)}
                    title={role.description}
                  >
                    <div className="flex flex-col items-center">
                      <span className={selectedRole === role.role_id ? 'text-blue-600 font-bold' : ''}>
                        {role.name}
                      </span>
                      {role.is_system && (
                        <Shield className="h-3 w-3 text-gray-400 mt-1" />
                      )}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {Object.entries(groupedPermissions).map(([resource, permissions]) => {
                const isExpanded = expandedResources.has(resource);
                return (
                  <React.Fragment key={resource}>
                    {/* Resource Header Row */}
                    <tr className="bg-gray-50">
                      <td className="sticky left-0 z-10 bg-gray-50 px-6 py-3">
                        <button
                          onClick={() => toggleResource(resource)}
                          className="flex items-center text-sm font-medium text-gray-900 hover:text-gray-700"
                        >
                          {isExpanded ? (
                            <ChevronDown className="h-4 w-4 mr-2" />
                          ) : (
                            <ChevronRight className="h-4 w-4 mr-2" />
                          )}
                          <Key className="h-4 w-4 mr-2 text-gray-400" />
                          {resource}
                        </button>
                      </td>
                      {matrixData.roles.map((role) => {
                        // Calculate aggregate for resource
                        const allPermissions = permissions.every(p =>
                          getPermissionValue(role.role_id, p.permission_id)
                        );
                        const somePermissions = permissions.some(p =>
                          getPermissionValue(role.role_id, p.permission_id)
                        );

                        return (
                          <td key={role.role_id} className="px-4 py-3 text-center">
                            <div className="flex justify-center">
                              {allPermissions ? (
                                <Check className="h-5 w-5 text-green-600" />
                              ) : somePermissions ? (
                                <Minus className="h-5 w-5 text-yellow-600" />
                              ) : (
                                <X className="h-5 w-5 text-gray-300" />
                              )}
                            </div>
                          </td>
                        );
                      })}
                    </tr>

                    {/* Individual Permission Rows */}
                    {isExpanded && permissions.map((permission) => (
                      <tr key={permission.permission_id} className="hover:bg-gray-50">
                        <td className="sticky left-0 z-10 bg-white px-6 py-3">
                          <div className="ml-8">
                            <p className="text-sm text-gray-900">{permission.action}</p>
                            {permission.description && (
                              <p className="text-xs text-gray-500">{permission.description}</p>
                            )}
                          </div>
                        </td>
                        {matrixData.roles.map((role) => {
                          const hasPermission = getPermissionValue(role.role_id, permission.permission_id);
                          const isChanged = pendingChanges[role.role_id]?.hasOwnProperty(permission.permission_id);

                          return (
                            <td key={role.role_id} className="px-4 py-3 text-center">
                              <button
                                onClick={() => togglePermission(role.role_id, permission.permission_id)}
                                disabled={role.is_system}
                                className={`p-1 rounded ${
                                  role.is_system ? 'cursor-not-allowed' : 'hover:bg-gray-100'
                                } ${isChanged ? 'ring-2 ring-yellow-400' : ''}`}
                              >
                                {hasPermission ? (
                                  <Check className={`h-5 w-5 ${
                                    isChanged ? 'text-yellow-600' : 'text-green-600'
                                  }`} />
                                ) : (
                                  <X className={`h-5 w-5 ${
                                    isChanged ? 'text-yellow-400' : 'text-gray-300'
                                  }`} />
                                )}
                              </button>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Legend */}
      <div className="mt-6 flex items-center gap-6 text-sm text-gray-600">
        <div className="flex items-center gap-2">
          <Check className="h-5 w-5 text-green-600" />
          <span>Granted</span>
        </div>
        <div className="flex items-center gap-2">
          <X className="h-5 w-5 text-gray-300" />
          <span>Not Granted</span>
        </div>
        <div className="flex items-center gap-2">
          <Minus className="h-5 w-5 text-yellow-600" />
          <span>Partial (Resource Level)</span>
        </div>
        <div className="flex items-center gap-2">
          <Shield className="h-3 w-3 text-gray-400" />
          <span>System Role (Read-only)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 ring-2 ring-yellow-400 rounded"></div>
          <span>Pending Change</span>
        </div>
      </div>
    </div>
  );
};
