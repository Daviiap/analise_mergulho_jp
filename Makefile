# Planejador de mergulho — João Pessoa
#   make instalar                          cria o ambiente Python e instala o pdfplumber
#   make atualizar PDF=tabua_2027.pdf      grava a tábua DHN no index.html (aceita URL e vários PDFs)
#   make abrir                             abre a página no navegador
#   make limpar                            remove o ambiente Python

PYTHON ?= python3
VENV   := .venv
PY     := $(VENV)/bin/python
PDF    ?=

.DEFAULT_GOAL := ajuda
.PHONY: ajuda instalar atualizar checar-pdf abrir limpar

ajuda:
	@sed -n '2,5s/^# *//p' $(firstword $(MAKEFILE_LIST))

$(PY):
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install --quiet "pdfplumber>=0.11,<1"

instalar: $(PY)
	@echo "Ambiente pronto em $(VENV)."

atualizar: checar-pdf $(PY)
	$(PY) atualizar_mares.py $(PDF)

checar-pdf:
	@test -n "$(PDF)" || { echo "Informe o PDF: make atualizar PDF=TABUA_CABEDELO_2027.pdf"; exit 1; }

abrir:
	@xdg-open index.html 2>/dev/null || open index.html 2>/dev/null || echo "Abra index.html no navegador."

limpar:
	rm -rf $(VENV)
