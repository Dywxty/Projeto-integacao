import sys
from pathlib import Path

from unittest.mock import Mock

import pytest


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import main


DADOS_VALIDOS = {
	"hora": "08:30:00",
	"temperatura": 26.4,
	"umidade": 68,
	"sensacao": 27.1,
	"vento": 5.2,
	"clima": "Agradável",
}


def test_dados_validos():
	valido, erro = main.validar_dados(DADOS_VALIDOS)

	assert valido is True
	assert erro is None


def test_campo_obrigatorio_ausente():
	dados = DADOS_VALIDOS.copy()
	del dados["temperatura"]

	valido, erro = main.validar_dados(dados)

	assert valido is False
	assert "temperatura" in erro


def test_campo_numerico_invalido():
	dados = DADOS_VALIDOS.copy()
	dados["umidade"] = "alta"

	valido, erro = main.validar_dados(dados)

	assert valido is False
	assert "valores numéricos" in erro


@pytest.mark.parametrize(
	("campo", "valor"),
	[("temperatura", 71), ("umidade", 101), ("vento", -1)],
)
def test_valores_fora_do_limite(campo, valor):
	dados = DADOS_VALIDOS.copy()
	dados[campo] = valor

	valido, erro = main.validar_dados(dados)

	assert valido is False
	assert erro


def test_rota_inicial():
	cliente = main.app.test_client()

	resposta = cliente.get("/")

	assert resposta.status_code == 200
	assert resposta.get_json()["status"] == "online"


def test_rota_status():
	cliente = main.app.test_client()

	resposta = cliente.get("/status")
	dados = resposta.get_json()

	assert resposta.status_code == 200
	assert dados["api"] is True
	assert dados["topico"] == main.MQTT_TOPIC


def test_post_dados_validos(monkeypatch):
	salvar_dados = Mock()
	monkeypatch.setattr(main, "salvar_dados", salvar_dados)
	cliente = main.app.test_client()

	resposta = cliente.post("/dados", json=DADOS_VALIDOS)

	assert resposta.status_code == 201
	assert resposta.get_json()["dados"] == DADOS_VALIDOS
	salvar_dados.assert_called_once_with(DADOS_VALIDOS)


def test_post_sem_json():
	cliente = main.app.test_client()

	resposta = cliente.post("/dados", data="temperatura=26")

	assert resposta.status_code == 400
	assert "JSON" in resposta.get_json()["erro"]
