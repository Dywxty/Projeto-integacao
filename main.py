from flask import Flask, jsonify, request
import paho.mqtt.client as mqtt
import json
import os
from pathlib import Path
import psycopg
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
# CORS
@app.after_request
def permitir_frontend(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


# CONFIGURAÇÕES MQTT
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "senai510/lttl/relogio"


# BANCO DE DADOS
DATABASE_URL = os.getenv("DATABASE_URL")


def conectar_banco():
    """
    Cria uma conexão com o PostgreSQL do Neon.
    """
    if not DATABASE_URL or not DATABASE_URL.startswith(("postgresql://", "postgres://")):
        raise RuntimeError(
            "DATABASE_URL não foi configurada corretamente no arquivo .env"
        )

    return psycopg.connect(DATABASE_URL)


def criar_tabela():
    """
    Cria a tabela e o índice caso ainda não existam.
    Não apaga dados existentes.
    """

    schema_path = BASE_DIR / "schema.sql"
    schema = schema_path.read_text(encoding="utf-8")

    with conectar_banco() as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(schema)


# 
# VALIDAÇÃO DOS DADOS
# 

def validar_dados(dados):
    """
    Valida os dados recebidos pela API ou pelo MQTT.
    """

    campos_obrigatorios = [
        "hora",
        "temperatura",
        "umidade",
        "sensacao",
        "vento",
        "clima"
    ]

    # Verifica campos obrigatórios
    campos_ausentes = [
        campo
        for campo in campos_obrigatorios
        if campo not in dados
    ]

    if campos_ausentes:
        return (
            False,
            f"Campos obrigatórios ausentes: {', '.join(campos_ausentes)}"
        )

    # Verifica valores numéricos
    try:
        temperatura = float(dados["temperatura"])
        umidade = float(dados["umidade"])
        sensacao = float(dados["sensacao"])
        vento = float(dados["vento"])
    except (TypeError, ValueError):
        return (
            False,
            "temperatura, umidade, sensacao e vento devem ser valores numéricos"
        )

    # Temperatura
    if temperatura < -50 or temperatura > 70:
        return (
            False,
            "A temperatura deve estar entre -50 e 70 graus Celsius"
        )

    # Umidade
    if umidade < 0 or umidade > 100:
        return (
            False,
            "A umidade deve estar entre 0 e 100%"
        )

    # Vento
    if vento < 0:
        return (
            False,
            "O vento deve ser maior ou igual a 0"
        )

    return True, None



# SALVAR DADOS
def salvar_dados(dados):

    valido, erro = validar_dados(dados)

    if not valido:
        raise ValueError(erro)

    with conectar_banco() as conexao:
        with conexao.cursor() as cursor:

            cursor.execute("""
                INSERT INTO leituras (
                    hora,
                    temperatura,
                    umidade,
                    sensacao,
                    vento,
                    clima
                )
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                dados["hora"],
                float(dados["temperatura"]),
                float(dados["umidade"]),
                float(dados["sensacao"]),
                float(dados["vento"]),
                dados["clima"]
            ))

        conexao.commit()


# 
# MQTT
# 

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

    except json.JSONDecodeError:

        print("Erro: a mensagem MQTT não contém um JSON válido.")

    except ValueError as erro:

        print("Erro de validação:")
        print(erro)

    except Exception as erro:

        print("Erro ao processar mensagem:")
        print(erro)


# 
# CLIENTE MQTT
# 

cliente_mqtt = mqtt.Client()

cliente_mqtt.on_connect = ao_conectar
cliente_mqtt.on_message = ao_receber_mensagem


# 
# ROTAS FLASK
# 

@app.route("/")
def inicio():

    return jsonify({
        "projeto": "Weather IoT",
        "status": "online",
        "mqtt": MQTT_TOPIC
    })


# 
# POST /dados
# 

@app.route("/dados", methods=["POST"])
def receber_dados():

    # Verifica se o conteúdo é JSON válido
    if not request.is_json:
        return jsonify({
            "erro": "O corpo da requisição deve ser um JSON válido"
        }), 400

    try:

        dados = request.get_json()

    except Exception:

        return jsonify({
            "erro": "JSON inválido"
        }), 400

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

    except ValueError as erro:

        return jsonify({
            "erro": str(erro)
        }), 400

    except psycopg.Error as erro:

        return jsonify({
            "erro": "Erro ao acessar o banco de dados",
            "detalhes": str(erro)
        }), 500

    except Exception as erro:

        return jsonify({
            "erro": str(erro)
        }), 500


# 
# GET /dados
# 

@app.route("/dados", methods=["GET"])
def listar_dados():

    try:

        with conectar_banco() as conexao:
            with conexao.cursor() as cursor:

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
                    ORDER BY data_hora DESC
                """)

                registros = cursor.fetchall()

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
                "data_hora": (
                    registro[7]
                    if isinstance(registro[7], str)
                    else registro[7].isoformat()
                )
            })

        return jsonify(dados), 200

    except psycopg.Error as erro:

        return jsonify({
            "erro": "Erro ao acessar o banco de dados",
            "detalhes": str(erro)
        }), 500

    except Exception as erro:

        return jsonify({
            "erro": str(erro)
        }), 500


# 
# GET /dados/ultimo
# 

@app.route("/dados/ultimo", methods=["GET"])
def ultimo_dado():

    try:

        with conectar_banco() as conexao:
            with conexao.cursor() as cursor:

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
                    ORDER BY data_hora DESC
                    LIMIT 1
                """)

                registro = cursor.fetchone()

        # Banco sem registros
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
            "data_hora": (
                registro[7]
                if isinstance(registro[7], str)
                else registro[7].isoformat()
            )

        }

        return jsonify(dados), 200

    except psycopg.Error as erro:

        return jsonify({
            "erro": "Erro ao acessar o banco de dados",
            "detalhes": str(erro)
        }), 500

    except Exception as erro:

        return jsonify({
            "erro": str(erro)
        }), 500


# 
# INICIAR MQTT
# 

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


# 
# INICIALIZAÇÃO
# 

if __name__ == "__main__":

    print("===================================")
    print("       WEATHER IoT - FLASK")
    print("===================================")

    try:

        criar_tabela()

        print("Banco de dados conectado!")
        print("Tabela 'leituras' verificada!")

    except Exception as erro:

        print("ERRO AO CONFIGURAR O BANCO:")
        print(erro)

    iniciar_mqtt()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
