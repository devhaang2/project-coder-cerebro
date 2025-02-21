import streamlit as st
import requests
import json
from datetime import datetime
import os
import ast  # Para análise de sintaxe
from typing import List, Dict
import zipfile
import io
import firebase_admin
from firebase_admin import credentials, firestore
import tiktoken  # Para cálculo de tokens

# Inicialização do Firebase
if not firebase_admin._apps:
    # Caminho para o arquivo JSON de credenciais do Firebase
    cred = credentials.Certificate(r"E:\Projeto cerebro v2\chat proprio dophin0\db-coder-v1-b2519-firebase-adminsdk-fbsvc-91e2720cba.json")  # Substitua pelo caminho correto
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Função para listar todas as conversas salvas no Firebase
def list_conversations_from_firebase() -> list[str]:
    try:
        conversations = []
        docs = db.collection("conversations").stream()
        for doc in docs:
            conversations.append(doc.id)
        return sorted(conversations, reverse=True)
    except Exception as e:
        st.error(f"Erro ao listar conversas no Firebase: {str(e)}")
        return []

# Função para carregar conversa do Firebase
def load_conversation_from_firebase(conversation_name: str) -> list[dict]:
    try:
        doc = db.collection("conversations").document(conversation_name).get()
        if doc.exists:
            return doc.to_dict().get("messages", [])
        else:
            st.warning(f"A conversa '{conversation_name}' não foi encontrada.")
            return []
    except Exception as e:
        st.error(f"Erro ao carregar conversa do Firebase: {str(e)}")
        return []

# Função para salvar conversa no Firebase
def save_conversation_to_firebase(conversation_name: str, messages: list[dict]):
    try:
        db.collection("conversations").document(conversation_name).set({
            "messages": messages,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        st.success(f"Conversa salva no Firebase com o nome: {conversation_name}")
    except Exception as e:
        st.error(f"Erro ao salvar conversa no Firebase: {str(e)}")

# Função para calcular o número de tokens usando tiktoken
def count_tokens(text: str, model_name: str = "mistral") -> int:
    try:
        encoding = tiktoken.encoding_for_model(model_name)
        return len(encoding.encode(text))
    except KeyError:
        return len(text.split())  # fallback para contagem simples de palavras

# Implementação customizada da API OpenRouter
class OpenRouterChat:
    def __init__(self, api_key: str, model: str, site_url: str, site_name: str):
        self.api_key = api_key
        self.model = model
        self.site_url = site_url
        self.site_name = site_name
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.site_url,
            "X-Title": self.site_name,
        }
        self.context_dir = "contexts"
        self.knowledge_base_path = "knowledge_base.txt"
        self.suggestions_path = "suggestions.txt"
        os.makedirs(self.context_dir, exist_ok=True)

    def load_knowledge_base(self) -> str:
        try:
            with open(self.knowledge_base_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def save_knowledge_base(self, content: str):
        with open(self.knowledge_base_path, "w", encoding="utf-8") as f:
            f.write(content)

    def load_suggestions(self) -> str:
        try:
            with open(self.suggestions_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def save_suggestions(self, content: str):
        with open(self.suggestions_path, "w", encoding="utf-8") as f:
            f.write(content)

    def generate(self, messages: list[dict]) -> str:
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7
        }

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=self.headers,
            json=data
        )
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']

# Função para analisar o código Python
def analyze_code(code: str, knowledge_base: str) -> dict:
    analysis = {"syntax_errors": [], "improvements": []}

    try:
        # Tenta analisar a árvore de sintaxe
        ast.parse(code)
    except SyntaxError as e:
        analysis["syntax_errors"].append(str(e))

    # Verifica variáveis não utilizadas
    try:
        tree = ast.parse(code)
        variables = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        variables.add(target.id)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                variables.discard(node.id)

        if variables:
            analysis["improvements"].append(f"As variáveis {', '.join(variables)} foram definidas mas nunca utilizadas.")
    except Exception as e:
        analysis["improvements"].append(f"Erro durante a análise avançada: {str(e)}")

    # Verifica se há regras na knowledge_base que podem ser aplicadas
    if "não use variáveis globais" in knowledge_base.lower():
        if any(isinstance(node, ast.Global) for node in ast.walk(ast.parse(code))):
            analysis["improvements"].append("Evite o uso de variáveis globais conforme recomendado na base de conhecimento.")

    return analysis

# Função para extrair arquivos de um ZIP
def extract_zip(upload_file) -> str:
    temp_dir = "temp_project"
    os.makedirs(temp_dir, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(upload_file.read()), "r") as zip_ref:
        zip_ref.extractall(temp_dir)

    return temp_dir

# Função para gerar código corrigido e explicação
def generate_solution(code: str, filename: str, knowledge_base: str, model: str) -> dict:
    prompt = (
        f"Corrija o seguinte código Python do arquivo `{filename}` considerando as seguintes diretrizes:\n"
        f"{knowledge_base}\n\nCódigo original:\n{code}\n\n"
        "Forneça uma breve explicação do problema encontrado e sugira um código corrigido."
    )

    # Enviar o prompt ao modelo
    response = openrouter.generate([{"role": "user", "content": prompt}, {"role": "assistant", "content": ""}])

    # Parse da resposta para separar explicação e código corrigido
    explanation, corrected_code = "", ""
    parts = response.split("\nCódigo corrigido:\n", 1)
    if len(parts) == 2:
        explanation, corrected_code = parts[0].strip(), parts[1].strip()
    else:
        explanation, corrected_code = response.strip(), ""

    return {"explanation": explanation, "corrected_code": corrected_code}

# Função para gerar respostas contextualizadas sobre o código
def generate_code_discussion(prompt: str, code: str, knowledge_base: str, model: str) -> str:
    full_prompt = (
        f"Você está discutindo o seguinte código Python:\n\n{code}\n\n"
        f"Considere as seguintes diretrizes:\n{knowledge_base}\n\n"
        f"Pergunta: {prompt}"
    )
    return openrouter.generate([{"role": "user", "content": full_prompt}, {"role": "assistant", "content": ""}])

# Configuração da interface do Streamlit
st.title("🤖 OpenRouter Chat Agent")
st.caption("Powered by LangChain and Mistral 24B")

# Barra lateral para gerenciamento de conversas, base de conhecimento e configuração do modelo
with st.sidebar:
    st.header("Gerenciamento de Conversas")
    
    # Listar conversas salvas no Firebase
    conversations = list_conversations_from_firebase()  # Agora a função está definida antes
    selected_conversation = st.selectbox("Selecione uma conversa salva:", ["Nova Conversa"] + conversations)

    if selected_conversation != "Nova Conversa":
        if st.button("Carregar Conversa"):
            st.session_state.messages = load_conversation_from_firebase(selected_conversation)
            st.session_state.conversation_name = selected_conversation

    # Salvar conversa atual no Firebase
    if st.button("Salvar Conversa Atual no Firebase"):
        if "conversation_name" in st.session_state:
            conversation_name = st.session_state.conversation_name
        else:
            conversation_name = st.text_input("Digite um nome para a conversa:")
            if not conversation_name.strip():
                st.warning("Por favor, insira um nome válido para a conversa.")
                st.stop()
        
        save_conversation_to_firebase(conversation_name, st.session_state.messages)
        st.session_state.conversation_name = conversation_name

    # Gerenciamento da Knowledge Base
    st.header("Base de Conhecimento")
    if "knowledge_base_content" not in st.session_state:
        st.session_state.knowledge_base_content = ""
    updated_kb = st.text_area("Edite a Base de Conhecimento:", value=st.session_state.knowledge_base_content, height=200)
    if st.button("Salvar Base de Conhecimento"):
        st.session_state.knowledge_base_content = updated_kb
        st.success("Base de Conhecimento atualizada com sucesso!")

    # Gerenciamento de Sugestões Temporárias
    st.header("Sugestões Temporárias")
    if "suggestions_content" not in st.session_state:
        st.session_state.suggestions_content = ""
    updated_suggestions = st.text_area("Visualize ou Edite as Sugestões:", value=st.session_state.suggestions_content, height=200)
    if st.button("Salvar Sugestões Temporárias"):
        st.session_state.suggestions_content = updated_suggestions
        st.success("Sugestões Temporárias salvas com sucesso!")

    # Seletor de Modelos
    st.header("Configuração do Modelo")
    selected_model = st.selectbox(
        "Selecione o modelo:",
        [
            "deepseek/deepseek-r1:free",
            "deepseek/deepseek-r1-distill-llama-70b:free",
            "meta-llama/llama-3.3-70b-instruct:free",
        ]
    )

# Inicializa o cliente OpenRouter após a seleção do modelo
if "openrouter" not in st.session_state or st.session_state.selected_model != selected_model:
    st.session_state.openrouter = OpenRouterChat(
        api_key=st.secrets["OPENROUTER_API_KEY"],
        model=selected_model,  # Usa o modelo selecionado pelo usuário
        site_url="https://chat.example.com",
        site_name="AI Chat"
    )
    st.session_state.selected_model = selected_model

openrouter = st.session_state.openrouter

# Inicialização do estado da sessão
if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation_name" not in st.session_state:
    st.session_state.conversation_name = None
if "token_metrics" not in st.session_state:
    st.session_state.token_metrics = {"input_tokens": [], "output_tokens": []}

# Carregar a base de conhecimento
knowledge_base = openrouter.load_knowledge_base() if hasattr(openrouter, "load_knowledge_base") else ""

# Inicializar mensagem do sistema se for uma nova conversa
if not st.session_state.messages:
    system_message = "Você é um assistente útil e objetivo. Responda de forma concisa e verdadeira. "
    system_message += "Se não tiver certeza sobre algo, diga que não sabe. Comunique-se sempre em Português do Brasil. "
    system_message += "Seu propósito é auxiliar Marcos da melhor maneira possível.\n\n"
    system_message += f"Base de Conhecimento:\n{knowledge_base}"

    st.session_state.messages = [
        {"role": "system", "content": system_message}
    ]

# Carregador de arquivos ZIP contendo pastas de projetos
uploaded_zip = st.file_uploader("Carregue um arquivo ZIP contendo sua pasta de projeto (.zip)", type=["zip"])
if uploaded_zip:
    if "uploaded_codes" not in st.session_state:
        st.session_state.uploaded_codes = {}

    # Extrair o conteúdo do ZIP
    temp_dir = extract_zip(uploaded_zip)
    st.info(f"Pasta do projeto extraída: `{temp_dir}`")

    # Processar todos os arquivos .py na pasta extraída
    for root, _, files in os.walk(temp_dir):
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                with open(file_path, "r", encoding="utf-8") as f:
                    code_content = f.read()
                    st.session_state.uploaded_codes[file] = code_content

                # Exibir as primeiras 20 linhas como notificação
                first_20_lines = "\n".join(code_content.splitlines()[:20])
                st.info(f"Arquivo carregado: `{file}`\n\nPrimeiras 20 linhas:\n```\n{first_20_lines}\n```")

    # Botão para gerar soluções para todos os arquivos carregados
    if st.button("Gerar Soluções para Todos os Arquivos"):
        knowledge_base_content = openrouter.load_knowledge_base()
        for filename, code_content in st.session_state.uploaded_codes.items():
            # Gerar solução para o arquivo
            solution = generate_solution(code_content, filename, knowledge_base_content, openrouter.model)

            # Exibir a explicação
            st.write(f"### Solução para `{filename}`:")
            st.write("#### Explicação:")
            st.write(solution["explanation"])

            # Exibir o código corrigido de forma copiável
            st.write("#### Código Corrigido (Clique para Copiar):")
            st.code(solution["corrected_code"], language="python")

            # Salvar sugestões no arquivo temporário
            if solution["explanation"]:
                openrouter.save_suggestions(openrouter.load_suggestions() + "\n\n" + solution["explanation"])

# Exibir mensagens do chat
for msg in st.session_state.messages:
    if msg["role"] == "user":
        with st.chat_message("user"):
            st.write(msg["content"])
    elif msg["role"] == "assistant":
        with st.chat_message("assistant"):
            st.write(msg["content"])

# Tratamento de entrada de chat
if prompt := st.chat_input("Pergunte algo sobre o código ou discuta melhorias"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""

        # Contar tokens na entrada do usuário
        input_tokens = count_tokens(prompt, model_name=openrouter.model)
        st.session_state.token_metrics["input_tokens"].append(input_tokens)

        # Se houver arquivos carregados, usar o primeiro como contexto
        if "uploaded_codes" in st.session_state and st.session_state.uploaded_codes:
            filename, code_content = next(iter(st.session_state.uploaded_codes.items()))
            knowledge_base_content = openrouter.load_knowledge_base()
            response = generate_code_discussion(prompt, code_content, knowledge_base_content, openrouter.model)
        else:
            response = openrouter.generate(st.session_state.messages)

        full_response = response

        # Contar tokens na resposta do modelo
        output_tokens = count_tokens(full_response, model_name=openrouter.model)
        st.session_state.token_metrics["output_tokens"].append(output_tokens)

        response_placeholder.write(full_response)

    st.session_state.messages.append({"role": "assistant", "content": full_response})

# Mostrar gráfico de tokens
st.subheader("Métricas de Tokens")
if st.session_state.token_metrics["input_tokens"] or st.session_state.token_metrics["output_tokens"]:
    token_data = {
        "Input Tokens": st.session_state.token_metrics["input_tokens"],
        "Output Tokens": st.session_state.token_metrics["output_tokens"]
    }
    st.line_chart(token_data)
else:
    st.info("Nenhuma métrica de tokens disponível ainda.")