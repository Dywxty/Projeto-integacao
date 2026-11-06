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


def test_iniciar_mqtt_configura_reconexao(monkeypatch):
	reconnect_delay_set = Mock()
	connect_async = Mock()
	loop_start = Mock()
	monkeypatch.setattr(main.cliente_mqtt, "reconnect_delay_set", reconnect_delay_set)
	monkeypatch.setattr(main.cliente_mqtt, "connect_async", connect_async)
	monkeypatch.setattr(main.cliente_mqtt, "loop_start", loop_start)

	main.iniciar_mqtt()

	reconnect_delay_set.assert_called_once_with(min_delay=2, max_delay=30)
	connect_async.assert_called_once_with(main.MQTT_BROKER, main.MQTT_PORT, 60)
	loop_start.assert_called_once_with()
	assert main.mqtt_erro == "Conectando ao broker MQTT"


def test_falha_de_conexao_mqtt_fica_disponivel_no_status():
	main.ao_falhar_conexao(main.cliente_mqtt, None)

	resposta = main.app.test_client().get("/status")

	assert resposta.get_json()["mqtt_erro"] == (
		"Não foi possível alcançar o broker MQTT; tentando novamente"
	)


def test_publica_clima_no_topico_da_placa(monkeypatch):
	dados_clima = {
		"hora": "14:00:00",
		"temperatura": 25.0,
		"umidade": 60.0,
		"sensacao": 26.0,
		"vento": 5.0,
		"clima": "Ensolarado",
	}
	resultado_publicacao = Mock(rc=main.mqtt.MQTT_ERR_SUCCESS)
	resultado_publicacao.is_published.return_value = True
	monkeypatch.setattr(main, "buscar_clima_open_meteo", Mock(return_value=dados_clima))
	monkeypatch.setattr(main.cliente_mqtt, "is_connected", Mock(return_value=True))
	publicar = Mock(return_value=resultado_publicacao)
	monkeypatch.setattr(main.cliente_mqtt, "publish", publicar)

	resposta = main.app.test_client().post("/clima/publicar")

	assert resposta.status_code == 200
	assert resposta.get_json()["topico"] == main.MQTT_DISPLAY_TOPIC
	assert resposta.get_json()["dados"] == dados_clima
	publicar.assert_called_once()
	assert publicar.call_args.args[0] == main.MQTT_DISPLAY_TOPIC
	resultado_publicacao.wait_for_publish.assert_called_once_with(timeout=5)


def test_nao_publica_clima_com_mqtt_desconectado(monkeypatch):
	monkeypatch.setattr(main.cliente_mqtt, "is_connected", Mock(return_value=False))
	publicar = Mock()
	monkeypatch.setattr(main.cliente_mqtt, "publish", publicar)

	resposta = main.app.test_client().post("/clima/publicar")

	assert resposta.status_code == 503
	publicar.assert_not_called()


def test_post_dados_validos(monkeypatch): #estender o comportamento de um programa em tempo de execução
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
