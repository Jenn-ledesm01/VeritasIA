# --- INICIALIZACIÓN Y CONFIGURACIÓN ---
import re
from langchain_community.graphs import Neo4jGraph 
from langchain_ollama import ChatOllama 
from langchain_core.prompts import PromptTemplate
from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain

# Configuración de conexión a Neo4j
NEO4J_URI = "neo4j+s://dc72b8db.databases.neo4j.io"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "9ERAWvMoJgoolM5s1_UfpHklmMs7rngUJVSz111Task"
NEO4J_DATABASE = "neo4j"

# Inicializar grafo
try:
    graph = Neo4jGraph(
        url=NEO4J_URI,
        username=NEO4J_USER,
        password=NEO4J_PASSWORD,
        database=NEO4J_DATABASE 
    )
    # Refrescar esquema una vez al inicio para preguntas generales
    graph_schema = graph.get_schema
except Exception as e:
    print(f"Error al conectar con Neo4j: {e}")
    print("Asegúrate de que las credenciales son correctas.")
    exit()

# Configurar modelo LLM
llm = ChatOllama(
    model="llama3.2",
    temperature=0.3,
    base_url="http://127.0.0.1:11434",
    top_p=0.9,
    num_predict=512
)

# Template para la generación de la respuesta final
FINAL_ANSWER_TEMPLATE = """
Basado en el contexto de Neo4j proporcionado a continuación, responde la pregunta de la manera más natural y concisa posible.

Contexto del Grafo: {context}

Pregunta original: {question}
"""
final_answer_prompt = PromptTemplate(
    template=FINAL_ANSWER_TEMPLATE,
    input_variables=["context", "question"]
)
final_answer_chain = final_answer_prompt | llm

# Diccionario de mapeo de palabras clave de veracidad
VERACITY_MAP = {
    'falsa': 'Falsa',
    'falsas': 'Falsa',
    'verdadera': 'Verdadera',
    'verdaderas': 'Verdadera',
    'indeterminada': 'Indeterminada',
    'indeterminadas': 'Indeterminada',
}

# --- FUNCIONES DE LÓGICA DE NEGOCIO ---

def get_veracity_query_info(pregunta: str):
    """
    Busca palabras clave de veracidad en la pregunta y retorna el valor de Cypher.
    """
    lower_pregunta = pregunta.lower()
    for key, value in VERACITY_MAP.items():
        if key in lower_pregunta:
            return value
    return None

def execute_fixed_cypher(veracity_value: str, pregunta: str):
    """
    Ejecuta una consulta Cypher fija y robusta para obtener el conteo y titulares de noticias.
    Esta consulta asume que los titulares existen como una propiedad en algún nodo conectado a :Resultado.
    """
    
    # 🚨 CONSULTA ROBUSTA Y FIJA 🚨:
    # Busca CUALQUIER nodo (n) que tenga la propiedad 'titular' (asumiendo que es la noticia).
    # Luego busca cualquier camino (corta distancia) hasta un nodo :Resultado con el valor deseado.
    CYPHER = f"""
    MATCH (n) 
    WHERE EXISTS(n.titular) 
    MATCH (n)-[*1..2]->(r:Resultado)
    WHERE r.valor = '{veracity_value}'
    RETURN count(n) AS count, collect(n.titular) AS titulares
    """
    
    try:
        # Ejecutar el Cypher directamente en la base de datos
        result = graph.query(CYPHER)

        # Procesar el resultado
        count = 0
        titulares = []
        if result and result[0]['count'] is not None:
            count = result[0]['count']
            # Usamos list(set(...)) para limpiar y evitar duplicados
            titulares = list(set(result[0]['titulares'])) if result[0]['titulares'] else []
        
        # Formatear el contexto para que el LLM genere la respuesta final
        if count > 0:
            titulares_str = ", ".join(titulares)
            contexto = f"Se encontraron {count} noticias con veracidad '{veracity_value}'. Sus titulares son: {titulares_str}"
        else:
            contexto = f"No se encontraron noticias con veracidad '{veracity_value}'. La base de datos no tiene datos que coincidan con esta veracidad."
        
        # Generar la respuesta final usando el LLM
        final_response = final_answer_chain.invoke({"context": contexto, "question": pregunta}).content

        return {
            "pregunta": pregunta,
            "respuesta": final_response,
            "cypher_generado": CYPHER.strip(),
            "datos_recuperados": contexto,
            "exito": True
        }
    except Exception as e:
        return {
            "pregunta": pregunta,
            "respuesta": f"Lo siento, ocurrió un error al ejecutar la consulta de veracidad. Esto podría indicar que la propiedad 'titular' o la etiqueta ':Resultado' no existen en la base de datos. Error: {str(e)}",
            "cypher_generado": CYPHER.strip(),
            "datos_recuperados": "N/A",
            "exito": False
        }


def consultar_veritas(pregunta: str) -> dict:
    """
    Procesa una pregunta del usuario.
    Prioriza la ejecución de Cypher fijo para preguntas de veracidad.
    """
    veracity_value = get_veracity_query_info(pregunta)
    
    # 1. Si es una pregunta de Veracidad (Falsa/Verdadera/Indeterminada), usamos Cypher fijo.
    if veracity_value:
        return execute_fixed_cypher(veracity_value, pregunta)

    # 2. Si no es de veracidad, usamos la cadena LLM tradicional (para el resto de preguntas)
    else:
        # --- PROMPT PARA PREGUNTAS GENERALES ---
        GENERIC_CYPHER_TEMPLATE = """
        Eres un experto en generar consultas Cypher de Neo4j.
        Traduce la siguiente pregunta a una consulta Cypher VÁLIDA.
        Considera este esquema como la base de datos: {schema}
        
        Pregunta: {question}
        """
        generic_cypher_prompt = PromptTemplate(template=GENERIC_CYPHER_TEMPLATE, input_variables=["schema", "question"])

        # Para preguntas generales, usamos el LLM para generar Cypher
        generic_chain = GraphCypherQAChain.from_llm(
            llm=llm,
            graph=graph,
            verbose=False,
            cypher_prompt=generic_cypher_prompt.partial(schema=graph_schema),
            allow_dangerous_requests=True,
            return_intermediate_steps=True
        )

        try:
            resultado = generic_chain.invoke({"query": pregunta}) 
            return {
                "pregunta": pregunta,
                "respuesta": resultado["result"],
                "cypher_generado": resultado["intermediate_steps"][0]["query"],
                "datos_recuperados": resultado["intermediate_steps"][1]["context"],
                "exito": True
            }
        except Exception as e:
            # Si hay un error, lo registramos.
            print(f"DEBUG ERROR: Fallo en consulta general: {e}")
            return {
                "pregunta": pregunta,
                "respuesta": f"Lo siento, ocurrió un error al procesar tu consulta general: {str(e)}. Intenta preguntar solo por la veracidad (Falsa/Verdadera/Indeterminada).",
                "exito": False
            }


# --- CHAT INTERACTIVO ---
def chat_veritasia():
    """
    Bucle de conversación con el asistente
    """
    print("=== VeritasIA Chat Asistente ===")
    print("Pregúntame sobre noticias, evidencias y verificaciones.")
    print("Asegúrate de que Ollama esté corriendo con el modelo llama3.2")
    print("Escribe 'salir' para terminar.\n")

    while True:
        pregunta = input("Tú: ")

        if pregunta.lower() in ['salir', 'exit', 'quit']:
            print("¡Hasta pronto!")
            break

        resultado = consultar_veritas(pregunta)

        print(f"\nVeritasIA: {resultado['respuesta']}\n")

        # Muestra los datos intermedios si el usuario añade --debug
        if '--debug' in pregunta.lower():
            print(f"[DEBUG] Tipo de consulta: {'Fija (Veracidad)' if get_veracity_query_info(pregunta) else 'General (LLM)'}")
            print(f"[DEBUG] Cypher ejecutado: {resultado.get('cypher_generado', 'N/A')}")
            print(f"[DEBUG] Datos de Neo4j: {resultado.get('datos_recuperados', 'N/A')}\n")

# Ejecutar asistente
if __name__ == "__main__":
    chat_veritasia()
