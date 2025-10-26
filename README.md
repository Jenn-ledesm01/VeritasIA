🤖 Proyecto VeritasIA: Asistente de Verificación de Noticias

Este proyecto es un asistente de chat impulsado por LangChain, Neo4j y el modelo de lenguaje Llama3.2, diseñado para responder preguntas basadas en un grafo de conocimiento de noticias y su veracidad.

1. ⚙️ Requisitos Previos

Antes de ejecutar el proyecto, asegúrate de tener instalados los siguientes componentes:

1.1. Python y Dependencias

Necesitas Python 3.9 o superior.

Instalar dependencias de Python:
Asegúrate de que todas las librerías necesarias estén instaladas. Ejecuta el siguiente comando en tu terminal (probablemente necesites un requirements.txt, pero aquí están las principales):

pip install langchain-community langchain-ollama langchain-core python-dotenv neo4j


1.2. Servidor de Lenguaje (Ollama)

Necesitas tener Ollama instalado y corriendo localmente para que el modelo Llama3.2 pueda ser accedido por el script.

Instalar Ollama: Sigue las instrucciones oficiales para tu sistema operativo.

Descargar y ejecutar el modelo llama3.2:
Abre tu terminal y ejecuta el siguiente comando. Esto descargará el modelo y lo mantendrá corriendo en el puerto predeterminado (127.0.0.1:11434).

ollama run llama3.2


Nota: El script de Python asume que el modelo llama3.2 está corriendo en http://127.0.0.1:11434.

1.3. Base de Datos Neo4j

Necesitas acceso a la base de datos de Neo4j configurada para el proyecto.

Credenciales de Acceso: Verifica que las siguientes credenciales en el archivo veritas_ia.py sean correctas (o usa un archivo .env):

NEO4J_URI

NEO4J_USER

NEO4J_PASSWORD

NEO4J_DATABASE

Carga de Datos: ¡Es crucial! Asegúrate de que los datos iniciales y el esquema de Frames (Declaracion de frames en cypher (1).txt y Carga inicial datos (1).txt) estén cargados en la base de datos remota para que las consultas funcionen.

2. ▶️ Instrucciones de Ejecución

Una vez que todos los requisitos previos están listos (especialmente Ollama y el modelo llama3.2 corriendo), puedes iniciar el asistente.

Ejecutar el script principal:
Abre tu terminal en la carpeta donde se encuentra veritas_ia.py y ejecuta:

python veritas_ia.py


Interactuar con el Asistente:
El chat comenzará y podrás hacer preguntas sobre el grafo de conocimiento.

Preguntas de Veracidad (Fijas): El script usa una consulta Cypher robusta y fija para estas preguntas, lo que garantiza resultados rápidos y precisos.

Ejemplo: ¿Cuántas noticias falsas hay en el sistema y cuáles son sus titulares?

Ejemplo: Dame el conteo de noticias verdaderas.

Preguntas Generales (LLM Genera Cypher): Para cualquier otra pregunta, el LLM generará la consulta Cypher.

Ejemplo: ¿Qué tipos de evidencia existen?

Modo Debug: Para ver el Cypher generado y el contexto de Neo4j en la terminal, añade --debug al final de tu pregunta:

Ejemplo: ¿Qué tipos de evidencia existen? --debug

Finalizar: Escribe salir para cerrar el asistente.
