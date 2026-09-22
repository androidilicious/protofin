import yfinance as yf
from openai import OpenAI
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print("========================================")
print("1. DATA INGESTION (Live from Yahoo Finance)")
print("========================================")

try:
    tnx = yf.Ticker("^TNX")
    current_yield = tnx.history(period="1d")['Close'].iloc[-1]
    
    spy = yf.Ticker("SPY")
    spy_hist = spy.history(period="1mo")
    spy_return = ((spy_hist['Close'].iloc[-1] / spy_hist['Close'].iloc[0]) - 1) * 100
    
    news = spy.news
    latest_headline = "Markets remain steady."
    if news and isinstance(news, list) and len(news) > 0 and isinstance(news[0], dict):
        latest_headline = news[0].get('title') or news[0].get('content', {}).get('title') or latest_headline
    
    data_payload = f"10-Year Treasury Yield is {current_yield:.2f}%. S&P 500 (SPY) 1-Month Return is {spy_return:.2f}%. Latest headline: '{latest_headline}'."
    
    print(f"Data Payload for LLM: \n{data_payload}\n")
    
except Exception as e:
    print(f"Failed to get live data: {e}")
    exit(1)

print("========================================")
print("2. AI CIO REASONING (Live from OpenAI)")
print("========================================")

api_key = os.getenv("OPENAI_API_KEY")
if not api_key or api_key == "YOUR_API_KEY_HERE":
    print("Error: Missing OPENAI_API_KEY in .env file.")
    exit(1)

try:
    client = OpenAI(api_key=api_key)
    prompt = f"""
    You are a macro portfolio manager. Evaluate this live data:
    {data_payload}
    
    Output a 3-sentence rationale.
    Then output:
    SPY_Score: [1-10]
    TLT_Score: [1-10]
    """
    response = client.chat.completions.create(
        model="gpt-3.5-turbo", # Falling back to 3.5 turbo to ensure it runs fast and cheap for the test
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=200
    )
    
    llm_output = response.choices[0].message.content
    print(llm_output)
    print()
    
    # Parse scores
    spy_score = 5
    tlt_score = 5
    for line in llm_output.split('\n'):
        if "SPY_Score:" in line:
            try: spy_score = int(line.split(":")[1].strip())
            except: pass
        elif "TLT_Score:" in line:
            try: tlt_score = int(line.split(":")[1].strip())
            except: pass
            
except Exception as e:
    print(f"Failed to run LLM: {e}")
    exit(1)
    
print("========================================")
print("3. PORTFOLIO ALLOCATION")
print("========================================")

total = spy_score + tlt_score
if total == 0: total = 1
spy_w = (spy_score / total) * 100
tlt_w = (tlt_score / total) * 100

print(f"Equities (SPY): {spy_w:.1f}%")
print(f"Bonds (TLT): {tlt_w:.1f}%")
print("========================================")
