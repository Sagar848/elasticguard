{{/*
ElasticGuard Helm Chart — Template Helpers
*/}}

{{/*
Expand the name of the chart.
*/}}
{{- define "elasticguard.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
Truncated at 63 chars because Kubernetes name fields have a limit.
*/}}
{{- define "elasticguard.fullname" -}}
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
Create chart label.
*/}}
{{- define "elasticguard.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels — applied to every resource.
*/}}
{{- define "elasticguard.labels" -}}
helm.sh/chart: {{ include "elasticguard.chart" . }}
app.kubernetes.io/name: {{ include "elasticguard.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.global.labels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Selector labels — used in Deployments and Services.
*/}}
{{- define "elasticguard.selectorLabels" -}}
app.kubernetes.io/name: {{ include "elasticguard.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Component-specific selector labels.
*/}}
{{- define "elasticguard.componentLabels" -}}
{{- $component := index . 0 -}}
{{- $ctx := index . 1 -}}
app.kubernetes.io/name: {{ include "elasticguard.name" $ctx }}
app.kubernetes.io/instance: {{ $ctx.Release.Name }}
app.kubernetes.io/component: {{ $component }}
{{- end }}

{{/*
ServiceAccount name.
*/}}
{{- define "elasticguard.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "elasticguard.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Backend full name.
*/}}
{{- define "elasticguard.backend.fullname" -}}
{{- printf "%s-backend" (include "elasticguard.fullname" .) }}
{{- end }}

{{/*
Frontend full name.
*/}}
{{- define "elasticguard.frontend.fullname" -}}
{{- printf "%s-frontend" (include "elasticguard.fullname" .) }}
{{- end }}

{{/*
Ollama full name.
*/}}
{{- define "elasticguard.ollama.fullname" -}}
{{- printf "%s-ollama" (include "elasticguard.fullname" .) }}
{{- end }}

{{/*
Prometheus full name.
*/}}
{{- define "elasticguard.prometheus.fullname" -}}
{{- printf "%s-prometheus" (include "elasticguard.fullname" .) }}
{{- end }}

{{/*
Grafana full name.
*/}}
{{- define "elasticguard.grafana.fullname" -}}
{{- printf "%s-grafana" (include "elasticguard.fullname" .) }}
{{- end }}

{{/*
Ollama base URL — auto-detect whether in-cluster or external.
*/}}
{{- define "elasticguard.ollama.url" -}}
{{- if .Values.ollama.enabled -}}
http://{{ include "elasticguard.ollama.fullname" . }}:{{ .Values.ollama.service.port }}
{{- else -}}
{{ .Values.ai.ollama.baseUrl }}
{{- end }}
{{- end }}

{{/*
Backend API URL — used by frontend.
*/}}
{{- define "elasticguard.backend.url" -}}
{{- printf "http://%s:%d" (include "elasticguard.backend.fullname" .) (.Values.backend.service.port | int) }}
{{- end }}

{{/*
Image pull secrets.
*/}}
{{- define "elasticguard.imagePullSecrets" -}}
{{- with .Values.global.imagePullSecrets }}
imagePullSecrets:
{{- range . }}
  - name: {{ . }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Resolve storage class — component-level overrides global.
Usage: {{ include "elasticguard.storageClass" (dict "sc" .Values.backend.persistence.storageClass "global" .Values.global.storageClass) }}
*/}}
{{- define "elasticguard.storageClass" -}}
{{- if .sc -}}
storageClassName: {{ .sc }}
{{- else if .global -}}
storageClassName: {{ .global }}
{{- else -}}
storageClassName: ""
{{- end }}
{{- end }}
