from flask import Flask, jsonify, request, send_from_directory
import paho.mqtt.client as mqtt
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
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
MQTT_DISPLAY_TOPIC = f"{MQTT_TOPIC}/display"
mqtt_erro = None


def buscar_clima_open_meteo():
    parametros = urlencode({
        "latitude": -22.72528,
        "longitude": -47.64917,
        "current": (
            "temperature_2m,relative_humidity_2m,apparent_temperature,"
            "wind_speed_10m,weather_code"
        ),
        "timezone": "America/Sao_Paulo",
    })
    url = f"https://api.open-meteo.com/v1/forecast?{parametros}"

    with urlopen(url, timeout=10) as resposta:
        dados_api = json.loads(resposta.read().decode("utf-8"))

    atual = dados_api["current"]
    codigo_clima = int(atual["weather_code"])
    descricoes_clima = {
        0: "Ensolarado",
        1: "P. nublado",
        2: "P. nublado",
        3: "Nublado",
        45: "Neblina",
        48: "Neblina",
        51: "Chuvisco",
        53: "Chuvisco",
        55: "Chuvisco",
        56: "Chuvisco",
        57: "Chuvisco",
        61: "Chuvoso",
        63: "Chuvoso",
        65: "Chuvoso",
        66: "Chuva gelo",
        67: "Chuva gelo",
        71: "Nevasca",
        73: "Nevasca",
        75: "Nevasca",
        77: "Neve",
        80: "Pancadas",
        81: "Pancadas",
        82: "Pancadas",
        85: "Neve",
        86: "Neve",
        95: "Tempestade",
        96: "Tempestade",
        99: "Tempestade",
    }

    return {
        "hora": atual["time"].split("T")[-1] + ":00",
        "temperatura": float(atual["temperature_2m"]),
        "umidade": float(atual["relative_humidity_2m"]),
        "sensacao": float(atual["apparent_temperature"]),
        "vento": float(atual["wind_speed_10m"]),
        "clima": descricoes_clima.get(codigo_clima, "Indisponivel"),
    }


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

def ao_conectar(client, userdata, flags, reason_code, properties):

    global mqtt_erro

    if reason_code == 0:

        mqtt_erro = None

        print("Conectado ao MQTT!")

        client.subscribe(MQTT_TOPIC)

        print("Inscrito no tópico:")
        print(MQTT_TOPIC)

    else:

        mqtt_erro = str(reason_code)
        print("Erro ao conectar ao MQTT:", reason_code)


def ao_desconectar(client, userdata, disconnect_flags, reason_code, properties):

    global mqtt_erro
    mqtt_erro = str(reason_code)
    print("MQTT desconectado:", reason_code)


def ao_falhar_conexao(client, userdata):

    global mqtt_erro
    mqtt_erro = "Não foi possível alcançar o broker MQTT; tentando novamente"
    print(mqtt_erro)


def ao_receber_mensagem(client, userdata, mensagem):

    print("\n===================================")
    print("Mensagem recebida pelo MQTT")
    print("===================================")

    try:

        texto = mensagem.payload.decode("utf-8-sig").strip()

        print("Mensagem:")
        print(texto)

        dados = json.loads(texto)
        if not isinstance(dados, dict):
            raise ValueError("o payload MQTT deve ser um objeto JSON")

        print("Dados recebidos:")
        print(dados)

        salvar_dados(dados)

        print("Dados salvos no banco!")

    except json.JSONDecodeError as erro:

        print(f"Erro: JSON MQTT inválido no tópico {mensagem.topic}: {erro}")
        print(f"Payload bruto: {mensagem.payload!r}")

    except ValueError as erro:

        print("Erro de validação:")
        print(erro)

    except Exception as erro:

        print("Erro ao processar mensagem:")
        print(erro)


# 
# CLIENTE MQTT
# 

cliente_mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

cliente_mqtt.on_connect = ao_conectar
cliente_mqtt.on_disconnect = ao_desconectar
cliente_mqtt.on_connect_fail = ao_falhar_conexao
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


@app.route("/painel", methods=["GET"])
def painel():

    return send_from_directory(BASE_DIR, "index.html")


@app.route("/status", methods=["GET"])
def status():

    return jsonify({
        "api": True,
        "mqtt": cliente_mqtt.is_connected(),
        "topico": MQTT_TOPIC,
        "mqtt_erro": mqtt_erro
    })


@app.route("/clima/publicar", methods=["POST"])
def publicar_clima_para_placa():
    if not cliente_mqtt.is_connected():
        return jsonify({
            "erro": "Cliente MQTT do servidor está desconectado"
        }), 503

    try:
        dados = buscar_clima_open_meteo()
        resultado = cliente_mqtt.publish(
            MQTT_DISPLAY_TOPIC,
            json.dumps(dados, ensure_ascii=False),
            qos=1,
        )
        if resultado.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"Falha ao publicar no MQTT (código {resultado.rc})")

        resultado.wait_for_publish(timeout=5)
        if not resultado.is_published():
            raise TimeoutError("O broker não confirmou a publicação MQTT")

        return jsonify({
            "mensagem": "Clima enviado para a placa",
            "topico": MQTT_DISPLAY_TOPIC,
            "dados": dados,
        }), 200
    except Exception as erro:
        app.logger.exception("Falha ao enviar clima para a placa")
        return jsonify({
            "erro": str(erro)
        }), 502


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

    global mqtt_erro

    try:

        cliente_mqtt.reconnect_delay_set(min_delay=2, max_delay=30)
        cliente_mqtt.connect_async(
            MQTT_BROKER,
            MQTT_PORT,
            60
        )

        mqtt_erro = "Conectando ao broker MQTT"
        cliente_mqtt.loop_start()

        print("Tentativa de conexão MQTT iniciada; reconexão automática ativa.")

    except Exception as erro:

        mqtt_erro = str(erro)
        print("Erro ao iniciar MQTT:", erro)


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
        debug=True,
        use_reloader=False
    )
