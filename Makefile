# ═══════════════════════════════════════════════════════════════
#  ElasticGuard — Makefile
#  Shortcuts for common development and deployment tasks.
#
#  Usage:  make <target>
#          make help        (list all targets)
# ═══════════════════════════════════════════════════════════════

NAMESPACE       ?= monitoring
RELEASE         ?= elasticguard
HELM_CHART      := ./helm/elasticguard
REGISTRY        ?= ghcr.io/your-org
VERSION         ?= 1.0.0
BACKEND_IMAGE   := $(REGISTRY)/elasticguard-backend:$(VERSION)
FRONTEND_IMAGE  := $(REGISTRY)/elasticguard-frontend:$(VERSION)

.DEFAULT_GOAL := help

# ── Help ──────────────────────────────────────────────────────
.PHONY: help
help: ## Show this help
	@echo ""
	@echo "  ElasticGuard — Available Targets"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-28s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ── Local Development ─────────────────────────────────────────
.PHONY: dev
dev: ## Start local dev server (backend + frontend)
	./start.sh local

.PHONY: dev-docker
dev-docker: ## Start with Docker Compose (all services)
	docker-compose up

.PHONY: stop
stop: ## Stop all running services
	./start.sh stop
	docker-compose down 2>/dev/null || true

# ── Linting & Type-checking ───────────────────────────────────
.PHONY: lint
lint: lint-backend lint-frontend lint-helm ## Run all linters

.PHONY: lint-backend
lint-backend: ## Lint Python backend (ruff)
	cd backend && pip install ruff -q && ruff check . --ignore E501

.PHONY: lint-frontend
lint-frontend: ## Lint Next.js frontend
	cd frontend && npm run lint

.PHONY: typecheck
typecheck: ## TypeScript type check
	cd frontend && npx tsc --noEmit

.PHONY: lint-helm
lint-helm: ## Lint Helm chart
	helm lint $(HELM_CHART)
	@echo "✓ Helm lint passed"

# ── Docker Images ─────────────────────────────────────────────
.PHONY: build
build: build-backend build-frontend ## Build all Docker images

.PHONY: build-backend
build-backend: ## Build backend Docker image
	docker build -t $(BACKEND_IMAGE) ./backend
	@echo "✓ Built $(BACKEND_IMAGE)"

.PHONY: build-frontend
build-frontend: ## Build frontend Docker image
	docker build -t $(FRONTEND_IMAGE) \
		--build-arg NEXT_PUBLIC_API_URL=http://localhost:8000 \
		--build-arg NEXT_PUBLIC_WS_URL=ws://localhost:8000 \
		./frontend
	@echo "✓ Built $(FRONTEND_IMAGE)"

.PHONY: push
push: ## Push images to registry
	docker push $(BACKEND_IMAGE)
	docker push $(FRONTEND_IMAGE)
	@echo "✓ Pushed images to $(REGISTRY)"

.PHONY: build-push
build-push: build push ## Build and push all images

# ── Helm Chart ────────────────────────────────────────────────
.PHONY: helm-template
helm-template: ## Render Helm templates (dry run, stdout)
	helm template $(RELEASE) $(HELM_CHART) \
		--set backend.image.repository=$(REGISTRY)/elasticguard-backend \
		--set frontend.image.repository=$(REGISTRY)/elasticguard-frontend \
		--debug

.PHONY: helm-template-prod
helm-template-prod: ## Render production Helm templates
	helm template $(RELEASE) $(HELM_CHART) \
		-f helm/values-production.yaml \
		--set backend.image.repository=$(REGISTRY)/elasticguard-backend \
		--set frontend.image.repository=$(REGISTRY)/elasticguard-frontend \
		--set ai.existingSecret=elasticguard-ai-keys \
		--set notifications.existingSecret=elasticguard-notification-keys \
		--set grafana.existingSecret=elasticguard-grafana-admin

.PHONY: helm-install
helm-install: ## Install Helm chart (dev defaults, Ollama AI)
	kubectl create namespace $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	helm upgrade --install $(RELEASE) $(HELM_CHART) \
		--namespace $(NAMESPACE) \
		--set backend.image.repository=$(REGISTRY)/elasticguard-backend \
		--set backend.image.tag=$(VERSION) \
		--set frontend.image.repository=$(REGISTRY)/elasticguard-frontend \
		--set frontend.image.tag=$(VERSION) \
		--set app.secretKey=$$(openssl rand -hex 32) \
		--set app.approvalWebhookSecret=$$(openssl rand -hex 16) \
		--wait --timeout=10m
	@echo ""
	@echo "✓ ElasticGuard installed in namespace $(NAMESPACE)"

.PHONY: helm-install-minimal
helm-install-minimal: ## Install minimal chart (no Grafana/Prometheus)
	kubectl create namespace $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	helm upgrade --install $(RELEASE) $(HELM_CHART) \
		--namespace $(NAMESPACE) \
		-f helm/values-minimal.yaml \
		--set backend.image.repository=$(REGISTRY)/elasticguard-backend \
		--set frontend.image.repository=$(REGISTRY)/elasticguard-frontend \
		--set app.secretKey=$$(openssl rand -hex 32) \
		--wait --timeout=10m

.PHONY: helm-install-prod
helm-install-prod: ## Install production chart (requires existing secrets)
	helm upgrade --install $(RELEASE) $(HELM_CHART) \
		--namespace $(NAMESPACE) \
		-f helm/values-production.yaml \
		--set backend.image.repository=$(REGISTRY)/elasticguard-backend \
		--set backend.image.tag=$(VERSION) \
		--set frontend.image.repository=$(REGISTRY)/elasticguard-frontend \
		--set frontend.image.tag=$(VERSION) \
		--set ai.existingSecret=elasticguard-ai-keys \
		--set notifications.existingSecret=elasticguard-notification-keys \
		--set grafana.existingSecret=elasticguard-grafana-admin \
		--set app.secretKey=$$(openssl rand -hex 32) \
		--set app.approvalWebhookSecret=$$(openssl rand -hex 16) \
		--wait --timeout=15m

.PHONY: helm-upgrade
helm-upgrade: ## Upgrade existing installation
	helm upgrade $(RELEASE) $(HELM_CHART) \
		--namespace $(NAMESPACE) \
		--reuse-values \
		--set backend.image.tag=$(VERSION) \
		--set frontend.image.tag=$(VERSION) \
		--wait --timeout=10m

.PHONY: helm-test
helm-test: ## Run Helm test suite
	helm test $(RELEASE) --namespace $(NAMESPACE) --logs

.PHONY: helm-uninstall
helm-uninstall: ## Uninstall Helm release (keeps PVCs)
	helm uninstall $(RELEASE) --namespace $(NAMESPACE)

.PHONY: helm-purge
helm-purge: ## Uninstall release AND delete all PVCs (DESTRUCTIVE)
	helm uninstall $(RELEASE) --namespace $(NAMESPACE) || true
	kubectl delete pvc -n $(NAMESPACE) -l app.kubernetes.io/instance=$(RELEASE) || true
	@echo "⚠  All data deleted"

.PHONY: helm-package
helm-package: ## Package Helm chart as .tgz
	helm package $(HELM_CHART) -d helm-packages/
	@echo "✓ Packaged: $$(ls helm-packages/elasticguard-*.tgz | tail -1)"

# ── Kubernetes Utilities ──────────────────────────────────────
.PHONY: status
status: ## Show pod status in namespace
	kubectl get pods,svc,pvc,ingress -n $(NAMESPACE) -l app.kubernetes.io/instance=$(RELEASE)

.PHONY: logs-backend
logs-backend: ## Tail backend logs
	kubectl logs -n $(NAMESPACE) -l app.kubernetes.io/component=backend -f --tail=100

.PHONY: logs-frontend
logs-frontend: ## Tail frontend logs
	kubectl logs -n $(NAMESPACE) -l app.kubernetes.io/component=frontend -f --tail=100

.PHONY: logs-ollama
logs-ollama: ## Tail Ollama logs
	kubectl logs -n $(NAMESPACE) -l app.kubernetes.io/component=ollama -f --tail=50

.PHONY: port-forward
port-forward: ## Port-forward all services locally
	@echo "Port-forwarding all services..."
	@echo "  Frontend → http://localhost:3000"
	@echo "  Backend  → http://localhost:8000"
	@echo "  Grafana  → http://localhost:3001"
	@echo "  Prometheus → http://localhost:9090"
	@kubectl port-forward -n $(NAMESPACE) svc/$(RELEASE)-frontend 3000:3000 &
	@kubectl port-forward -n $(NAMESPACE) svc/$(RELEASE)-backend 8000:8000 &
	@kubectl port-forward -n $(NAMESPACE) svc/$(RELEASE)-grafana 3001:3000 2>/dev/null &
	@kubectl port-forward -n $(NAMESPACE) svc/$(RELEASE)-prometheus 9090:9090 2>/dev/null &
	@echo "Press Ctrl+C to stop all port-forwards"
	@wait

.PHONY: secrets
secrets: ## Run interactive secrets helper
	./helm/secrets-helper.sh --namespace $(NAMESPACE)

# ── Git & Release ─────────────────────────────────────────────
.PHONY: release
release: ## Tag and push a new release (prompts for version)
	@echo -n "Release version (e.g. 1.0.1): "; read V; \
	git tag -a "v$$V" -m "Release v$$V" && \
	git push origin "v$$V" && \
	echo "✓ Tagged and pushed v$$V"
