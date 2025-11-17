import streamlit as st
import re
from langchain_community.graphs import Neo4jGraph
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate

# ---- CONFIG ----
LLM_MODEL = "llama3.2"
OLLAMA_URL = "https://collins-reduces-correspondence-shirts.trycloudflare.com"
#OLLAMA_URL = "http://localhost:11434"
NEO4J_URI = "neo4j+s://18d82ec3.databases.neo4j.io"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "z8MX32MmuY1JfLRDXQA467AKttB73vZ6GGaW7YnTb9s"
NEO4J_DATABASE = "neo4j"

# Configuración de la página
st.set_page_config(
    page_title="VeritasIA Chat",
    page_icon="🔍", 
    layout="wide"
)

# Inicializar conexiones (con caché para mejor rendimiento)
@st.cache_resource
def init_connections():
    try:
        graph = Neo4jGraph(
            url=NEO4J_URI,
            username=NEO4J_USER,
            password=NEO4J_PASSWORD,
            database=NEO4J_DATABASE
        )
        llm = ChatOllama(model=LLM_MODEL, base_url=OLLAMA_URL, temperature=0.3)
        return graph, llm, None
    except Exception as e:
        return None, None, str(e)

graph, llm, connection_error = init_connections()

FINAL_PROMPT = PromptTemplate(
    template="""Basado en el siguiente análisis, determina si la noticia parece verdadera o falsa y explica brevemente:
Contexto: {context}
Pregunta: {question}""",
    input_variables=["context", "question"]
)

CHAT_PROMPT = PromptTemplate(
    template="""Eres VeritasIA, un asistente experto en verificación de noticias y detección de desinformación.

Conversación previa:
{history}

Usuario: {message}

Responde de forma amigable y útil. Si el usuario te pasa una noticia para analizar (puede ser con o sin formato específico), analízala. Si te hace preguntas sobre verificación de noticias, desinformación, o temas relacionados, responde con tu expertise. Si detectas que el mensaje contiene una noticia, ofrécete a analizarla.""",
    input_variables=["history", "message"]
)

def split_into_sentences(text: str):
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s for s in sentences if len(s.split()) > 3]

def insert_news_and_evidences(graph, title: str, text: str, evidencias):
    from random import randint
    news_id = randint(1000, 9999)

    cypher_lines = [
        "MERGE (n:Noticia {id: $news_id})",
        "SET n.titular = $title, n.texto = $text, n.fecha = date()"
    ]

    for i, ev_text in enumerate(evidencias, start=1):
        cypher_lines.append(f"MERGE (e{i}:Evidencia {{id: $ev_id{i}}})")
        cypher_lines.append(f"SET e{i}.contenido = $ev_text{i}")
        cypher_lines.append(f"MERGE (n)-[:tiene]->(e{i})")

    cypher = "\n".join(cypher_lines)

    params = {"news_id": news_id, "title": title, "text": text}
    for i, ev_text in enumerate(evidencias, start=1):
        params[f"ev_id{i}"] = f"{news_id}_{i}"
        params[f"ev_text{i}"] = ev_text

    graph.query(cypher, params)
    return news_id

def run_processing_pipeline(graph, news_id):
    cypher_processing = f"""
    MATCH (n:Noticia {{id: {news_id}}})
    WITH n
    CALL {{
        WITH n
        MATCH (n)-[:tiene]->(e:Evidencia)
        OPTIONAL MATCH (t:TipoEvidencia)
        WITH e, t, [word IN coalesce(t.palabras_clave, []) WHERE toLower(e.contenido) CONTAINS toLower(word)] AS coincidencias
        WHERE size(coincidencias) > 0
        WITH e, t, size(coincidencias) AS count
        ORDER BY count DESC, t.id
        WITH e, head(collect(t)) AS mejor_tipo, head(collect(count)) AS mejor_count
        WHERE mejor_tipo IS NOT NULL
        MERGE (e)-[:clasificada_en]->(mejor_tipo)
        SET e.peso = coalesce(mejor_tipo.peso_unitario, 0.0) * mejor_count
        RETURN count(*) AS clasificadas
        UNION
        WITH n
        RETURN 0 AS clasificadas
    }}
    WITH n
    MATCH (n)-[:tiene]->(todas_evidencias:Evidencia)
    MERGE (eval:Evaluacion {{id: n.id}})
    MERGE (eval)-[:evaluacion_de]->(n)
    MERGE (eval)-[:evidencias_analizadas]->(todas_evidencias)
    WITH n, eval
    OPTIONAL MATCH (n)-[:tiene]->(ev:Evidencia)-[:clasificada_en]->(t:TipoEvidencia)
    WHERE ev.peso > 0
    WITH eval, n, collect(DISTINCT t.nombre) AS tipos_encontrados
    WITH eval, n, [tipo IN tipos_encontrados WHERE tipo IS NOT NULL] AS tipos_unicos
    SET eval.resultado_parcial = tipos_unicos
    WITH n, eval, tipos_unicos
    MATCH (resultado_verdadera:Resultado {{valor: 'Verdadera'}})
    MATCH (resultado_falsa:Resultado {{valor: 'Falsa'}})
    WITH n, eval, tipos_unicos,
         CASE WHEN size(tipos_unicos) = 0 THEN resultado_verdadera ELSE resultado_falsa END AS resultado_aplicable
    MERGE (v:Veredicto {{id: n.id}})
    MERGE (v)-[:clasifica_una]->(n)
    MERGE (v)-[:tiene_resultado]->(resultado_aplicable)
    SET v.justificacion = CASE 
            WHEN size(tipos_unicos) = 0 THEN 'Sin evidencias problemáticas detectadas'
            ELSE 'Evidencias problemáticas: ' + apoc.text.join(tipos_unicos, ', ')
        END
    RETURN n.titular AS titular, resultado_aplicable.valor AS estado, v.justificacion AS justificacion;
    """
    result = graph.query(cypher_processing)
    return result[0] if result else None

def generate_final_answer(llm, news_info):
    context = f"Titular: {news_info['titular']}\nResultado: {news_info['estado']}\nJustificación: {news_info['justificacion']}"
    question = "¿Cuál es la veracidad de esta noticia y por qué?"
    chain = FINAL_PROMPT | llm
    return chain.invoke({"context": context, "question": question}).content

def analyze_news(title, text):
    """Analiza una noticia y devuelve el resultado."""
    try:
        evidencias = split_into_sentences(text)
        news_id = insert_news_and_evidences(graph, title, text, evidencias)
        news_info = run_processing_pipeline(graph, news_id)
        answer = generate_final_answer(llm, news_info)
        
        return {
            "success": True,
            "titular": news_info['titular'],
            "estado": news_info['estado'],
            "justificacion": news_info['justificacion'],
            "respuesta": answer,
            "evidencias_count": len(evidencias)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def chat_with_ai(message, history):
    """Chat libre con la IA."""
    try:
        history_text = ""
        for msg in history[-6:]:
            role = "Asistente" if msg["role"] == "assistant" else "Usuario"
            history_text += f"{role}: {msg['content'][:200]}...\n"
        
        chain = CHAT_PROMPT | llm
        response = chain.invoke({"history": history_text, "message": message})
        return {
            "success": True,
            "response": response.content
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def detect_news_in_message(message):
    """Detecta si el mensaje contiene una noticia para analizar."""
    message_lower = message.lower()
    
    if ("titular:" in message_lower or "título:" in message_lower) and \
       ("texto:" in message_lower or "noticia:" in message_lower):
        return True
    
    if len(message.split()) > 100:
        return True
    
    keywords = ["analiza", "verifica", "es verdad", "es falso", "fake news", 
                "noticia", "verificar", "revisar", "chequear"]
    if any(keyword in message_lower for keyword in keywords):
        return True
    
    return False

def extract_title_and_text(message):
    """Extrae titular y texto de un mensaje."""
    if "titular:" in message.lower() or "título:" in message.lower():
        parts = message.split("Texto:", 1) if "Texto:" in message else message.split("texto:", 1)
        if "Titular:" in parts[0]:
            title = parts[0].split("Titular:", 1)[1].strip()
        elif "titular:" in parts[0]:
            title = parts[0].split("titular:", 1)[1].strip()
        elif "Título:" in parts[0]:
            title = parts[0].split("Título:", 1)[1].strip()
        elif "título:" in parts[0]:
            title = parts[0].split("título:", 1)[1].strip()
        else:
            title = parts[0].strip()
        
        text = parts[1].strip() if len(parts) > 1 else ""
        return title, text
    
    lines = message.strip().split("\n")
    if len(lines) > 1:
        title = lines[0].strip()
        text = "\n".join(lines[1:]).strip()
        return title, text
    
    return "Noticia sin titular", message.strip()

# ---- INTERFAZ DE STREAMLIT ----
st.title("🔍 VeritasIA - Chat de Verificación de Noticias")
st.markdown("Verifica la veracidad de noticias usando IA y análisis de grafos")

# Verificar estado de conexión
if connection_error:
    st.error(f"""
    ⚠️ **Error de Conexión**
    
    No se pudo conectar a los servicios necesarios:
    
    ```
    {connection_error}
    ```
    
    **Posibles soluciones:**
    1. Verifica tu conexión a internet
    2. Asegúrate de que Ollama esté corriendo: `ollama serve`
    3. Verifica que el modelo llama3.2 esté instalado: `ollama pull llama3.2`
    4. Verifica las credenciales de Neo4j en el código
    5. Comprueba que la base de datos Neo4j esté accesible
    """)
    st.stop()

# Inicializar el historial de chat
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.messages.append({
        "role": "assistant",
        "content": """¡Hola! Soy VeritasIA 🔍

Puedo ayudarte a:
- 📰 Analizar noticias con grafos de conocimiento y Neo4j
- 💬 Responder preguntas sobre verificación de hechos
- 🎯 Detectar señales de desinformación

**Puedes chatear libremente conmigo.** Solo pégame la noticia que quieres verificar, o pregúntame lo que necesites.

Si quieres que analice una noticia, simplemente pégala aquí (con o sin formato). También puedes usar:
```
Titular: [Tu titular]
Texto: [Tu texto]
```

¿En qué puedo ayudarte hoy?"""
    })

if "waiting_for_news" not in st.session_state:
    st.session_state.waiting_for_news = False
    st.session_state.current_title = None
    st.session_state.current_text = None

# Mostrar historial de chat
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Input del usuario
if prompt := st.chat_input("Escribe tu mensaje aquí..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    with st.chat_message("assistant"):
        with st.spinner("Pensando..."):
            if detect_news_in_message(prompt):
                title, text = extract_title_and_text(prompt)
                
                if text and len(text.split()) > 10:
                    result = analyze_news(title, text)
                    
                    if result["success"]:
                        response = f"""### 📊 Resultado del Análisis con Neo4j

**Titular:** {result['titular']}

**Veracidad:** {'✅ ' if result['estado'] == 'Verdadera' else '❌ '}{result['estado']}

**Evidencias analizadas:** {result['evidencias_count']}

**Justificación técnica:** {result['justificacion']}

---

### 🤖 Análisis del Modelo:

{result['respuesta']}

---

¿Tienes otra noticia o alguna pregunta?"""
                    else:
                        response = f"❌ Error al analizar: {result['error']}\n\nIntenta de nuevo."
                else:
                    result = chat_with_ai(prompt, st.session_state.messages)
                    response = result["response"] if result["success"] else f"❌ Error: {result['error']}"
            else:
                result = chat_with_ai(prompt, st.session_state.messages)
                response = result["response"] if result["success"] else f"❌ Error: {result['error']}"
            
            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})

# Sidebar con información
with st.sidebar:
    st.header("ℹ️ Información")
    st.markdown("""
    ### 💬 Chat Libre
    
    Puedes chatear naturalmente:
    - Pega una noticia directamente
    - Pregunta sobre verificación
    - Pide consejos sobre fake news
    
    ### 📝 Formato recomendado:
    
    Para mejores resultados, usa:
    ```
    Titular: [Tu titular aquí]
    Texto: [Tu texto aquí]
    ```
    
    También puedes pegar la noticia directamente.
    
    ### 🔧 Tecnologías:
    - 🤖 Llama 3.2 (Ollama)
    - 🗄️ Neo4j (Grafos)
    - 🔗 LangChain
    - 🎨 Streamlit
    """)
    
    if st.button("🗑️ Limpiar chat"):
        st.session_state.messages = []
        st.session_state.waiting_for_news = False
        st.session_state.current_title = None
        st.session_state.current_text = None
        st.rerun()
