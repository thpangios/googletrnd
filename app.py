from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pytrends.request import TrendReq
import time
from typing import Optional

app = FastAPI(title="Google Trends API")

# Allow n8n to call this
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize pytrends (reuse connection)
pytrends = TrendReq(hl='en-US', tz=360, timeout=(10, 25))

@app.get("/")
def home():
    return {"status": "Google Trends API is running"}

@app.get("/trends")
def get_trends(keyword: str, timeframe: str = "today 3-m", geo: str = "US"):
    """
    Get Google Trends data for a keyword
    
    Args:
        keyword: Product name/search term
        timeframe: Options: 'today 3-m', 'today 12-m', 'today 5-y'
        geo: Country code (US, GB, etc.)
    
    Returns:
        {
            "keyword": "string",
            "current_score": 0-100,
            "average_score": 0-100,
            "trend_direction": "rising|falling|stable",
            "peak_score": 0-100,
            "data_points": [...]
        }
    """
    try:
        # Build payload
        pytrends.build_payload([keyword], timeframe=timeframe, geo=geo)
        
        # Get interest over time
        interest_df = pytrends.interest_over_time()
        
        if interest_df.empty or keyword not in interest_df.columns:
            return {
                "keyword": keyword,
                "current_score": 0,
                "average_score": 0,
                "trend_direction": "no_data",
                "peak_score": 0,
                "data_points": []
            }
        
        # Extract data
        data = interest_df[keyword].tolist()
        current_score = int(data[-1]) if data else 0
        average_score = int(sum(data) / len(data)) if data else 0
        peak_score = int(max(data)) if data else 0
        
        # Determine trend direction (last 30 days vs previous 30 days)
        if len(data) >= 8:  # At least 8 weeks of data
            recent_avg = sum(data[-4:]) / 4
            previous_avg = sum(data[-8:-4]) / 4
            
            if recent_avg > previous_avg * 1.2:
                trend_direction = "rising"
            elif recent_avg < previous_avg * 0.8:
                trend_direction = "falling"
            else:
                trend_direction = "stable"
        else:
            trend_direction = "insufficient_data"
        
        # Rate limiting (Google Trends allows ~100 requests/hour)
        time.sleep(1)
        
        return {
            "keyword": keyword,
            "current_score": current_score,
            "average_score": average_score,
            "trend_direction": trend_direction,
            "peak_score": peak_score,
            "data_points": data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/trends/batch")
def get_trends_batch(keywords: str, timeframe: str = "today 3-m", geo: str = "US"):
    """
    Get trends for multiple keywords (comma-separated, max 5)
    Example: /trends/batch?keywords=dog bed,cat toy,pet feeder
    """
    keyword_list = [k.strip() for k in keywords.split(",")[:5]]  # Max 5 keywords
    results = []
    
    for keyword in keyword_list:
        result = get_trends(keyword=keyword, timeframe=timeframe, geo=geo)
        results.append(result)
        time.sleep(2)  # Rate limiting between requests
    
    return {"results": results}
