from flask import Flask, jsonify, request
import paho.mqtt.client as mqtt
import sqlite3
import json
import os
from datetime import datetime

app = Flask(__name__)


@app.after_request
def permitir_frontend(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


# =========================================================
# CONFIGURAÇÕES
# =========================================================

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "senai510/lttl/relogio"


# =========================================================
# BANCO DE DADOS
# =========================================================

DATABASE_PATH = os.getenv("DATABASE_PATH", "weather.db")


def conectar_banco():
    conexao = sqlite3.connect(DATABASE_PATH)
    conexao.execute("PRAGMA journal_mode=WAL")
    return conexao


def criar_tabela():

    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leituras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hora VARCHAR(10),
            temperatura REAL,
            umidade REAL,
            sensacao REAL,
            vento REAL,
            clima VARCHAR(100),
            data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conexao.commit()

    cursor.close()
    conexao.close()


# =========================================================
# SALVAR DADOS
# =========================================================

def salvar_dados(dados):

    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute("""
        INSERT INTO leituras
        (hora, temperatura, umidade, sensacao, vento, clima)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        dados.get("hora"),
        dados.get("temperatura"),
        dados.get("umidade"),
        dados.get("sensacao"),
        dados.get("vento"),
        dados.get("clima")
    ))

    conexao.commit()

    cursor.close()
    conexao.close()


# =========================================================
# MQTT
# =========================================================

def ao_conectar(client, userdata, flags, rc):

    if rc == 0:

        print("Conectado ao MQTT!")

        client.subscribe(MQTT_TOPIC)

        print("Inscrito no tópico:")
        print(MQTT_TOPIC)

    else:

        print("Erro ao conectar ao MQTT:", rc)


def ao_receber_mensagem(client, userdata, mensagem):

    print("\n===================================")
    print("Mensagem recebida pelo MQTT")
    print("===================================")

    try:

        texto = mensagem.payload.decode()

        print("Mensagem:")
        print(texto)

        dados = json.loads(texto)

        print("Dados recebidos:")
        print(dados)

        salvar_dados(dados)

        print("Dados salvos no banco!")

    except Exception as erro:

        print("Erro ao processar mensagem:")
        print(erro)


# =========================================================
# CLIENTE MQTT
# =========================================================

cliente_mqtt = mqtt.Client()

cliente_mqtt.on_connect = ao_conectar
cliente_mqtt.on_message = ao_receber_mensagem


# =========================================================
# ROTAS FLASK
# =========================================================

@app.route("/")
def inicio():

    return jsonify({
        "projeto": "Weather IoT",
        "status": "online",
        "mqtt": MQTT_TOPIC
    })


# ---------------------------------------------------------
# ROTA PARA RECEBER DADOS MANUALMENTE
# ---------------------------------------------------------

@app.route("/dados", methods=["POST"])
def receber_dados():

    dados = request.get_json()

    if not dados:

        return jsonify({
            "erro": "Nenhum dado enviado"
        }), 400

    try:

        salvar_dados(dados)

        return jsonify({
            "mensagem": "Dados recebidos e salvos com sucesso!",
            "dados": dados
        }), 201

    except Exception as erro:

        return jsonify({
            "erro": str(erro)
        }), 500


# ---------------------------------------------------------
# ROTA PARA CONSULTAR TODOS OS DADOS
# ---------------------------------------------------------

@app.route("/dados", methods=["GET"])
def listar_dados():

    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            id,
            hora,
            temperatura,
            umidade,
            sensacao,
            vento,
            clima,
            data_hora
        FROM leituras
        ORDER BY id DESC
    """)

    registros = cursor.fetchall()

    cursor.close()
    conexao.close()

    dados = []

    for registro in registros:

        dados.append({
            "id": registro[0],
            "hora": registro[1],
            "temperatura": registro[2],
            "umidade": registro[3],
            "sensacao": registro[4],
            "vento": registro[5],
            "clima": registro[6],
            "data_hora": registro[7] if isinstance(registro[7], str) else registro[7].isoformat()
        })

    return jsonify(dados)


# ---------------------------------------------------------
# ROTA PARA CONSULTAR O ÚLTIMO DADO
# ---------------------------------------------------------

@app.route("/dados/ultimo", methods=["GET"])
def ultimo_dado():

    conexao = conectar_banco()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT
            id,
            hora,
            temperatura,
            umidade,
            sensacao,
            vento,
            clima,
            data_hora
        FROM leituras
        ORDER BY id DESC
        LIMIT 1
    """)

    registro = cursor.fetchone()

    cursor.close()
    conexao.close()

    if not registro:

        return jsonify({
            "mensagem": "Nenhum dado encontrado",
            "dados": None
        }), 200

    dados = {

        "id": registro[0],
        "hora": registro[1],
        "temperatura": registro[2],
        "umidade": registro[3],
        "sensacao": registro[4],
        "vento": registro[5],
        "clima": registro[6],
        "data_hora": registro[7] if isinstance(registro[7], str) else registro[7].isoformat()

    }

    return jsonify(dados)


# =========================================================
# INICIAR MQTT
# =========================================================

def iniciar_mqtt():

    try:

        cliente_mqtt.connect(
            MQTT_BROKER,
            MQTT_PORT,
            60
        )

        cliente_mqtt.loop_start()

        print("MQTT iniciado!")

    except Exception as erro:

        print("Erro ao iniciar MQTT:")
        print(erro)


# INICIALIZAÇÃO
if __name__ == "__main__":

    print("===================================")
    print("       WEATHER IoT - FLASK")
    print("===================================")

    criar_tabela()

    iniciar_mqtt()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )