import React, { useState, useEffect } from 'react';
import { Shield, AlertTriangle, Lock, Key, Activity, TrendingUp, Users, FileText } from 'lucide-react';
import { useWorkflowApi } from '../../hooks/useWorkflowApi';
import { Card } from '../layout/Card';
import { Grid } from '../layout/Grid';

interface SecurityMetrics {
  total_users: number;
  active_sessions: number;
  failed_login_attempts: number;
  security_incidents: number;
  permission_violations: number;
  data_access_anomalies: number;
  compliance_score: number;
  last_security_scan: string;
}

interface SecurityEvent {
  event_id: string;
  type: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  description: string;
  timestamp: string;
  user_id?: string;
  ip_address?: string;
  resolved: boolean;
}

export const SecurityDashboard: React.FC = () => {
  const { executeWorkflow } = useWorkflowApi();
  const [metrics, setMetrics] = useState<SecurityMetrics | null>(null);
  const [recentEvents, setRecentEvents] = useState<SecurityEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState(30000); // 30 seconds

  // Fetch security metrics
  const fetchMetrics = async () => {
    try {
      const result = await executeWorkflow('admin_security_metrics', {
        include_trends: true
      });
      setMetrics(result.metrics);
    } catch (error) {
      console.error('Failed to fetch security metrics:', error);
    }
  };

  // Fetch recent security events
  const fetchRecentEvents = async () => {
    try {
      const result = await executeWorkflow('admin_recent_security_events', {
        limit: 10,
        unresolved_only: false
      });
      setRecentEvents(result.events || []);
    } catch (error) {
      console.error('Failed to fetch security events:', error);
    }
  };

  // Initial load and refresh
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([fetchMetrics(), fetchRecentEvents()]);
      setLoading(false);
    };

    loadData();

    // Set up refresh interval
    const interval = setInterval(loadData, refreshInterval);
    return () => clearInterval(interval);
  }, [refreshInterval]);

  const severityColors = {
    low: 'text-green-600 bg-green-100',
    medium: 'text-yellow-600 bg-yellow-100',
    high: 'text-orange-600 bg-orange-100',
    critical: 'text-red-600 bg-red-100'
  };

  const MetricCard: React.FC<{
    title: string;
    value: number | string;
    icon: React.ReactNode;
    trend?: 'up' | 'down' | 'stable';
    alert?: boolean;
  }> = ({ title, value, icon, trend, alert }) => (
    <Card variant="bordered" padding="md" className={alert ? 'border-red-500' : ''}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-600">{title}</p>
          <p className={`text-2xl font-bold ${alert ? 'text-red-600' : 'text-gray-900'}`}>
            {value}
          </p>
          {trend && (
            <div className={`text-sm mt-1 ${
              trend === 'up' ? 'text-red-600' :
              trend === 'down' ? 'text-green-600' :
              'text-gray-600'
            }`}>
              {trend === 'up' ? '↑' : trend === 'down' ? '↓' : '→'} vs last period
            </div>
          )}
        </div>
        <div className={`p-3 rounded-lg ${alert ? 'bg-red-100' : 'bg-gray-100'}`}>
          {icon}
        </div>
      </div>
    </Card>
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Security Dashboard</h1>
        <p className="text-gray-600">Monitor security metrics and incidents</p>
      </div>

      {/* Refresh Controls */}
      <div className="mb-6 flex justify-end">
        <select
          value={refreshInterval}
          onChange={(e) => setRefreshInterval(Number(e.target.value))}
          className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
        >
          <option value={10000}>Refresh every 10s</option>
          <option value={30000}>Refresh every 30s</option>
          <option value={60000}>Refresh every 1m</option>
          <option value={300000}>Refresh every 5m</option>
        </select>
      </div>

      {/* Metrics Grid */}
      {metrics && (
        <Grid cols={4} gap="md" className="mb-8">
          <MetricCard
            title="Active Users"
            value={metrics.total_users}
            icon={<Users className="h-6 w-6 text-gray-600" />}
          />
          <MetricCard
            title="Active Sessions"
            value={metrics.active_sessions}
            icon={<Activity className="h-6 w-6 text-blue-600" />}
          />
          <MetricCard
            title="Failed Logins (24h)"
            value={metrics.failed_login_attempts}
            icon={<Lock className="h-6 w-6 text-orange-600" />}
            trend={metrics.failed_login_attempts > 10 ? 'up' : 'stable'}
            alert={metrics.failed_login_attempts > 50}
          />
          <MetricCard
            title="Security Incidents"
            value={metrics.security_incidents}
            icon={<AlertTriangle className="h-6 w-6 text-red-600" />}
            alert={metrics.security_incidents > 0}
          />
          <MetricCard
            title="Permission Violations"
            value={metrics.permission_violations}
            icon={<Key className="h-6 w-6 text-purple-600" />}
            trend={metrics.permission_violations > 5 ? 'up' : 'down'}
          />
          <MetricCard
            title="Data Anomalies"
            value={metrics.data_access_anomalies}
            icon={<FileText className="h-6 w-6 text-indigo-600" />}
          />
          <MetricCard
            title="Compliance Score"
            value={`${metrics.compliance_score}%`}
            icon={<Shield className="h-6 w-6 text-green-600" />}
            trend={metrics.compliance_score >= 90 ? 'stable' : 'down'}
          />
          <MetricCard
            title="Last Security Scan"
            value={new Date(metrics.last_security_scan).toLocaleString()}
            icon={<TrendingUp className="h-6 w-6 text-gray-600" />}
          />
        </Grid>
      )}

      {/* Recent Security Events */}
      <Card variant="elevated" padding="none">
        <Card.Header className="px-6 py-4">
          <h2 className="text-lg font-medium text-gray-900">Recent Security Events</h2>
        </Card.Header>
        <Card.Body className="p-0">
          <div className="divide-y divide-gray-200">
            {recentEvents.length === 0 ? (
              <div className="px-6 py-8 text-center text-gray-500">
                No recent security events
              </div>
            ) : (
              recentEvents.map((event) => (
                <div key={event.event_id} className="px-6 py-4 hover:bg-gray-50">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                          severityColors[event.severity]
                        }`}>
                          {event.severity}
                        </span>
                        <span className="text-sm font-medium text-gray-900">
                          {event.type}
                        </span>
                        {event.resolved && (
                          <span className="text-xs text-green-600">Resolved</span>
                        )}
                      </div>
                      <p className="mt-1 text-sm text-gray-600">{event.description}</p>
                      <div className="mt-1 flex items-center gap-4 text-xs text-gray-500">
                        <span>{new Date(event.timestamp).toLocaleString()}</span>
                        {event.user_id && <span>User: {event.user_id}</span>}
                        {event.ip_address && <span>IP: {event.ip_address}</span>}
                      </div>
                    </div>
                    {!event.resolved && (
                      <button
                        onClick={() => {
                          // Handle event resolution
                          executeWorkflow('admin_resolve_security_event', {
                            event_id: event.event_id
                          });
                        }}
                        className="ml-4 px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
                      >
                        Resolve
                      </button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </Card.Body>
      </Card>
    </div>
  );
};
