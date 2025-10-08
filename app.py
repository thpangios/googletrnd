from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pytrends.request import TrendReq
import time
import random
from typing import Optional
from datetime import datetime, timedelta
import asyncio

app = FastAPI(title="Google Trends API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting: Track last request time
last_request_time = datetime.now()
request_count = 0
REQUESTS_PER_HOUR = 80  # Conservative limit

def rate_limit_check():
    global last_request_time, request_count
    
    current_time = datetime.now()
    time_diff = (current_time - last_request_time).total_seconds()
    
    # Reset counter every hour
    if time_diff > 3600:
        request_count = 0
        last_request_time = current_time
    
    # Check if we're over limit
    if request_count >= REQUESTS_PER_HOUR:
        wait_time = 3600 - time_diff
        raise HTTPException(
            status_code=429, 
            detail=f"Rate limit reached. Wait {int(wait_time)} seconds"
        )
    
    request_count += 1
    
    # Random delay between 3-7 seconds to appear more human
    delay = random.uniform(3, 7)
    time.sleep(delay)

def get_pytrends():
    """Create new pytrends instance with random user agent"""
    return TrendReq(
        hl='en-US', 
        tz=360, 
        timeout=(10, 25),
        retries=3,
        backoff_factor=0.5
    )

@app.get("/")
def home():
    return {
        "status": "Google Trends API is running",
        "requests_used": request_count,
        "requests_remaining": REQUESTS_PER_HOUR - request_count
    }

@app.get("/trends")
def get_trends(keyword: str, timeframe: str = "today 3-m", geo: str = "US"):
    rate_limit_check()
    
    try:
        pytrends = get_pytrends()
        pytrends.build_payload([keyword], timeframe=timeframe, geo=geo)
        
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
        
        data = interest_df[keyword].tolist()
        current_score = int(data[-1]) if data else 0
        average_score = int(sum(data) / len(data)) if data else 0
        peak_score = int(max(data)) if data else 0
        
        if len(data) >= 8:
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
        
        return {
            "keyword": keyword,
            "current_score": current_score,
            "average_score": average_score,
            "trend_direction": trend_direction,
            "peak_score": peak_score,
            "data_points": data
        }
        
    except Exception as e:
        if "429" in str(e):
            raise HTTPException(
                status_code=429,
                detail="Google Trends rate limit hit. Please wait before retrying."
            )
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/trends/batch")
def get_trends_batch(keywords: str, timeframe: str = "today 3-m", geo: str = "US"):
    """
    SEQUENTIAL batch processing with delays
    Max 3 keywords to be safe
    """
    keyword_list = [k.strip() for k in keywords.split(",")[:3]]  # Limit to 3
    results = []
    
    for i, keyword in enumerate(keyword_list):
        try:
            result = get_trends(keyword=keyword, timeframe=timeframe, geo=geo)
            results.append(result)
            
            # Extra delay between batch items (5-10 seconds)
            if i < len(keyword_list) - 1:  # Don't delay after last item
                time.sleep(random.uniform(5, 10))
                
        except HTTPException as e:
            # If rate limited, return what we have so far
            if e.status_code == 429:
                return {
                    "results": results,
                    "partial": True,
                    "error": "Rate limit reached, partial results returned"
                }
            raise
    
    return {"results": results, "partial": False}

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "requests_used": request_count,
        "requests_remaining": REQUESTS_PER_HOUR - request_count
    }
