import os, requests, pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from pinecone import Pinecone
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

load_dotenv()

# 1. FIXED: Custom Embeddings class to fit your 512-dim index
class TruncatedEmbeddings(OpenAIEmbeddings):
    def embed_query(self, text: str):
        return super().embed_query(text)[:512]
    def embed_documents(self, texts: list[str]):
        return [e[:512] for e in super().embed_documents(texts)]

# 2. Setup Vector Store
embeddings = TruncatedEmbeddings(model="text-embedding-3-small")
vectorstore = PineconeVectorStore(
    index_name=os.getenv("PINECONE_INDEX_NAME"),  

    embedding=embeddings
)

def get_1hour_trend():
    """Institutional Filter: Checks last 4 hours on Tiingo."""
    try:
        url = f"https://api.tiingo.com/tiingo/fx/xauusd/prices?resampleFreq=1hour&token={os.getenv('TIINGO_KEY')}"
        data = requests.get(url).json()
        df = pd.DataFrame(data)
        current, past = df['close'].iloc[-1], df['close'].iloc[-4]
        return "BULLISH" if current > past else "BEARISH"
    except Exception as e:
        print(f"⚠️ Trend Error: {e}")
        return "NEUTRAL"

def save_trade(trade_id, side, entry, pnl, reason):
    """Saves trade as a LangChain Document."""
    doc = Document(
        page_content=f"Gold {side} at {entry}. Result: {reason}. PnL: {pnl}",
        metadata={"id": str(trade_id), "side": side, "pnl": float(pnl)}
    )
    vectorstore.add_documents([doc])

def get_memory(query, k=3):
    """Retrieves similar past trades to avoid repeating mistakes."""
    docs = vectorstore.similarity_search(query, k=k)
    return "\n".join([f"- {d.page_content}" for d in docs])