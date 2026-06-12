SHELL := /bin/sh
.ONESHELL:
.SHELLFLAGS := -e -u -o pipefail -c

.DEFAULT_GOAL := help


.PHONY: help build up down

help: ## Show this help message
	@echo "Companion-2-OpenAVC — common targets:"
	@fgrep -h "##" $(MAKEFILE_LIST) | grep -v fgrep | sed -e 's/\([^:]*\):[^#]*##\(.*\)/  \1|\2/' | column -t -s '|'

build: ## Build the project
	docker compose build

up: ## Start the project
	docker compose up -d

down: ## Stop the project
	docker compose down

pull: ## Pull the latest images
	docker compose pull

clean: ## Clean the project
	docker compose down -v
	docker compose rm -f
	docker compose build
	docker compose up -d
	docker system prune -f