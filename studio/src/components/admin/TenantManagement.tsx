import React, { useState, useEffect, useCallback } from 'react';
import { Building2, Plus, Edit2, Trash2, Database, Users, Settings, Activity } from 'lucide-react';
import { useWorkflowApi } from '../../hooks/useWorkflowApi';
import { Card } from '../layout/Card';

interface Tenant {
  tenant_id: string;
  name: string;
  subdomain: string;
  status: 'active' | 'suspended' | 'trial' | 'expired';
  plan: 'free' | 'starter' | 'professional' | 'enterprise';
  created_at: string;
  expires_at?: string;
  settings: {
    max_users?: number;
    max_workflows?: number;
    max_storage_gb?: number;
    features: string[];
  };
  usage: {
    users: number;
    workflows: number;
    storage_gb: number;
    api_calls_monthly: number;
  };
}

export const TenantManagement: React.FC = () => {
  const { executeWorkflow } = useWorkflowApi();
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [selectedTenant, setSelectedTenant] = useState<Tenant | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterStatus, setFilterStatus] = useState<string>('all');

  // Fetch tenants
  const fetchTenants = useCallback(async () => {
    setLoading(true);
    try {
      const result = await executeWorkflow('admin_list_tenants', {
        search_query: searchQuery,
        status_filter: filterStatus !== 'all' ? filterStatus : undefined
      });
      setTenants(result.tenants || []);
    } catch (error) {
      console.error('Failed to fetch tenants:', error);
    } finally {
      setLoading(false);
    }
  }, [executeWorkflow, searchQuery, filterStatus]);

  useEffect(() => {
    fetchTenants();
  }, [fetchTenants]);

  // Create tenant
  const handleCreateTenant = async (tenantData: Partial<Tenant>) => {
    try {
      await executeWorkflow('admin_create_tenant', {
        tenant_data: tenantData
      });
      setShowCreateModal(false);
      fetchTenants();
    } catch (error) {
      console.error('Failed to create tenant:', error);
    }
  };

  // Update tenant
  const handleUpdateTenant = async (tenantId: string, updates: Partial<Tenant>) => {
    try {
      await executeWorkflow('admin_update_tenant', {
        tenant_id: tenantId,
        updates
      });
      fetchTenants();
    } catch (error) {
      console.error('Failed to update tenant:', error);
    }
  };

  // Delete tenant
  const handleDeleteTenant = async (tenantId: string) => {
    if (!confirm('Are you sure you want to delete this tenant? This action cannot be undone.')) return;

    try {
      await executeWorkflow('admin_delete_tenant', {
        tenant_id: tenantId
      });
      fetchTenants();
    } catch (error) {
      console.error('Failed to delete tenant:', error);
    }
  };

  // Suspend/Activate tenant
  const toggleTenantStatus = async (tenant: Tenant) => {
    const newStatus = tenant.status === 'active' ? 'suspended' : 'active';
    await handleUpdateTenant(tenant.tenant_id, { status: newStatus });
  };

  const statusColors = {
    active: 'bg-green-100 text-green-800',
    suspended: 'bg-red-100 text-red-800',
    trial: 'bg-yellow-100 text-yellow-800',
    expired: 'bg-gray-100 text-gray-800'
  };

  const planColors = {
    free: 'bg-gray-100 text-gray-800',
    starter: 'bg-blue-100 text-blue-800',
    professional: 'bg-purple-100 text-purple-800',
    enterprise: 'bg-indigo-100 text-indigo-800'
  };

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Tenant Management</h1>
        <p className="text-gray-600">Manage multi-tenant deployments</p>
      </div>

      {/* Filters */}
      <div className="mb-6 flex flex-col sm:flex-row gap-4">
        <div className="flex-1">
          <input
            type="text"
            placeholder="Search tenants..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
        >
          <option value="all">All Status</option>
          <option value="active">Active</option>
          <option value="suspended">Suspended</option>
          <option value="trial">Trial</option>
          <option value="expired">Expired</option>
        </select>

        <button
          onClick={() => setShowCreateModal(true)}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2"
        >
          <Plus className="h-5 w-5" />
          Create Tenant
        </button>
      </div>

      {/* Tenants Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {loading ? (
          <div className="col-span-full flex justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        ) : tenants.length === 0 ? (
          <div className="col-span-full text-center text-gray-500 py-12">
            No tenants found
          </div>
        ) : (
          tenants.map((tenant) => (
            <Card key={tenant.tenant_id} variant="bordered" padding="md">
              <div className="flex justify-between items-start mb-4">
                <div>
                  <h3 className="text-lg font-medium text-gray-900">{tenant.name}</h3>
                  <p className="text-sm text-gray-500">{tenant.subdomain}.kailash.io</p>
                </div>
                <Building2 className="h-5 w-5 text-gray-400" />
              </div>

              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    statusColors[tenant.status]
                  }`}>
                    {tenant.status}
                  </span>
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    planColors[tenant.plan]
                  }`}>
                    {tenant.plan}
                  </span>
                </div>

                {/* Usage Metrics */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-gray-500 flex items-center gap-1">
                      <Users className="h-4 w-4" />
                      Users
                    </span>
                    <span className="font-medium">
                      {tenant.usage.users}
                      {tenant.settings.max_users && ` / ${tenant.settings.max_users}`}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-gray-500 flex items-center gap-1">
                      <Activity className="h-4 w-4" />
                      Workflows
                    </span>
                    <span className="font-medium">
                      {tenant.usage.workflows}
                      {tenant.settings.max_workflows && ` / ${tenant.settings.max_workflows}`}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-gray-500 flex items-center gap-1">
                      <Database className="h-4 w-4" />
                      Storage
                    </span>
                    <span className="font-medium">
                      {tenant.usage.storage_gb.toFixed(1)} GB
                      {tenant.settings.max_storage_gb && ` / ${tenant.settings.max_storage_gb} GB`}
                    </span>
                  </div>
                </div>

                {/* Expiry Warning */}
                {tenant.expires_at && (
                  <div className="text-xs text-orange-600">
                    Expires: {new Date(tenant.expires_at).toLocaleDateString()}
                  </div>
                )}

                {/* Actions */}
                <div className="flex justify-end gap-2 pt-3 border-t">
                  <button
                    onClick={() => toggleTenantStatus(tenant)}
                    className="p-2 text-gray-600 hover:text-gray-900"
                    title={tenant.status === 'active' ? 'Suspend' : 'Activate'}
                  >
                    <Settings className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => setSelectedTenant(tenant)}
                    className="p-2 text-blue-600 hover:text-blue-900"
                  >
                    <Edit2 className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => handleDeleteTenant(tenant.tenant_id)}
                    className="p-2 text-red-600 hover:text-red-900"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </Card>
          ))
        )}
      </div>

      {/* Create/Edit Modal */}
      {(showCreateModal || selectedTenant) && (
        <TenantFormModal
          tenant={selectedTenant}
          onClose={() => {
            setShowCreateModal(false);
            setSelectedTenant(null);
          }}
          onSubmit={selectedTenant ?
            (data) => handleUpdateTenant(selectedTenant.tenant_id, data) :
            handleCreateTenant
          }
        />
      )}
    </div>
  );
};

// Tenant Form Modal
interface TenantFormModalProps {
  tenant?: Tenant | null;
  onClose: () => void;
  onSubmit: (data: Partial<Tenant>) => Promise<void>;
}

const TenantFormModal: React.FC<TenantFormModalProps> = ({ tenant, onClose, onSubmit }) => {
  const [formData, setFormData] = useState({
    name: tenant?.name || '',
    subdomain: tenant?.subdomain || '',
    plan: tenant?.plan || 'free',
    status: tenant?.status || 'trial',
    settings: {
      max_users: tenant?.settings.max_users || 10,
      max_workflows: tenant?.settings.max_workflows || 50,
      max_storage_gb: tenant?.settings.max_storage_gb || 10,
      features: tenant?.settings.features || []
    }
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await onSubmit(formData);
    onClose();
  };

  const availableFeatures = [
    'api_access',
    'custom_nodes',
    'mcp_integration',
    'advanced_analytics',
    'priority_support',
    'white_label',
    'sso_integration',
    'audit_logs'
  ];

  return (
    <div className="fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full p-6 max-h-[90vh] overflow-y-auto">
        <h2 className="text-xl font-bold mb-4">
          {tenant ? 'Edit Tenant' : 'Create New Tenant'}
        </h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Tenant Name
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
                Subdomain
              </label>
              <div className="flex">
                <input
                  type="text"
                  value={formData.subdomain}
                  onChange={(e) => setFormData({ ...formData, subdomain: e.target.value })}
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-l-lg focus:ring-2 focus:ring-blue-500"
                  required
                  pattern="[a-z0-9-]+"
                />
                <span className="px-3 py-2 bg-gray-100 border border-l-0 border-gray-300 rounded-r-lg text-gray-500">
                  .kailash.io
                </span>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Plan
              </label>
              <select
                value={formData.plan}
                onChange={(e) => setFormData({ ...formData, plan: e.target.value as any })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                <option value="free">Free</option>
                <option value="starter">Starter</option>
                <option value="professional">Professional</option>
                <option value="enterprise">Enterprise</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Status
              </label>
              <select
                value={formData.status}
                onChange={(e) => setFormData({ ...formData, status: e.target.value as any })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                <option value="trial">Trial</option>
                <option value="active">Active</option>
                <option value="suspended">Suspended</option>
                <option value="expired">Expired</option>
              </select>
            </div>
          </div>

          <div>
            <h3 className="text-sm font-medium text-gray-700 mb-2">Resource Limits</h3>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-xs text-gray-500 mb-1">Max Users</label>
                <input
                  type="number"
                  value={formData.settings.max_users}
                  onChange={(e) => setFormData({
                    ...formData,
                    settings: { ...formData.settings, max_users: parseInt(e.target.value) }
                  })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                  min="1"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Max Workflows</label>
                <input
                  type="number"
                  value={formData.settings.max_workflows}
                  onChange={(e) => setFormData({
                    ...formData,
                    settings: { ...formData.settings, max_workflows: parseInt(e.target.value) }
                  })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                  min="1"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Max Storage (GB)</label>
                <input
                  type="number"
                  value={formData.settings.max_storage_gb}
                  onChange={(e) => setFormData({
                    ...formData,
                    settings: { ...formData.settings, max_storage_gb: parseInt(e.target.value) }
                  })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                  min="1"
                />
              </div>
            </div>
          </div>

          <div>
            <h3 className="text-sm font-medium text-gray-700 mb-2">Features</h3>
            <div className="grid grid-cols-2 gap-2">
              {availableFeatures.map((feature) => (
                <label key={feature} className="flex items-center">
                  <input
                    type="checkbox"
                    checked={formData.settings.features.includes(feature)}
                    onChange={(e) => {
                      const features = e.target.checked
                        ? [...formData.settings.features, feature]
                        : formData.settings.features.filter(f => f !== feature);
                      setFormData({
                        ...formData,
                        settings: { ...formData.settings, features }
                      });
                    }}
                    className="mr-2"
                  />
                  <span className="text-sm text-gray-700">
                    {feature.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                  </span>
                </label>
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
              {tenant ? 'Update' : 'Create'} Tenant
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
