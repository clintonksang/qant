"""
Test script to verify Pinecone Vector DB connection and functionality.
Run this to confirm your vector database is working.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from pinecone import Pinecone
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from datetime import datetime

# Load environment
load_dotenv(Path(__file__).parent / ".env")

print("=" * 60)
print("🔍 PINECONE VECTOR DB CONNECTION TEST")
print("=" * 60)

# Check environment variables
print("\n1️⃣ Checking environment variables...")
pinecone_key = os.getenv("PINECONE_API_KEY")
index_name = os.getenv("PINECONE_INDEX_NAME")
openai_key = os.getenv("OPENAI_API_KEY")

if not pinecone_key:
    print("❌ PINECONE_API_KEY not found in .env")
else:
    print(f"✅ PINECONE_API_KEY: {pinecone_key[:20]}...")

if not index_name:
    print("❌ PINECONE_INDEX_NAME not found in .env")
else:
    print(f"✅ PINECONE_INDEX_NAME: {index_name}")

if not openai_key:
    print("❌ OPENAI_API_KEY not found in .env")
else:
    print(f"✅ OPENAI_API_KEY: {openai_key[:20]}...")

# Test Pinecone connection
print("\n2️⃣ Testing Pinecone connection...")
try:
    pc = Pinecone(api_key=pinecone_key)
    indexes = pc.list_indexes()
    print(f"✅ Connected to Pinecone!")
    print(f"   Available indexes: {[idx.name for idx in indexes]}")
    
    # Get index stats
    index = pc.Index(index_name)
    stats = index.describe_index_stats()
    print(f"   Index '{index_name}' stats:")
    print(f"   - Total vectors: {stats.total_vector_count}")
    print(f"   - Namespaces: {list(stats.namespaces.keys()) if stats.namespaces else 'default only'}")
except Exception as e:
    print(f"❌ Pinecone connection failed: {e}")

# Test embeddings
print("\n3️⃣ Testing OpenAI Embeddings...")
try:
    class TruncatedEmbeddings(OpenAIEmbeddings):
        def embed_query(self, text: str):
            return super().embed_query(text)[:512]
        def embed_documents(self, texts: list[str]):
            return [e[:512] for e in super().embed_documents(texts)]
    
    embeddings = TruncatedEmbeddings(model="text-embedding-3-small")
    test_embedding = embeddings.embed_query("Test gold trading pattern")
    print(f"✅ Embeddings working! Dimension: {len(test_embedding)}")
except Exception as e:
    print(f"❌ Embeddings failed: {e}")

# Test vector store
print("\n4️⃣ Testing LangChain Vector Store...")
try:
    vectorstore = PineconeVectorStore(
        index_name=index_name,
        embedding=embeddings
    )
    print("✅ Vector store initialized!")
except Exception as e:
    print(f"❌ Vector store failed: {e}")

# Test write operation
print("\n5️⃣ Testing WRITE to vector store...")
try:
    test_doc = Document(
        page_content=f"TEST: Gold trading test at {datetime.now().isoformat()}. This is a connection test.",
        metadata={
            "type": "connection_test",
            "timestamp": datetime.now().isoformat(),
            "test": True
        }
    )
    vectorstore.add_documents([test_doc])
    print("✅ Successfully wrote test document to Pinecone!")
except Exception as e:
    print(f"❌ Write failed: {e}")

# Test read operation
print("\n6️⃣ Testing READ (similarity search)...")
try:
    results = vectorstore.similarity_search("gold trading test", k=3)
    print(f"✅ Search returned {len(results)} results:")
    for i, doc in enumerate(results[:3]):
        content_preview = doc.page_content[:80] + "..." if len(doc.page_content) > 80 else doc.page_content
        print(f"   {i+1}. {content_preview}")
        print(f"      Metadata: {doc.metadata}")
except Exception as e:
    print(f"❌ Read failed: {e}")

# Test pattern namespace
print("\n7️⃣ Testing patterns namespace...")
try:
    pattern_store = PineconeVectorStore(
        index_name=index_name,
        embedding=embeddings,
        namespace="patterns"
    )
    
    # Write test pattern
    pattern_doc = Document(
        page_content="TEST PATTERN: Bullish engulfing at 4320, resulted in WIN +3.50",
        metadata={
            "pattern": "bullish_engulfing",
            "outcome": "WIN",
            "pnl": 3.50,
            "test": True
        }
    )
    pattern_store.add_documents([pattern_doc])
    print("✅ Pattern namespace working!")
    
    # Read from patterns
    pattern_results = pattern_store.similarity_search("bullish engulfing", k=2)
    print(f"   Found {len(pattern_results)} patterns in namespace")
except Exception as e:
    print(f"❌ Pattern namespace failed: {e}")

print("\n" + "=" * 60)
print("📊 TEST SUMMARY")
print("=" * 60)

# Final stats
try:
    stats = pc.Index(index_name).describe_index_stats()
    print(f"Total vectors in database: {stats.total_vector_count}")
    if stats.namespaces:
        for ns, ns_stats in stats.namespaces.items():
            print(f"  - Namespace '{ns}': {ns_stats.vector_count} vectors")
except:
    pass

print("\n✅ If you see this, your vector database is connected and working!")
print("   The bot will save trades and patterns to learn from them.")
