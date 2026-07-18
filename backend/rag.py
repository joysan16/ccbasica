# rag.py — CareerCompass RAG Engine
# Handles: AI Mentor chat, concept explanation, MCQ generation

import os
import json
from dotenv import load_dotenv

load_dotenv()
os.environ['HF_TOKEN'] = os.getenv('HF_TOKEN', '')
# ── CONFIG ───────────────────────────────────────────────────────
BASE         = os.path.dirname(__file__)
KNOWLEDGE_DIR = os.path.join(BASE, '../data/knowledge')
VECTORSTORE  = os.path.join(BASE, '../data/vectorstore')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

# ── LAZY LOAD (only when first used) ────────────────────────────
_vectordb   = None
_llm        = None
_embeddings = None


def get_embeddings():
    global _embeddings
    if _embeddings is None:
        print("⏳ Loading embeddings model...")
        from langchain_huggingface import HuggingFaceEmbeddings
        _embeddings = HuggingFaceEmbeddings(
            model_name="all-MiniLM-L6-v2",
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        print("✅ Embeddings ready!")
    return _embeddings


def get_llm():
    global _llm
    if _llm is None:
        from langchain_groq import ChatGroq
        _llm = ChatGroq(
            api_key=GROQ_API_KEY,
            model_name="llama-3.1-8b-instant",
            temperature=0.3
        )
    return _llm


def get_vectordb():
    global _vectordb
    if _vectordb is None:
        from langchain_chroma import Chroma
        if not os.path.exists(VECTORSTORE):
            print("⚠️  Vectorstore not found. Building now...")
            build_vectorstore()
        _vectordb = Chroma(
            persist_directory=VECTORSTORE,
            embedding_function=get_embeddings()
        )
        print("✅ RAG vectorstore loaded")
    return _vectordb


# ── BUILD VECTORSTORE ────────────────────────────────────────────
def build_vectorstore():
    """
    Run once to create the vector database from knowledge files.
    Called automatically if vectorstore doesn't exist.
    """
    from langchain_chroma import Chroma
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    import shutil

    print("🔨 Building vectorstore from knowledge base...")

    # Delete old vectorstore if exists
    if os.path.exists(VECTORSTORE):
        shutil.rmtree(VECTORSTORE)

    # Load all .txt files from knowledge folder
    all_chunks   = []
    all_metadata = []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=60,
        separators=["\n\n", "\n", ". ", " "]
    )

    if not os.path.exists(KNOWLEDGE_DIR):
        os.makedirs(KNOWLEDGE_DIR)
        print(f"⚠️  Created empty knowledge dir: {KNOWLEDGE_DIR}")
        print("    Add .txt files to data/knowledge/ and restart.")
        return

    for filename in os.listdir(KNOWLEDGE_DIR):
        if not filename.endswith('.txt'):
            continue
        filepath = os.path.join(KNOWLEDGE_DIR, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()

        chunks = splitter.split_text(text)
        subject = filename.replace('.txt', '').replace('_', ' ').title()

        for chunk in chunks:
            all_chunks.append(chunk)
            all_metadata.append({'source': filename, 'subject': subject})

        print(f"  ✓ Loaded {filename} → {len(chunks)} chunks")

    if not all_chunks:
        print("⚠️  No chunks found. Add .txt files to data/knowledge/")
        return

    print(f"\n  Total chunks: {len(all_chunks)}")
    print("  Creating embeddings (first time may take ~2 mins)...")

    Chroma.from_texts(
        texts=all_chunks,
        metadatas=all_metadata,
        embedding=get_embeddings(),
        persist_directory=VECTORSTORE
    )

    print(f"✅ Vectorstore built → {VECTORSTORE}")


# ── CORE RAG FUNCTION ────────────────────────────────────────────
def rag_query(question: str, k: int = 4) -> dict:
    """
    Core RAG: retrieve relevant chunks + send to LLM.
    Returns dict with answer and sources.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    try:
        db  = get_vectordb()
        llm = get_llm()

        # Retrieve relevant chunks
        docs = db.similarity_search(question, k=k)
        if not docs:
            return {
                'answer': "I couldn't find relevant information. Please ask about ECE topics like Digital Electronics, C Programming, Networking, or Aptitude.",
                'sources': []
            }

        context = "\n\n".join([
            f"[{doc.metadata.get('subject','ECE')}]: {doc.page_content}"
            for doc in docs
        ])
        sources = list(set([doc.metadata.get('subject','') for doc in docs]))

        return {'context': context, 'sources': sources, 'llm': llm}

    except Exception as e:
        return {'error': str(e)}


# ── FEATURE 1: AI MENTOR CHAT ────────────────────────────────────
def mentor_chat(question: str, company: str = 'HCL') -> dict:
    """
    Student asks a doubt → RAG finds relevant content → LLM answers.
    Used in: AI Mentor chat page.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    result = rag_query(question)
    if 'error' in result:
        return {'answer': f"Error: {result['error']}", 'sources': []}

    if 'answer' in result:
        return result

    context = result['context']
    sources = result['sources']
    llm     = result['llm']

    system = f"""You are CareerCompass AI, a friendly placement mentor for ECE students targeting {company}.

Your job: Answer student doubts clearly and helpfully using the provided context.

RULES:
- Answer ONLY from the provided context
- Keep answers concise (3-6 sentences for simple questions, more for complex ones)
- Use simple language — student is preparing for placements, not PhD
- Give specific examples, numbers, formulas when available in context
- End with one exam tip if relevant
- If not in context, say: "I don't have that in my notes. Try asking about Digital Electronics, C Programming, Networking, or Aptitude."
- NEVER make up information"""

    user = f"""Context from ECE knowledge base:
{context}

Student question: {question}

Answer clearly and helpfully:"""

    try:
        messages  = [SystemMessage(content=system), HumanMessage(content=user)]
        response  = llm.invoke(messages)
        return {
            'answer':  response.content,
            'sources': sources
        }
    except Exception as e:
        return {'answer': f"LLM error: {str(e)}", 'sources': []}


# ── FEATURE 2: CONCEPT EXPLANATION ──────────────────────────────
def explain_concept(topic: str, level: str = 'Beginner') -> dict:
    """
    Student clicks a topic → RAG explains it in simple terms.
    Used in: Learn page when student clicks "Explain with AI".
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    question = f"Explain {topic} in detail"
    result   = rag_query(question, k=5)

    if 'error' in result:
        return {'explanation': f"Error: {result['error']}"}
    if 'answer' in result:
        return {'explanation': result['answer']}

    context = result['context']
    llm     = result['llm']

    level_instructions = {
        'Beginner':     'Use very simple language. Start from basics. Use analogies.',
        'Intermediate': 'Assume basic knowledge. Focus on key concepts and formulas.',
        'Expert':       'Go deeper. Include edge cases and interview-level details.'
    }
    instruction = level_instructions.get(level, level_instructions['Beginner'])

    system = f"""You are an ECE placement coach explaining concepts to students.
Student level: {level}. {instruction}

Structure your explanation as:
1. Simple definition (1-2 sentences)
2. Key points (3-5 bullet points)
3. Example or formula if applicable
4. One HCL exam tip

Use the provided context. Be clear and concise."""

    user = f"""Context:
{context}

Explain: {topic}"""

    try:
        messages = [SystemMessage(content=system), HumanMessage(content=user)]
        response = llm.invoke(messages)
        return {
            'explanation': response.content,
            'topic':       topic,
            'level':       level
        }
    except Exception as e:
        return {'explanation': f"Error: {str(e)}"}


# ── FEATURE 3: MCQ GENERATION ────────────────────────────────────
def generate_mcqs(topic: str, level: str = 'basic', count: int = 5) -> dict:
    """
    Generate fresh MCQs from knowledge base content.
    Used in: Practice page for AI-generated questions.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    question = f"Questions about {topic} for placement test"
    result   = rag_query(question, k=6)

    if 'error' in result:
        return {'questions': [], 'error': result['error']}
    if 'answer' in result:
        return {'questions': [], 'error': 'No content found'}

    context = result['context']
    llm     = result['llm']

    difficulty_map = {
        'basic':        'simple recall questions, straightforward options',
        'intermediate': 'application questions, tricky distractors',
        'expert':       'analysis questions, very close options, requires deep understanding'
    }
    difficulty = difficulty_map.get(level, difficulty_map['basic'])

    system = """You are an ECE placement test designer. Generate MCQs in STRICT JSON format.
Return ONLY valid JSON array, no markdown, no explanation, no backticks."""

    user = f"""Context:
{context}

Generate exactly {count} MCQs about "{topic}" at {level} level ({difficulty}).

Return ONLY this JSON format:
[
  {{
    "q": "Question text here?",
    "opts": ["Option A", "Option B", "Option C", "Option D"],
    "ans": 0,
    "exp": "Brief explanation why answer is correct"
  }}
]

Rules:
- ans is 0-indexed (0=A, 1=B, 2=C, 3=D)
- All 4 options must be plausible
- Questions must be based on provided context only
- Explanations must be clear and educational
- Return ONLY the JSON array, nothing else"""

    try:
        messages = [SystemMessage(content=system), HumanMessage(content=user)]
        response = llm.invoke(messages)

        # Clean and parse JSON
        raw = response.content.strip()
        raw = raw.replace('```json', '').replace('```', '').strip()

        # Find JSON array
        start = raw.find('[')
        end   = raw.rfind(']') + 1
        if start == -1 or end == 0:
            return {'questions': [], 'error': 'Invalid JSON from LLM'}

        questions = json.loads(raw[start:end])

        # Validate structure
        valid = []
        for q in questions:
            if all(k in q for k in ['q', 'opts', 'ans', 'exp']):
                if len(q['opts']) == 4 and isinstance(q['ans'], int):
                    valid.append(q)

        return {'questions': valid, 'topic': topic, 'level': level}

    except json.JSONDecodeError as e:
        return {'questions': [], 'error': f'JSON parse error: {str(e)}'}
    except Exception as e:
        return {'questions': [], 'error': str(e)}


# ── REBUILD VECTORSTORE ──────────────────────────────────────────
def rebuild():
    """Force rebuild vectorstore. Call when knowledge files change."""
    global _vectordb
    _vectordb = None
    build_vectorstore()
    _vectordb = None  # Force reload on next use
    print("✅ Vectorstore rebuilt. Restart Flask to apply.")


if __name__ == '__main__':
    print("Building CareerCompass RAG vectorstore...")
    build_vectorstore()
    print("\nTesting RAG...")
    r = mentor_chat("What is NAND gate and why is it called universal gate?")
    print("Answer:", r['answer'][:200])