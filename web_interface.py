import json
import os
import re
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd
import yfinance as yf
from flask import Flask, jsonify, render_template, request, send_file
from openai import OpenAI

import static_util
from trading_graph import TradingGraph

app = Flask(__name__)


class WebTradingAnalyzer:
    def __init__(self):
        """Initialize the web trading analyzer."""
        from default_config import DEFAULT_CONFIG
        # Start with default config (OpenAI)
        self.config = DEFAULT_CONFIG.copy()
        self.trading_graph = TradingGraph(config=self.config)
        self.data_dir = Path("data")

        # Ensure data dir exists
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Available assets and their display names
        self.asset_mapping = {
            "SPX": "S&P 500",
            "BTC": "Bitcoin",
            "GC": "Gold Futures",
            "NQ": "Nasdaq Futures",
            "CL": "Crude Oil",
            "ES": "E-mini S&P 500",
            "DJI": "Dow Jones",
            "QQQ": "Invesco QQQ Trust",
            "VIX": "Volatility Index",
            "DXY": "US Dollar Index",
            "AAPL": "Apple Inc.",  # New asset
            "TSLA": "Tesla Inc.",  # New asset
        }

        # Yahoo Finance symbol mapping
        self.yfinance_symbols = {
            "SPX": "^GSPC",  # S&P 500
            "BTC": "BTC-USD",  # Bitcoin
            "GC": "GC=F",  # Gold Futures
            "NQ": "NQ=F",  # Nasdaq Futures
            "CL": "CL=F",  # Crude Oil
            "ES": "ES=F",  # E-mini S&P 500
            "DJI": "^DJI",  # Dow Jones
            "QQQ": "QQQ",  # Invesco QQQ Trust
            "VIX": "^VIX",  # Volatility Index
            "DXY": "DX-Y.NYB",  # US Dollar Index
        }

        # Yahoo Finance interval mapping
        self.yfinance_intervals = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1h",
            "4h": "4h",  # yfinance supports 4h natively!
            "1d": "1d",
            "1w": "1wk",
            "1mo": "1mo",
        }

        # TradingView symbol mapping
        self.tradingview_symbols = {
            "SPX": "SPX",  # S&P 500
            "BTC": "BINANCE:BTCUSDT",  # Bitcoin (using Binance for better data)
            "GC": "COMEX:GC1!",  # Gold Futures
            "NQ": "CME:NQ1!",  # Nasdaq Futures
            "CL": "NYMEX:CL1!",  # Crude Oil
            "ES": "CME:ES1!",  # E-mini S&P 500
            "DJI": "DJI",  # Dow Jones
            "QQQ": "NASDAQ:QQQ",  # Invesco QQQ Trust
            "VIX": "CBOE:VIX",  # Volatility Index
            "DXY": "TVC:DXY",  # US Dollar Index
            "AAPL": "NASDAQ:AAPL",  # Apple Inc.
            "TSLA": "NASDAQ:TSLA",  # Tesla Inc.
        }

        # TradingView timeframe mapping (in minutes)
        self.tradingview_timeframes = {
            "1m": "1",
            "5m": "5",
            "15m": "15",
            "30m": "30",
            "1h": "60",
            "4h": "240",
            "1d": "D",
            "1w": "W",
            "1mo": "M",
        }

        # Load persisted custom assets
        self.custom_assets_file = self.data_dir / "custom_assets.json"
        self.custom_assets = self.load_custom_assets()

    def fetch_yfinance_data(
        self, symbol: str, interval: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """Fetch OHLCV data from Yahoo Finance."""
        try:
            yf_symbol = self.yfinance_symbols.get(symbol, symbol)
            yf_interval = self.yfinance_intervals.get(interval, interval)

            df = yf.download(
                tickers=yf_symbol, start=start_date, end=end_date, interval=yf_interval
            )

            if df is None or df.empty:
                return pd.DataFrame()

            # Ensure df is a DataFrame, not a Series
            if isinstance(df, pd.Series):
                df = df.to_frame()

            # Reset index to ensure we have a clean DataFrame
            df = df.reset_index()

            # Ensure we have a DataFrame
            if not isinstance(df, pd.DataFrame):
                return pd.DataFrame()

            # Handle potential MultiIndex columns
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # Rename columns if needed
            column_mapping = {
                "Date": "Datetime",
                "Open": "Open",
                "High": "High",
                "Low": "Low",
                "Close": "Close",
                "Volume": "Volume",
            }

            # Only rename columns that exist
            existing_columns = {
                old: new for old, new in column_mapping.items() if old in df.columns
            }
            df = df.rename(columns=existing_columns)

            # Ensure we have the required columns
            required_columns = ["Datetime", "Open", "High", "Low", "Close"]
            if not all(col in df.columns for col in required_columns):
                print(f"Warning: Missing columns. Available: {list(df.columns)}")
                return pd.DataFrame()

            # Select only the required columns
            df = df[required_columns]
            df["Datetime"] = pd.to_datetime(df["Datetime"])

            return df

        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            return pd.DataFrame()

    def fetch_yfinance_data_with_datetime(
        self,
        symbol: str,
        interval: str,
        start_datetime: datetime,
        end_datetime: datetime,
    ) -> pd.DataFrame:
        """Fetch OHLCV data from Yahoo Finance using datetime objects for exact time precision."""
        try:
            yf_symbol = self.yfinance_symbols.get(symbol, symbol)
            yf_interval = self.yfinance_intervals.get(interval, interval)

            print(
                f"Fetching {yf_symbol} from {start_datetime} to {end_datetime} with interval {yf_interval}"
            )

            # Use datetime objects directly for yfinance
            df = yf.download(
                tickers=yf_symbol,
                start=start_datetime,
                end=end_datetime,
                interval=yf_interval,
                auto_adjust=True,
                prepost=False,
            )

            if df is None or df.empty:
                print(f"No data returned for {symbol}")
                return pd.DataFrame()

            # Ensure df is a DataFrame, not a Series
            if isinstance(df, pd.Series):
                df = df.to_frame()

            # Reset index to ensure we have a clean DataFrame
            df = df.reset_index()

            # Ensure we have a DataFrame
            if not isinstance(df, pd.DataFrame):
                return pd.DataFrame()

            # Handle potential MultiIndex columns
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # Rename columns if needed
            column_mapping = {
                "Date": "Datetime",
                "Open": "Open",
                "High": "High",
                "Low": "Low",
                "Close": "Close",
                "Volume": "Volume",
            }

            # Only rename columns that exist
            existing_columns = {
                old: new for old, new in column_mapping.items() if old in df.columns
            }
            df = df.rename(columns=existing_columns)

            # Ensure we have the required columns
            required_columns = ["Datetime", "Open", "High", "Low", "Close"]
            if not all(col in df.columns for col in required_columns):
                print(f"Warning: Missing columns. Available: {list(df.columns)}")
                return pd.DataFrame()

            # Select only the required columns
            df = df[required_columns]
            df["Datetime"] = pd.to_datetime(df["Datetime"])

            print(f"Successfully fetched {len(df)} data points for {symbol}")
            print(f"Date range: {df['Datetime'].min()} to {df['Datetime'].max()}")

            return df

        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            return pd.DataFrame()

    def get_available_assets(self) -> list:
        """Get list of available assets from the asset mapping dictionary."""
        return sorted(list(self.asset_mapping.keys()))

    def get_available_files(self, asset: str, timeframe: str) -> list:
        """Get available data files for a specific asset and timeframe."""
        asset_dir = self.data_dir / asset.lower()
        if not asset_dir.exists():
            return []

        pattern = f"{asset}_{timeframe}_*.csv"
        files = list(asset_dir.glob(pattern))
        return sorted(files)

    def convert_to_tradingview_format(self, df: pd.DataFrame) -> list:
        """
        Convert pandas DataFrame to TradingView-compatible format.
        Returns list of [timestamp_ms, open, high, low, close, volume] arrays.
        """
        if df.empty:
            return []
        
        # Ensure Datetime column exists and is datetime type
        if "Datetime" not in df.columns:
            return []
        
        df_copy = df.copy()
        df_copy["Datetime"] = pd.to_datetime(df_copy["Datetime"])
        
        # Convert to Unix timestamp in milliseconds
        timestamps = (df_copy["Datetime"].astype("int64") // 10**6).tolist()
        
        # Build TradingView data format: [timestamp, open, high, low, close, volume]
        tradingview_data = []
        for i, (idx, row) in enumerate(df_copy.iterrows()):
            volume = float(row.get("Volume", 0)) if "Volume" in df_copy.columns else 0
            tradingview_data.append([
                timestamps[i],
                float(row["Open"]),
                float(row["High"]),
                float(row["Low"]),
                float(row["Close"]),
                volume
            ])
        
        return tradingview_data

    def extract_support_resistance_lines(self, df: pd.DataFrame) -> Dict[str, list]:
        """
        Extract support and resistance lines from DataFrame for TradingView overlay.
        Returns dict with 'support' and 'resistance' arrays of [timestamp, price] pairs.
        """
        try:
            from graph_util import fit_trendlines_high_low, fit_trendlines_single, get_line_points
            
            if df.empty or len(df) < 10:
                return {"support": [], "resistance": []}
            
            df_copy = df.copy()
            df_copy["Datetime"] = pd.to_datetime(df_copy["Datetime"])
            df_copy.set_index("Datetime", inplace=True)
            
            # Use last 50 candles for trendline calculation
            candles = df_copy.tail(50).copy()
            
            # Calculate trendlines
            support_coefs_c, resist_coefs_c = fit_trendlines_single(candles["Close"])
            support_coefs, resist_coefs = fit_trendlines_high_low(
                candles["High"], candles["Low"], candles["Close"]
            )
            
            # Generate line points
            support_line_c = support_coefs_c[0] * np.arange(len(candles)) + support_coefs_c[1]
            resist_line_c = resist_coefs_c[0] * np.arange(len(candles)) + resist_coefs_c[1]
            
            # Convert to timestamp-price pairs
            timestamps = (candles.index.astype("int64") // 10**6).tolist()
            
            support_points = [[int(ts), float(price)] for ts, price in zip(timestamps, support_line_c)]
            resistance_points = [[int(ts), float(price)] for ts, price in zip(timestamps, resist_line_c)]
            
            return {
                "support": support_points,
                "resistance": resistance_points
            }
        except Exception as e:
            print(f"Error extracting support/resistance lines: {e}")
            return {"support": [], "resistance": []}

    def run_analysis(
        self, df: pd.DataFrame, asset_name: str, timeframe: str
    ) -> Dict[str, Any]:
        """Run the trading analysis on the provided DataFrame."""
        try:
            # Debug: Check DataFrame structure
            print(f"DataFrame columns: {df.columns}")
            print(f"DataFrame index: {type(df.index)}")
            print(f"DataFrame shape: {df.shape}")

            # Prepare data for analysis
            if len(df) > 49:
                df_slice = df.tail(49).iloc[:-3]
            else:
                df_slice = df.tail(45)

            # Ensure DataFrame has the expected structure
            required_columns = ["Datetime", "Open", "High", "Low", "Close"]
            if not all(col in df_slice.columns for col in required_columns):
                return {
                    "success": False,
                    "error": f"Missing required columns. Available: {list(df_slice.columns)}",
                }

            # Reset index to avoid any MultiIndex issues
            df_slice = df_slice.reset_index(drop=True)

            # Derive basic price/time info for the most recent candle
            current_price = None
            last_timestamp_str = None
            last_timestamp_utc3_str = None
            if not df_slice.empty:
                last_row = df_slice.iloc[-1]
                try:
                    current_price = float(last_row["Close"])
                except Exception:
                    current_price = None

                try:
                    last_dt = pd.to_datetime(last_row["Datetime"])
                    last_timestamp_str = last_dt.strftime("%Y-%m-%d %H:%M:%S")
                    # Assume source timestamps are effectively UTC and convert to UTC+3 for display
                    last_dt_utc3 = last_dt + timedelta(hours=3)
                    last_timestamp_utc3_str = last_dt_utc3.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    last_timestamp_str = None
                    last_timestamp_utc3_str = None

            # Debug: Check the slice before conversion
            print(f"Slice columns: {df_slice.columns}")
            print(f"Slice index: {type(df_slice.index)}")

            # Convert to dict for tool input - use explicit conversion to avoid tuple keys
            df_slice_dict = {}
            for col in required_columns:
                if col == "Datetime":
                    # Convert datetime objects to strings for JSON serialization
                    df_slice_dict[col] = (
                        df_slice[col].dt.strftime("%Y-%m-%d %H:%M:%S").tolist()
                    )
                else:
                    df_slice_dict[col] = df_slice[col].tolist()

            # Debug: Check the resulting dictionary
            print(f"Dictionary keys: {list(df_slice_dict.keys())}")
            print(f"Dictionary key types: {[type(k) for k in df_slice_dict.keys()]}")

            # Format timeframe for display
            display_timeframe = timeframe
            if timeframe.endswith("h"):
                display_timeframe += "our"
            elif timeframe.endswith("m"):
                display_timeframe += "in"
            elif timeframe.endswith("d"):
                display_timeframe += "ay"
            elif timeframe == "1w":
                display_timeframe = "1 week"
            elif timeframe == "1mo":
                display_timeframe = "1 month"

            p_image = static_util.generate_kline_image(df_slice_dict)
            t_image = static_util.generate_trend_image(df_slice_dict)

            # Create initial state
            initial_state = {
                "kline_data": df_slice_dict,
                "analysis_results": None,
                "messages": [],
                "time_frame": display_timeframe,
                "stock_name": asset_name,
                "pattern_image": p_image["pattern_image"],
                "trend_image": t_image["trend_image"],
            }

            # Run the trading graph
            final_state = self.trading_graph.graph.invoke(initial_state)

            # Derive a simple, heuristic confidence score for the signal
            indicator_text = (final_state.get("indicator_report", "") or "").strip()
            pattern_text = (final_state.get("pattern_report", "") or "").strip()
            trend_text = (final_state.get("trend_report", "") or "").strip()
            non_empty_sections = sum(
                1 for section in [indicator_text, pattern_text, trend_text] if section
            )

            if len(df_slice) < 20 or non_empty_sections <= 1:
                signal_confidence = "Low"
            elif len(df_slice) < 40 or non_empty_sections == 2:
                signal_confidence = "Medium"
            else:
                signal_confidence = "High"

            # Convert to TradingView format for chart display
            tradingview_data = self.convert_to_tradingview_format(df_slice)
            support_resistance = self.extract_support_resistance_lines(df_slice)

            return {
                "success": True,
                "final_state": final_state,
                "asset_name": asset_name,
                "timeframe": display_timeframe,
                "data_length": len(df_slice),
                "current_price": current_price,
                "last_timestamp": last_timestamp_str,
                "last_timestamp_utc3": last_timestamp_utc3_str,
                "signal_confidence": signal_confidence,
                "tradingview_data": tradingview_data,
                "support_resistance": support_resistance,
                "raw_df": df_slice,  # Keep raw DataFrame for API endpoint
            }

        except Exception as e:
            error_msg = str(e)
            
            # Get current provider from config
            provider = self.config.get("agent_llm_provider", "openai")
            if provider == "openai":
                provider_name = "OpenAI"
            elif provider == "anthropic":
                provider_name = "Anthropic"
            else:
                provider_name = "Qwen"

            # Check for specific API key authentication errors
            if (
                "authentication" in error_msg.lower()
                or "invalid api key" in error_msg.lower()
                or "401" in error_msg
                or "invalid_api_key" in error_msg.lower()
            ):
                return {
                    "success": False,
                    "error": f"❌ Invalid API Key: The {provider_name} API key you provided is invalid or has expired. Please check your API key in the Settings section and try again.",
                }
            elif "rate limit" in error_msg.lower() or "429" in error_msg:
                return {
                    "success": False,
                    "error": f"⚠️ Rate Limit Exceeded: You've hit the {provider_name} API rate limit. Please wait a moment and try again.",
                }
            elif "quota" in error_msg.lower() or "billing" in error_msg.lower():
                return {
                    "success": False,
                    "error": f"💳 Billing Issue: Your {provider_name} account has insufficient credits or billing issues. Please check your {provider_name} account.",
                }
            elif "network" in error_msg.lower() or "connection" in error_msg.lower():
                return {
                    "success": False,
                    "error": f"🌐 Network Error: Unable to connect to {provider_name} servers. Please check your internet connection and try again.",
                }
            else:
                return {"success": False, "error": f"❌ Analysis Error: {error_msg}"}

    def extract_analysis_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and format analysis results for web display."""
        if not results["success"]:
            return {"error": results["error"]}

        final_state = results["final_state"]

        # Extract analysis results from state fields
        technical_indicators = final_state.get("indicator_report", "")
        pattern_analysis = final_state.get("pattern_report", "")
        trend_analysis = final_state.get("trend_report", "")
        final_decision_raw = final_state.get("final_trade_decision", "")

        # Extract chart data if available
        pattern_chart = final_state.get("pattern_image", "")
        trend_chart = final_state.get("trend_image", "")
        pattern_image_filename = final_state.get("pattern_image_filename", "")
        trend_image_filename = final_state.get("trend_image_filename", "")

        # Parse final decision
        final_decision = ""
        if final_decision_raw:
            try:
                # Try to extract JSON from the decision
                start = final_decision_raw.find("{")
                end = final_decision_raw.rfind("}") + 1
                if start != -1 and end != 0:
                    json_str = final_decision_raw[start:end]
                    decision_data = json.loads(json_str)
                    final_decision = {
                        "decision": decision_data.get("decision", "N/A"),
                        "risk_reward_ratio": decision_data.get(
                            "risk_reward_ratio", "N/A"
                        ),
                        "forecast_horizon": decision_data.get(
                            "forecast_horizon", "N/A"
                        ),
                        "justification": decision_data.get("justification", "N/A"),
                    }
                else:
                    # If no JSON found, return the raw text
                    final_decision = {"raw": final_decision_raw}
            except json.JSONDecodeError:
                # If JSON parsing fails, return the raw text
                final_decision = {"raw": final_decision_raw}

        # Get TradingView data and symbol mapping
        tradingview_data = results.get("tradingview_data", [])
        support_resistance = results.get("support_resistance", {"support": [], "resistance": []})
        asset_code = results.get("asset_name", "")
        
        # Map asset to TradingView symbol
        tradingview_symbol = self.tradingview_symbols.get(asset_code, asset_code)
        if asset_code not in self.tradingview_symbols and asset_code in self.custom_assets:
            # For custom assets, try to use the symbol directly or add exchange prefix
            tradingview_symbol = asset_code
        
        return {
            "success": True,
            "asset_name": results["asset_name"],
            "timeframe": results["timeframe"],
            "data_length": results["data_length"],
            "technical_indicators": technical_indicators,
            "pattern_analysis": pattern_analysis,
            "trend_analysis": trend_analysis,
            "pattern_chart": pattern_chart,
            "trend_chart": trend_chart,
            "pattern_image_filename": pattern_image_filename,
            "trend_image_filename": trend_image_filename,
            "final_decision": final_decision,
            # Enriched metadata for UI
            "current_price": results.get("current_price"),
            "last_timestamp": results.get("last_timestamp"),
            "last_timestamp_utc3": results.get("last_timestamp_utc3"),
            "signal_confidence": results.get("signal_confidence"),
            # TradingView data
            "tradingview_data": tradingview_data,
            "tradingview_symbol": tradingview_symbol,
            "support_lines": support_resistance.get("support", []),
            "resistance_lines": support_resistance.get("resistance", []),
        }

    def get_timeframe_date_limits(self, timeframe: str) -> Dict[str, Any]:
        """Get valid date range limits for a given timeframe."""
        limits = {
            "1m": {"max_days": 7, "description": "1 minute data: max 7 days"},
            "2m": {"max_days": 60, "description": "2 minute data: max 60 days"},
            "5m": {"max_days": 60, "description": "5 minute data: max 60 days"},
            "15m": {"max_days": 60, "description": "15 minute data: max 60 days"},
            "30m": {"max_days": 60, "description": "30 minute data: max 60 days"},
            "60m": {"max_days": 730, "description": "1 hour data: max 730 days"},
            "90m": {"max_days": 60, "description": "90 minute data: max 60 days"},
            "1h": {"max_days": 730, "description": "1 hour data: max 730 days"},
            "4h": {"max_days": 730, "description": "4 hour data: max 730 days"},
            "1d": {"max_days": 730, "description": "1 day data: max 730 days"},
            "5d": {"max_days": 60, "description": "5 day data: max 60 days"},
            "1w": {"max_days": 730, "description": "1 week data: max 730 days"},
            "1wk": {"max_days": 730, "description": "1 week data: max 730 days"},
            "1mo": {"max_days": 730, "description": "1 month data: max 730 days"},
            "3mo": {"max_days": 730, "description": "3 month data: max 730 days"},
        }

        return limits.get(
            timeframe, {"max_days": 730, "description": "Default: max 730 days"}
        )

    def validate_date_range(
        self,
        start_date: str,
        end_date: str,
        timeframe: str,
        start_time: str = "00:00",
        end_time: str = "23:59",
    ) -> Dict[str, Any]:
        """Validate date and time range for the given timeframe."""
        try:
            # Create datetime objects with time
            start_datetime_str = f"{start_date} {start_time}"
            end_datetime_str = f"{end_date} {end_time}"

            start = datetime.strptime(start_datetime_str, "%Y-%m-%d %H:%M")
            end = datetime.strptime(end_datetime_str, "%Y-%m-%d %H:%M")

            if start >= end:
                return {
                    "valid": False,
                    "error": "Start date/time must be before end date/time",
                }

            # Get timeframe limits
            limits = self.get_timeframe_date_limits(timeframe)
            max_days = limits["max_days"]

            # Calculate time difference in days (including fractional days)
            time_diff = end - start
            days_diff = time_diff.total_seconds() / (24 * 3600)  # Convert to days

            if days_diff > max_days:
                return {
                    "valid": False,
                    "error": f"Time range too large. {limits['description']}. Please select a smaller range.",
                    "max_days": max_days,
                    "current_days": round(days_diff, 2),
                }

            return {"valid": True, "days": round(days_diff, 2)}

        except ValueError as e:
            return {"valid": False, "error": f"Invalid date/time format: {str(e)}"}

    def validate_api_key(self, provider: str = None) -> Dict[str, Any]:
        """Validate the current API key by making a simple test call."""
        try:
            # Get provider from config if not provided
            if provider is None:
                provider = self.config.get("agent_llm_provider", "openai")
            
            if provider == "openai":
                from openai import OpenAI
                client = OpenAI()
                
                # Make a simple test call
                _ = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": "Hello"}],
                    max_tokens=5,
                )
                
                provider_name = "OpenAI"
            elif provider == "anthropic":
                from anthropic import Anthropic
                api_key = os.environ.get("ANTHROPIC_API_KEY") or self.config.get("anthropic_api_key", "")
                if not api_key:
                    return {
                        "valid": False,
                        "error": "❌ Invalid API Key: The Anthropic API key is not set. Please update it in the Settings section.",
                    }
                
                client = Anthropic(api_key=api_key)
                
                # Make a simple test call
                _ = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=5,
                    messages=[{"role": "user", "content": "Hello"}],
                )
                
                provider_name = "Anthropic"
            else:  # qwen
                from langchain_qwq import ChatQwen
                api_key = os.environ.get("DASHSCOPE_API_KEY") or self.config.get("qwen_api_key", "")
                if not api_key:
                    return {
                        "valid": False,
                        "error": "❌ Invalid API Key: The Qwen API key is not set. Please update it in the Settings section.",
                    }
                
                # Make a simple test call using LangChain
                llm = ChatQwen(model="qwen-flash", api_key=api_key)
                _ = llm.invoke([("user", "Hello")])
                
                provider_name = "Qwen"
            return {"valid": True, "message": f"{provider_name} API key is valid"}

        except Exception as e:
            error_msg = str(e)
            
            # Determine provider name for error messages
            if provider is None:
                provider = self.config.get("agent_llm_provider", "openai")
            if provider == "openai":
                provider_name = "OpenAI"
            elif provider == "anthropic":
                provider_name = "Anthropic"
            else:
                provider_name = "Qwen"

            if (
                "authentication" in error_msg.lower()
                or "invalid api key" in error_msg.lower()
                or "401" in error_msg
                or "invalid_api_key" in error_msg.lower()
            ):
                return {
                    "valid": False,
                    "error": f"❌ Invalid API Key: The {provider_name} API key is invalid or has expired. Please update it in the Settings section.",
                }
            elif "rate limit" in error_msg.lower() or "429" in error_msg:
                return {
                    "valid": False,
                    "error": f"⚠️ Rate Limit Exceeded: You've hit the {provider_name} API rate limit. Please wait a moment and try again.",
                }
            elif "quota" in error_msg.lower() or "billing" in error_msg.lower():
                return {
                    "valid": False,
                    "error": f"💳 Billing Issue: Your {provider_name} account has insufficient credits or billing issues. Please check your {provider_name} account.",
                }
            elif "network" in error_msg.lower() or "connection" in error_msg.lower():
                return {
                    "valid": False,
                    "error": f"🌐 Network Error: Unable to connect to {provider_name} servers. Please check your internet connection.",
                }
            else:
                return {"valid": False, "error": f"❌ API Key Error: {error_msg}"}

    def load_custom_assets(self) -> list:
        """Load custom assets from persistent JSON file."""
        try:
            if self.custom_assets_file.exists():
                with open(self.custom_assets_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            return []
        except Exception as e:
            print(f"Error loading custom assets: {e}")
            return []

    def save_custom_asset(self, symbol: str) -> bool:
        """Save a custom asset symbol persistently (avoid duplicates)."""
        try:
            symbol = symbol.strip()
            if not symbol:
                return False
            if symbol in self.custom_assets:
                return True  # already present
            self.custom_assets.append(symbol)
            # write to file
            with open(self.custom_assets_file, "w", encoding="utf-8") as f:
                json.dump(self.custom_assets, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving custom asset '{symbol}': {e}")
            return False


# Initialize the analyzer
analyzer = WebTradingAnalyzer()


@app.route("/")
def index():
    """Main landing page - redirect to demo."""
    return render_template("demo_new.html")


@app.route("/demo")
def demo():
    """Demo page with new interface."""
    return render_template("demo_new.html")


@app.route("/output")
def output():
    """Output page with analysis results."""
    # Get results from session or query parameters
    results = request.args.get("results")
    if results:
        try:
            # Handle URL-encoded results
            results = urllib.parse.unquote(results)
            results_data = json.loads(results)
            return render_template("output.html", results=results_data)
        except (json.JSONDecodeError, Exception) as e:
            print(f"Error parsing results: {e}")
            # Fall back to default results

    # Default results if none provided
    default_results = {
        "asset_name": "BTC",
        "timeframe": "1h",
        "data_length": 1247,
        "technical_indicators": "RSI (14): 65.4 - Neutral to bullish momentum\nMACD: Bullish crossover with increasing histogram\nMoving Averages: Price above 50-day and 200-day MA\nBollinger Bands: Price in upper band, showing strength\nVolume: Above average volume supporting price action",
        "pattern_analysis": "Bull Flag Pattern: Consolidation after strong upward move\nGolden Cross: 50-day MA crossing above 200-day MA\nHigher Highs & Higher Lows: Uptrend confirmation\nVolume Pattern: Increasing volume on price advances",
        "trend_analysis": "Primary Trend: Bullish (Long-term)\nSecondary Trend: Bullish (Medium-term)\nShort-term Trend: Consolidating with bullish bias\nADX: 28.5 - Moderate trend strength\nPrice Action: Higher highs and higher lows maintained\nMomentum: Positive divergence on RSI",
        "pattern_chart": "",
        "trend_chart": "",
        "pattern_image_filename": "",
        "trend_image_filename": "",
        "final_decision": {
            "decision": "LONG",
            "risk_reward_ratio": "1:2.5",
            "forecast_horizon": "24-48 hours",
            "justification": "Based on comprehensive analysis of technical indicators, pattern recognition, and trend analysis, the system recommends a LONG position on BTC. The analysis shows strong bullish momentum with key support levels holding, and multiple technical indicators confirming upward movement.",
        },
    }

    return render_template("output.html", results=default_results)


@app.route("/api/analyze", methods=["POST"])
def analyze():
    try:
        data = request.get_json()
        data_source = data.get("data_source")
        asset = data.get("asset")
        timeframe = data.get("timeframe")
        redirect_to_output = data.get("redirect_to_output", False)

        if data_source != "live":
            return jsonify({"error": "Only live Yahoo Finance data is supported."})

        # Live Yahoo Finance data only
        start_date = data.get("start_date")
        start_time = data.get("start_time", "00:00")
        end_date = data.get("end_date")
        end_time = data.get("end_time", "23:59")
        use_current_time = data.get("use_current_time", False)

        # Create datetime objects for validation
        if start_date:
            start_datetime_str = f"{start_date} {start_time}"
            try:
                start_dt = datetime.strptime(start_datetime_str, "%Y-%m-%d %H:%M")
            except ValueError:
                return jsonify({"error": "Invalid start date/time format."})

            if start_dt > datetime.now():
                return jsonify({"error": "Start date/time cannot be in the future."})

        if end_date:
            if use_current_time:
                end_dt = datetime.now()
            else:
                end_datetime_str = f"{end_date} {end_time}"
                try:
                    end_dt = datetime.strptime(end_datetime_str, "%Y-%m-%d %H:%M")
                except ValueError:
                    return jsonify({"error": "Invalid end date/time format."})

                if end_dt > datetime.now():
                    return jsonify({"error": "End date/time cannot be in the future."})

            if start_date and start_dt and end_dt and end_dt < start_dt:
                return jsonify(
                    {"error": "End date/time cannot be earlier than start date/time."}
                )

        # Fetch data with datetime objects
        df = analyzer.fetch_yfinance_data_with_datetime(
            asset, timeframe, start_dt, end_dt
        )
        if df.empty:
            return jsonify({"error": "No data available for the specified parameters"})

        display_name = analyzer.asset_mapping.get(asset, asset)
        if display_name is None:
            display_name = asset
        results = analyzer.run_analysis(df, display_name, timeframe)
        formatted_results = analyzer.extract_analysis_results(results)

        # If redirect is requested, return redirect URL with results
        if redirect_to_output:
            if formatted_results.get("success", False):
                # Create a version without base64 images for URL encoding
                # Base64 images are too large for URL parameters
                url_safe_results = formatted_results.copy()
                url_safe_results["pattern_chart"] = ""  # Remove base64 data
                url_safe_results["trend_chart"] = ""  # Remove base64 data

                # Encode results for URL
                results_json = json.dumps(url_safe_results)
                encoded_results = urllib.parse.quote(results_json)
                redirect_url = f"/output?results={encoded_results}"

                # Store full results (with images) in session or temporary storage
                # For now, we'll pass them back in the response for the frontend to handle
                return jsonify(
                    {
                        "redirect": redirect_url,
                        "full_results": formatted_results,  # Include images in response body
                    }
                )
            else:
                return jsonify(
                    {"error": formatted_results.get("error", "Analysis failed")}
                )

        return jsonify(formatted_results)
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/files/<asset>/<timeframe>")
def get_files(asset, timeframe):
    """API endpoint to get available files for an asset/timeframe."""
    try:
        files = analyzer.get_available_files(asset, timeframe)
        file_list = []

        for i, file_path in enumerate(files):
            match = re.search(r"_(\d+)\.csv$", file_path.name)
            file_number = match.group(1) if match else "N/A"
            file_list.append(
                {"index": i, "number": file_number, "name": file_path.name}
            )

        return jsonify({"files": file_list})

    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/save-custom-asset", methods=["POST"])
def save_custom_asset():
    """Save a custom asset symbol server-side for persistence."""
    try:
        data = request.get_json()
        symbol = (data.get("symbol") or "").strip()
        if not symbol:
            return jsonify({"success": False, "error": "Symbol required"}), 400

        ok = analyzer.save_custom_asset(symbol)
        if not ok:
            return jsonify({"success": False, "error": "Failed to save symbol"}), 500

        return jsonify({"success": True, "symbol": symbol})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/custom-assets", methods=["GET"])
def custom_assets():
    """Return server-persisted custom assets."""
    try:
        return jsonify({"custom_assets": analyzer.custom_assets or []})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/assets")
def get_assets():
    """API endpoint to get available assets."""
    try:
        assets = analyzer.get_available_assets()
        asset_list = []

        for asset in assets:
            asset_list.append(
                {"code": asset, "name": analyzer.asset_mapping.get(asset, asset)}
            )

        # Include server-persisted custom assets at the end
        for custom in analyzer.custom_assets:
            asset_list.append({"code": custom, "name": custom})

        return jsonify({"assets": asset_list})

    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/timeframe-limits/<timeframe>")
def get_timeframe_limits(timeframe):
    """API endpoint to get date range limits for a timeframe."""
    try:
        limits = analyzer.get_timeframe_date_limits(timeframe)
        return jsonify(limits)
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/validate-date-range", methods=["POST"])
def validate_date_range():
    """API endpoint to validate date and time range for a timeframe."""
    try:
        data = request.get_json()
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        timeframe = data.get("timeframe")
        start_time = data.get("start_time", "00:00")
        end_time = data.get("end_time", "23:59")

        if not all([start_date, end_date, timeframe]):
            return jsonify({"error": "Missing required parameters"})

        validation = analyzer.validate_date_range(
            start_date, end_date, timeframe, start_time, end_time
        )
        return jsonify(validation)

    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/update-provider", methods=["POST"])
def update_provider():
    """API endpoint to update LLM provider."""
    try:
        data = request.get_json()
        provider = data.get("provider", "openai")

        if provider not in ["openai", "anthropic", "qwen"]:
            return jsonify({"error": "Provider must be 'openai', 'anthropic', or 'qwen'"})

        print(f"Updating provider to: {provider}")

        # Update config in both analyzer and trading_graph
        analyzer.config["agent_llm_provider"] = provider
        analyzer.config["graph_llm_provider"] = provider
        analyzer.trading_graph.config["agent_llm_provider"] = provider
        analyzer.trading_graph.config["graph_llm_provider"] = provider
        
        # Update model names if switching providers
        if provider == "anthropic":
            # Set default Claude models if not already set to Anthropic models
            if not analyzer.config["agent_llm_model"].startswith("claude"):
                analyzer.config["agent_llm_model"] = "claude-haiku-4-5-20251001"
            if not analyzer.config["graph_llm_model"].startswith("claude"):
                analyzer.config["graph_llm_model"] = "claude-haiku-4-5-20251001"
        elif provider == "qwen":
            # Set default Qwen models if not already set to Qwen models
            if not analyzer.config["agent_llm_model"].startswith("qwen"):
                analyzer.config["agent_llm_model"] = "qwen3-max"
            if not analyzer.config["graph_llm_model"].startswith("qwen"):
                analyzer.config["graph_llm_model"] = "qwen3-vl-plus"
            
        else:
            # Set default OpenAI models if not already set to OpenAI models
            if analyzer.config["agent_llm_model"].startswith(("claude", "qwen")):
                analyzer.config["agent_llm_model"] = "gpt-4o-mini"
            if analyzer.config["graph_llm_model"].startswith(("claude", "qwen")):
                analyzer.config["graph_llm_model"] = "gpt-4o"
        
        analyzer.trading_graph.config.update(analyzer.config)

        # Refresh the trading graph with new provider
        analyzer.trading_graph.refresh_llms()

        print(f"Provider updated to {provider} successfully")
        print(f"graph_llm_model updated to {analyzer.config['graph_llm_model']} successfully")
        print(f"agent_llm updated to {analyzer.config['agent_llm_model']} successfully")
        return jsonify({"success": True, "message": f"Provider updated to {provider}"})

    except Exception as e:
        print(f"Error in update_provider: {str(e)}")
        return jsonify({"error": str(e)})


@app.route("/api/update-api-key", methods=["POST"])
def update_api_key():
    """API endpoint to update API key for OpenAI or Anthropic."""
    try:
        data = request.get_json()
        new_api_key = data.get("api_key")
        provider = data.get("provider", "openai")  # Default to "openai" for backward compatibility

        if not new_api_key:
            return jsonify({"error": "API key is required"})

        if provider not in ["openai", "anthropic", "qwen"]:
            return jsonify({"error": "Provider must be 'openai', 'anthropic', or 'qwen'"})

        print(f"Updating {provider} API key to: {new_api_key[:8]}...{new_api_key[-4:]}")

        # Update the environment variable
        if provider == "openai":
            os.environ["OPENAI_API_KEY"] = new_api_key
        elif provider == "anthropic":
            os.environ["ANTHROPIC_API_KEY"] = new_api_key
        elif provider == "qwen":
            os.environ["DASHSCOPE_API_KEY"] = new_api_key

        # Update the API key in the trading graph
        analyzer.trading_graph.update_api_key(new_api_key, provider=provider)

        print(f"{provider} API key updated successfully")
        return jsonify({"success": True, "message": f"{provider.capitalize()} API key updated successfully"})

    except Exception as e:
        print(f"Error in update_api_key: {str(e)}")
        return jsonify({"error": str(e)})


@app.route("/api/get-api-key-status")
def get_api_key_status():
    """API endpoint to check if API key is set for a provider."""
    try:
        provider = request.args.get("provider", "openai")
        
        # First check environment variables
        if provider == "openai":
            api_key = os.environ.get("OPENAI_API_KEY", "")
            # Fallback to config if not in environment
            if not api_key and hasattr(analyzer, 'config'):
                api_key = analyzer.config.get("api_key", "")
        elif provider == "anthropic":
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            # Fallback to config if not in environment
            if not api_key and hasattr(analyzer, 'config'):
                api_key = analyzer.config.get("anthropic_api_key", "")
        elif provider == "qwen":
            api_key = os.environ.get("DASHSCOPE_API_KEY", "")
            # Fallback to config if not in environment
            if not api_key and hasattr(analyzer, 'config'):
                api_key = analyzer.config.get("qwen_api_key", "")
        else:
            api_key = ""
        
        if api_key and api_key != "your-openai-api-key-here" and api_key != "":
            # Return masked version for security
            masked_key = (
                api_key[:3] + "..." + api_key[-3:] if len(api_key) > 12 else "***"
            )
            return jsonify({"has_key": True, "masked_key": masked_key})
        else:
            return jsonify({"has_key": False})
    except Exception as e:
        print(f"Error in get_api_key_status: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e), "has_key": False})


@app.route("/api/images/<image_type>")
def get_image(image_type):
    """API endpoint to serve generated images."""
    try:
        if image_type == "pattern":
            image_path = "kline_chart.png"
        elif image_type == "trend":
            image_path = "trend_graph.png"
        elif image_type == "pattern_chart":
            image_path = "pattern_chart.png"
        elif image_type == "trend_chart":
            image_path = "trend_chart.png"
        else:
            return jsonify({"error": "Invalid image type"})

        if not os.path.exists(image_path):
            return jsonify({"error": "Image not found"})

        return send_file(image_path, mimetype="image/png")

    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/validate-api-key", methods=["POST"])
def validate_api_key():
    """API endpoint to validate the current API key."""
    try:
        data = request.get_json() or {}
        provider = data.get("provider") or analyzer.config.get("agent_llm_provider", "openai")
        validation = analyzer.validate_api_key(provider=provider)
        return jsonify(validation)
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)})


@app.route("/api/tradingview-data", methods=["GET"])
def get_tradingview_data():
    """API endpoint to get OHLCV data in TradingView format."""
    try:
        asset = request.args.get("asset")
        timeframe = request.args.get("timeframe")
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        use_current_time = request.args.get("use_current_time", "false").lower() == "true"
        
        if not all([asset, timeframe, start_date, end_date]):
            return jsonify({"error": "Missing required parameters: asset, timeframe, start_date, end_date"}), 400
        
        # Create datetime objects
        start_datetime_str = f"{start_date} 00:00"
        try:
            start_dt = datetime.strptime(start_datetime_str, "%Y-%m-%d %H:%M")
        except ValueError:
            return jsonify({"error": "Invalid start date format"}), 400
        
        if use_current_time:
            end_dt = datetime.now()
        else:
            end_datetime_str = f"{end_date} 23:59"
            try:
                end_dt = datetime.strptime(end_datetime_str, "%Y-%m-%d %H:%M")
            except ValueError:
                return jsonify({"error": "Invalid end date format"}), 400
        
        # Fetch data
        df = analyzer.fetch_yfinance_data_with_datetime(asset, timeframe, start_dt, end_dt)
        if df.empty:
            return jsonify({"error": "No data available"}), 404
        
        # Convert to TradingView format
        tradingview_data = analyzer.convert_to_tradingview_format(df)
        support_resistance = analyzer.extract_support_resistance_lines(df)
        
        # Get TradingView symbol
        tradingview_symbol = analyzer.tradingview_symbols.get(asset, asset)
        tv_timeframe = analyzer.tradingview_timeframes.get(timeframe, timeframe)
        
        return jsonify({
            "symbol": tradingview_symbol,
            "timeframe": tv_timeframe,
            "data": tradingview_data,
            "support_lines": support_resistance.get("support", []),
            "resistance_lines": support_resistance.get("resistance", []),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/assets/<path:filename>")
def serve_assets(filename):
    """Serve static assets from the assets folder."""
    try:
        return send_file(f"assets/{filename}")
    except FileNotFoundError:
        return jsonify({"error": "Asset not found"}), 404


if __name__ == "__main__":
    # Create templates directory if it doesn't exist
    templates_dir = Path("templates")
    templates_dir.mkdir(exist_ok=True)

    # Create static directory if it doesn't exist
    static_dir = Path("static")
    static_dir.mkdir(exist_ok=True)

    app.run(debug=True, host="127.0.0.1", port=5000)
