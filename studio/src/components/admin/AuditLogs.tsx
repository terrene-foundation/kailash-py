import React, { useState, useEffect, useCallback } from 'react';
import { FileText, Download, Filter, Calendar, AlertCircle, CheckCircle, XCircle } from 'lucide-react';
import { useWorkflowApi } from '../../hooks/useWorkflowApi';

interface AuditLog {
  audit_id: string;
  event_type: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  action: string;
  user_id: string;
  user_email?: string;
  resource_type?: string;
  resource_id?: string;
  description: string;
  metadata: Record<string, any>;
  ip_address?: string;
  user_agent?: string;
  status: 'success' | 'failure' | 'warning';
  created_at: string;
  compliance_tags?: string[];
}

export const AuditLogs: React.FC = () => {
  const { executeWorkflow } = useWorkflowApi();
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({
    event_type: '',
    severity: '',
    date_from: '',
    date_to: '',
    user_id: '',
    status: ''
  });
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null);

  // Fetch audit logs
  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const result = await executeWorkflow('admin_query_audit_logs', {
        filters: {
          ...filters,
          date_range: filters.date_from && filters.date_to ? {
            start: filters.date_from,
            end: filters.date_to
          } : undefined
        },
        pagination: { page: currentPage, size: 50 }
      });
      
      setLogs(result.logs || []);
      setTotalPages(result.pagination?.total_pages || 1);
    } catch (error) {
      console.error('Failed to fetch audit logs:', error);
    } finally {
      setLoading(false);
    }
  }, [executeWorkflow, filters, currentPage]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  // Export logs
  const handleExport = async (format: 'csv' | 'json') => {
    try {
      const result = await executeWorkflow('admin_export_audit_logs', {
        filters,
        format,
        include_metadata: true
      });
      
      // Download the exported file
      if (result.download_url) {
        window.open(result.download_url, '_blank');
      }
    } catch (error) {
      console.error('Failed to export audit logs:', error);
    }
  };

  const severityColors = {
    low: 'bg-green-100 text-green-800',
    medium: 'bg-yellow-100 text-yellow-800',
    high: 'bg-orange-100 text-orange-800',
    critical: 'bg-red-100 text-red-800'
  };

  const statusIcons = {
    success: <CheckCircle className="h-4 w-4 text-green-600" />,
    failure: <XCircle className="h-4 w-4 text-red-600" />,
    warning: <AlertCircle className="h-4 w-4 text-yellow-600" />
  };

  const eventTypeColors: Record<string, string> = {
    user_login: 'text-blue-600',
    user_logout: 'text-gray-600',
    user_created: 'text-green-600',
    user_updated: 'text-yellow-600',
    user_deleted: 'text-red-600',
    permission_granted: 'text-purple-600',
    permission_revoked: 'text-orange-600',
    data_accessed: 'text-indigo-600',
    security_alert: 'text-red-700',
    system_error: 'text-red-800'
  };

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Audit Logs</h1>
        <p className="text-gray-600">Monitor system activity and compliance</p>
      </div>

      {/* Filters */}
      <div className="mb-6 bg-white rounded-lg shadow p-4">
        <div className="flex items-center mb-4">
          <Filter className="h-5 w-5 text-gray-400 mr-2" />
          <h2 className="text-lg font-medium">Filters</h2>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <select
            value={filters.event_type}
            onChange={(e) => setFilters({ ...filters, event_type: e.target.value })}
            className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Events</option>
            <option value="user_login">User Login</option>
            <option value="user_created">User Created</option>
            <option value="user_updated">User Updated</option>
            <option value="user_deleted">User Deleted</option>
            <option value="permission_granted">Permission Granted</option>
            <option value="data_accessed">Data Accessed</option>
            <option value="security_alert">Security Alert</option>
          </select>

          <select
            value={filters.severity}
            onChange={(e) => setFilters({ ...filters, severity: e.target.value })}
            className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Severities</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>

          <select
            value={filters.status}
            onChange={(e) => setFilters({ ...filters, status: e.target.value })}
            className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Status</option>
            <option value="success">Success</option>
            <option value="failure">Failure</option>
            <option value="warning">Warning</option>
          </select>

          <input
            type="date"
            value={filters.date_from}
            onChange={(e) => setFilters({ ...filters, date_from: e.target.value })}
            className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            placeholder="From Date"
          />

          <input
            type="date"
            value={filters.date_to}
            onChange={(e) => setFilters({ ...filters, date_to: e.target.value })}
            className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            placeholder="To Date"
          />

          <div className="flex gap-2">
            <button
              onClick={() => handleExport('csv')}
              className="px-3 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 flex items-center gap-1"
              title="Export as CSV"
            >
              <Download className="h-4 w-4" />
              CSV
            </button>
            <button
              onClick={() => handleExport('json')}
              className="px-3 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 flex items-center gap-1"
              title="Export as JSON"
            >
              <Download className="h-4 w-4" />
              JSON
            </button>
          </div>
        </div>
      </div>

      {/* Logs Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Timestamp
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Event
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                User
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Severity
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Description
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Details
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {loading ? (
              <tr>
                <td colSpan={7} className="px-6 py-4 text-center">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
                </td>
              </tr>
            ) : logs.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-6 py-4 text-center text-gray-500">
                  No audit logs found
                </td>
              </tr>
            ) : (
              logs.map((log) => (
                <tr key={log.audit_id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    <div className="flex items-center">
                      <Calendar className="h-4 w-4 mr-1 text-gray-400" />
                      {new Date(log.created_at).toLocaleString()}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`text-sm font-medium ${eventTypeColors[log.event_type] || 'text-gray-900'}`}>
                      {log.event_type.replace(/_/g, ' ').toUpperCase()}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    {log.user_email || log.user_id}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span
                      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                        severityColors[log.severity]
                      }`}
                    >
                      {log.severity}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      {statusIcons[log.status]}
                      <span className="ml-1 text-sm text-gray-600">
                        {log.status}
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-900">
                    <div className="max-w-xs truncate">
                      {log.description}
                    </div>
                    {log.compliance_tags && log.compliance_tags.length > 0 && (
                      <div className="mt-1 flex gap-1">
                        {log.compliance_tags.map((tag) => (
                          <span
                            key={tag}
                            className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button
                      onClick={() => setSelectedLog(log)}
                      className="text-blue-600 hover:text-blue-900"
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-between">
          <button
            onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
            disabled={currentPage === 1}
            className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
          >
            Previous
          </button>
          <span className="text-sm text-gray-700">
            Page {currentPage} of {totalPages}
          </span>
          <button
            onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
            disabled={currentPage === totalPages}
            className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
          >
            Next
          </button>
        </div>
      )}

      {/* Log Details Modal */}
      {selectedLog && (
        <LogDetailsModal
          log={selectedLog}
          onClose={() => setSelectedLog(null)}
        />
      )}
    </div>
  );
};

// Log Details Modal
interface LogDetailsModalProps {
  log: AuditLog;
  onClose: () => void;
}

const LogDetailsModal: React.FC<LogDetailsModalProps> = ({ log, onClose }) => {
  return (
    <div className="fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full p-6 max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-start mb-4">
          <h2 className="text-xl font-bold">Audit Log Details</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
          >
            ×
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="text-sm font-medium text-gray-700">Event ID</label>
            <p className="mt-1 text-sm text-gray-900 font-mono">{log.audit_id}</p>
          </div>

          <div>
            <label className="text-sm font-medium text-gray-700">Timestamp</label>
            <p className="mt-1 text-sm text-gray-900">
              {new Date(log.created_at).toLocaleString()}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-gray-700">Event Type</label>
              <p className="mt-1 text-sm text-gray-900">{log.event_type}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-gray-700">Severity</label>
              <p className="mt-1 text-sm text-gray-900">{log.severity}</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-gray-700">User</label>
              <p className="mt-1 text-sm text-gray-900">{log.user_email || log.user_id}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-gray-700">IP Address</label>
              <p className="mt-1 text-sm text-gray-900">{log.ip_address || 'N/A'}</p>
            </div>
          </div>

          <div>
            <label className="text-sm font-medium text-gray-700">Description</label>
            <p className="mt-1 text-sm text-gray-900">{log.description}</p>
          </div>

          {log.resource_type && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium text-gray-700">Resource Type</label>
                <p className="mt-1 text-sm text-gray-900">{log.resource_type}</p>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700">Resource ID</label>
                <p className="mt-1 text-sm text-gray-900">{log.resource_id || 'N/A'}</p>
              </div>
            </div>
          )}

          {log.compliance_tags && log.compliance_tags.length > 0 && (
            <div>
              <label className="text-sm font-medium text-gray-700">Compliance Tags</label>
              <div className="mt-1 flex flex-wrap gap-1">
                {log.compliance_tags.map((tag) => (
                  <span
                    key={tag}
                    className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-purple-100 text-purple-800"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          )}

          {log.metadata && Object.keys(log.metadata).length > 0 && (
            <div>
              <label className="text-sm font-medium text-gray-700">Additional Metadata</label>
              <pre className="mt-1 p-3 bg-gray-50 rounded text-xs overflow-x-auto">
                {JSON.stringify(log.metadata, null, 2)}
              </pre>
            </div>
          )}

          {log.user_agent && (
            <div>
              <label className="text-sm font-medium text-gray-700">User Agent</label>
              <p className="mt-1 text-sm text-gray-900 font-mono text-xs">{log.user_agent}</p>
            </div>
          )}
        </div>

        <div className="mt-6 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};