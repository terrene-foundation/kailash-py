{{/*
Expand the name of the chart.
*/}}
{{- define "kailash-user-management.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "kailash-user-management.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "kailash-user-management.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "kailash-user-management.labels" -}}
helm.sh/chart: {{ include "kailash-user-management.chart" . }}
{{ include "kailash-user-management.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: kailash-ecosystem
{{- end }}

{{/*
Selector labels
*/}}
{{- define "kailash-user-management.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kailash-user-management.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "kailash-user-management.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "kailash-user-management.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
PostgreSQL fullname
*/}}
{{- define "kailash-user-management.postgresql.fullname" -}}
{{- if .Values.postgresql.enabled }}
{{- include "postgresql.primary.fullname" .Subcharts.postgresql }}
{{- else }}
{{- .Values.externalDatabase.host }}
{{- end }}
{{- end }}

{{/*
Redis fullname
*/}}
{{- define "kailash-user-management.redis.fullname" -}}
{{- if .Values.redis.enabled }}
{{- include "redis.fullname" .Subcharts.redis }}
{{- else }}
{{- .Values.externalRedis.host }}
{{- end }}
{{- end }}

{{/*
Create a default fully qualified postgresql name.
*/}}
{{- define "kailash-user-management.postgresql.secretName" -}}
{{- if .Values.postgresql.enabled }}
{{- include "postgresql.secretName" .Subcharts.postgresql }}
{{- else }}
{{- include "kailash-user-management.fullname" . }}-external-db
{{- end }}
{{- end }}

{{/*
Create a default fully qualified redis name.
*/}}
{{- define "kailash-user-management.redis.secretName" -}}
{{- if .Values.redis.enabled }}
{{- include "redis.secretName" .Subcharts.redis }}
{{- else }}
{{- include "kailash-user-management.fullname" . }}-external-redis
{{- end }}
{{- end }}

{{/*
Generate certificate secret name
*/}}
{{- define "kailash-user-management.certificateSecretName" -}}
{{- if .Values.ingress.tls }}
{{- (index .Values.ingress.tls 0).secretName }}
{{- else }}
{{- include "kailash-user-management.fullname" . }}-tls
{{- end }}
{{- end }}

{{/*
Environment-specific configuration override
*/}}
{{- define "kailash-user-management.environmentConfig" -}}
{{- $environment := .Values.app.environment }}
{{- if hasKey .Values.environments $environment }}
{{- $envConfig := index .Values.environments $environment }}
{{- toYaml $envConfig }}
{{- end }}
{{- end }}

{{/*
Generate backup storage name
*/}}
{{- define "kailash-user-management.backupStorageName" -}}
{{- if .Values.persistence.backupStorage.enabled }}
{{- include "kailash-user-management.fullname" . }}-backup
{{- end }}
{{- end }}

{{/*
Generate log storage name
*/}}
{{- define "kailash-user-management.logStorageName" -}}
{{- if .Values.persistence.logStorage.enabled }}
{{- include "kailash-user-management.fullname" . }}-logs
{{- end }}
{{- end }}

{{/*
Create the database connection URL
*/}}
{{- define "kailash-user-management.databaseUrl" -}}
{{- if .Values.postgresql.enabled }}
postgresql://{{ .Values.postgresql.auth.username }}:{{ .Values.postgresql.auth.password }}@{{ include "kailash-user-management.postgresql.fullname" . }}:5432/{{ .Values.postgresql.auth.database }}
{{- else }}
postgresql://{{ .Values.externalDatabase.username }}:{{ .Values.externalDatabase.password }}@{{ .Values.externalDatabase.host }}:{{ .Values.externalDatabase.port }}/{{ .Values.externalDatabase.database }}
{{- end }}
{{- end }}

{{/*
Create the Redis connection URL
*/}}
{{- define "kailash-user-management.redisUrl" -}}
{{- if .Values.redis.enabled }}
redis://:{{ .Values.redis.auth.password }}@{{ include "kailash-user-management.redis.fullname" . }}-master:6379/0
{{- else }}
redis://:{{ .Values.externalRedis.password }}@{{ .Values.externalRedis.host }}:{{ .Values.externalRedis.port }}/{{ .Values.externalRedis.database }}
{{- end }}
{{- end }}

{{/*
Validate required values
*/}}
{{- define "kailash-user-management.validateValues" -}}
{{- if not .Values.postgresql.enabled }}
  {{- if not .Values.externalDatabase.host }}
    {{- fail "External database host is required when PostgreSQL is disabled" }}
  {{- end }}
{{- end }}
{{- if not .Values.redis.enabled }}
  {{- if not .Values.externalRedis.host }}
    {{- fail "External Redis host is required when Redis is disabled" }}
  {{- end }}
{{- end }}
{{- end }}

{{/*
Generate environment-specific resource limits
*/}}
{{- define "kailash-user-management.resources" -}}
{{- $environment := .Values.app.environment }}
{{- $resources := .Values.resources.app }}
{{- if hasKey .Values.environments $environment }}
{{- $envConfig := index .Values.environments $environment }}
{{- if hasKey $envConfig "resources" }}
{{- $resources = $envConfig.resources.app }}
{{- end }}
{{- end }}
{{- toYaml $resources }}
{{- end }}

{{/*
Generate environment-specific replica count
*/}}
{{- define "kailash-user-management.replicaCount" -}}
{{- $environment := .Values.app.environment }}
{{- $replicaCount := .Values.app.replicaCount }}
{{- if hasKey .Values.environments $environment }}
{{- $envConfig := index .Values.environments $environment }}
{{- if hasKey $envConfig "replicaCount" }}
{{- $replicaCount = $envConfig.replicaCount }}
{{- end }}
{{- end }}
{{- $replicaCount }}
{{- end }}