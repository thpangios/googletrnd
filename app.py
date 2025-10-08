from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pytrends.request import TrendReq
import time
import random
from datetime import datetime

app = FastAPI(title="Google Trends API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
last_request_time = datetime.now()
request_count = 0
REQUESTS_PER_HOUR = 60  # Conservative limit

def rate_limit_check():
    global last_request_time, request_count
    
    current_time = datetime.now()
    time_diff = (current_time - last_request_time).total_seconds()
    
    if time_diff > 3600:
        request_count = 0
        last_request_time = current_time
    
    if request_count >= REQUESTS_PER_HOUR:
        wait_time = 3600 - time_diff
        raise HTTPException(
            status_code=429, 
            detail=f"Rate limit: wait {int(wait_time)}s"
        )
    
    request_count += 1
    time.sleep(random.uniform(3, 6))  # Random delay

@app.get("/")
def home():
    return {
        "status": "running",
        "requests_used": request_count,
        "requests_remaining": REQUESTS_PER_HOUR - request_count
    }

@app.get("/trends")
def get_trends(keyword: str, timeframe: str = "today 3-m", geo: str = "US"):
    rate_limit_check()
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Simple initialization without retries parameter
            pytrends = TrendReq(hl='en-US', tz=360, timeout=(10, 25))
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
            error_msg = str(e)
            
            if "429" in error_msg or "quota" in error_msg.lower():
                if attempt < max_retries - 1:
                    time.sleep(30)  # Wait 30 seconds before retry
                    continue
                raise HTTPException(
                    status_code=429,
                    detail="Google Trends rate limit. Try again later."
                )
            
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
                
            raise HTTPException(status_code=500, detail=error_msg)

@app.get("/trends/batch")
def get_trends_batch(keywords: str, timeframe: str = "today 3-m", geo: str = "US"):
    keyword_list = [k.strip() for k in keywords.split(",")[:3]]
    results = []
    
    for i, keyword in enumerate(keyword_list):
        try:
            result = get_trends(keyword=keyword, timeframe=timeframe, geo=geo)
            results.append(result)  # ✅ Result added here
            
            # Delay between batch items
            if i < len(keyword_list) - 1:
                time.sleep(random.uniform(8, 15))
                
        except HTTPException as e:
            if e.status_code == 429:
                return {
                    "results": results,  # ✅ Whatever we got so far
                    "partial": True,
                    "completed": len(results),  # ✅ Fixed: actual count
                    "total": len(keyword_list),
                    "failed_on": keyword,  # ✅ Added: which keyword failed
                    "error": "Rate limited - partial results"
                }
            raise
    
    return {
        "results": results,
        "partial": False,
        "completed": len(results),
        "total": len(keyword_list)
    }

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "requests_used": request_count,
        "limit": REQUESTS_PER_HOUR
    }
