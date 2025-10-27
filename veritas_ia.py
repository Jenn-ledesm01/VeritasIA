# veritasia_auto_simple.py
import re
from langchain_community.graphs import Neo4jGraph
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate

# ---- CONFIG ----
LLM_MODEL = "llama3.2"
OLLAMA_URL = "http://localhost:11434"
NEO4J_URI = "neo4j+s://dc72b8db.databases.neo4j.io"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "9ERAWvMoJgoolM5s1_UfpHklmMs7rngUJVSz111Task"
NEO4J_DATABASE = "neo4j"

graph = Neo4jGraph(
    url=NEO4J_URI,
    username=NEO4J_USER,
    password=NEO4J_PASSWORD,
    database=NEO4J_DATABASE
)

llm = ChatOllama(model=LLM_MODEL, base_url=OLLAMA_URL, temperature=0.3)

FINAL_PROMPT = PromptTemplate(
    template="""Basado en el siguiente análisis, determina si la noticia parece verdadera o falsa y explica brevemente:
Contexto: {context}
Pregunta: {question}""",
    input_variables=["context", "question"]
)

def split_into_sentences(text: str):
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s for s in sentences if len(s.split()) > 3]

def insert_news_and_evidences(graph, title: str, text: str, evidencias):
    from random import randint
    news_id = randint(1000, 9999)

    # Parametrización segura
    cypher_lines = [
        "MERGE (n:Noticia {id: $news_id})",
        "SET n.titular = $title, n.texto = $text, n.fecha = date()"
    ]

    for i, ev_text in enumerate(evidencias, start=1):
        cypher_lines.append(f"MERGE (e{i}:Evidencia {{id: $ev_id{i}}})")
        cypher_lines.append(f"SET e{i}.contenido = $ev_text{i}")
        cypher_lines.append(f"MERGE (n)-[:tiene]->(e{i})")

    cypher = "\n".join(cypher_lines)

    # Construimos los parámetros
    params = {"news_id": news_id, "title": title, "text": text}
    for i, ev_text in enumerate(evidencias, start=1):
        params[f"ev_id{i}"] = f"{news_id}_{i}"
        params[f"ev_text{i}"] = ev_text

    graph.query(cypher, params)
    return news_id


def run_processing_pipeline(graph, news_id):
    """Ejecuta el pipeline de análisis de veracidad y devuelve todos los problemas si la noticia es falsa."""
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
    """Genera la explicación final con LLM."""
    context = f"Titular: {news_info['titular']}\nResultado: {news_info['estado']}\nJustificación: {news_info['justificacion']}"
    question = "¿Cuál es la veracidad de esta noticia y por qué?"
    chain = FINAL_PROMPT | llm
    return chain.invoke({"context": context, "question": question}).content


# ---- MAIN ----
def main():
    print("=== VeritasIA - Análisis automático (sin embeddings) ===")
    title = input("Titular de la noticia: ").strip()
    text = input("Pega el texto completo de la noticia:\n\n")

    # 1️⃣ Tokenización en evidencias
    evidencias = split_into_sentences(text)
    print(f"\nSe detectaron {len(evidencias)} posibles evidencias.")

    # 2️⃣ Inserción en Neo4j
    news_id = insert_news_and_evidences(graph, title, text, evidencias)

    # 3️⃣ Procesamiento y clasificación
    news_info = run_processing_pipeline(graph, news_id)

    # 4️⃣ Conclusión final con LLM
    answer = generate_final_answer(llm, news_info)

    print("\n=== RESULTADO FINAL ===")
    print(f"Titular: {news_info['titular']}")
    print(f"Veracidad: {news_info['estado']}")
    print(f"Justificación Cypher: {news_info['justificacion']}")
    print("\nRespuesta del modelo:")
    print(answer)


if __name__ == "__main__":
    main()
