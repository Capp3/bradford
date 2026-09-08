SHELL := /bin/bash
.ONESHELL:
.SHELLFLAGS := -euo pipefail -c

.DEFAULT_GOAL := help

ANSIBLE_DIR := ansible
UV := uv run
HOST ?= all
PLAYBOOK := provision-system.yml
VAULT := vault/secrets.yml

.PHONY: help build up down pull clean \
	install validate syntax lint inventory list-tasks ping provision github-pubkey \
	vault-edit vault-view vault-encrypt vault-decrypt

help: ## Show this help
	@echo "Bradford — common targets:"
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

# --- Compose ---

build: ## Build compose images
	docker compose build

up: ## Start the stack
	docker compose up -d

down: ## Stop the stack
	docker compose down

pull: ## Pull compose images
	docker compose pull

clean: ## Recreate the stack (volumes, rebuild, prune)
	docker compose down -v
	docker compose rm -f
	docker compose build
	docker compose up -d
	docker system prune -f

# --- Ansible ---

install: ## Install Python deps and Galaxy roles/collections
	uv sync
	cd $(ANSIBLE_DIR) && $(UV) ansible-galaxy install -r requirements.yml

validate: syntax lint inventory ## Run static Ansible checks

syntax: ## Check playbook YAML and Ansible syntax
	cd $(ANSIBLE_DIR) && $(UV) ansible-playbook $(PLAYBOOK) --syntax-check

lint: ## Lint playbooks and tasks
	cd $(ANSIBLE_DIR) && $(UV) ansible-lint

inventory: ## Show resolved inventory
	cd $(ANSIBLE_DIR) && $(UV) ansible-inventory --graph

list-tasks: ## List tasks that would run
	cd $(ANSIBLE_DIR) && $(UV) ansible-playbook $(PLAYBOOK) --list-tasks

ping: ## Ping hosts (HOST=all)
	cd $(ANSIBLE_DIR) && $(UV) ansible $(HOST) -m ping

provision: ## Run the kilolink playbook
	cd $(ANSIBLE_DIR) && $(UV) ansible-playbook -vv $(PLAYBOOK)

github-pubkey: ## Print GitHub SSH public keys from linux hosts
	cd $(ANSIBLE_DIR) && $(UV) ansible linux -m command -a 'cat ~/.ssh/id_ed25519_github.pub'
	cd $(ANSIBLE_DIR) && $(UV) ansible linux -b -m command -a 'cat /root/.ssh/id_ed25519_github.pub'

# --- Vault ---

vault-edit: ## Edit encrypted vault secrets
	cd $(ANSIBLE_DIR) && $(UV) ansible-vault edit $(VAULT)

vault-view: ## View encrypted vault secrets
	cd $(ANSIBLE_DIR) && $(UV) ansible-vault view $(VAULT)

vault-encrypt: ## Encrypt vault secrets
	cd $(ANSIBLE_DIR) && $(UV) ansible-vault encrypt $(VAULT)

vault-decrypt: ## Decrypt vault secrets
	cd $(ANSIBLE_DIR) && $(UV) ansible-vault decrypt $(VAULT)
