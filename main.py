"""
競馬期待値計算アプリ - FastAPI バックエンド
リアルタイム情報収集 × 改良版期待値エンジン
"""
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pathlib import Path
from datetime import datetime
import json
import os

from scraper import RaceScraper
from ev_engine import EVEngine

app = FastAPI(title="競馬期待値計算アプリ")

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# グローバルインスタンス
scraper = RaceScraper()
ev_engine = EVEngine(min_ev=1.0)


def apply_improved_factors(horses, course_name="", distance=0):
    """
    改良版エンジン用の補正係数を適用
    - 枠順補正（中山・阪神の長距離で内枠有利）
    - 馬場適性（推定）
    """
    inner_advantage_courses = ['中山', '阪神']
    is_inner_advantage = any(c in course_name for c in inner_advantage_courses) and distance >= 2000
    
    for h in horses:
        gate = h.get('number', 8)  # 馬番を枠順として使用
        
        # 枠順補正
        if is_inner_advantage:
            if gate <= 4:
                h['gate_factor'] = 1.10
            elif gate <= 8:
                h['gate_factor'] = 1.02
            elif gate <= 12:
                h['gate_factor'] = 0.98
            else:
                h['gate_factor'] = 0.90
        else:
            h['gate_factor'] = 1.0
        
        # デフォルト値の設定
        h.setdefault('condition_factor', 1.0)
        h.setdefault('horse_course_aptitude', 1.0)
        h.setdefault('jockey_course_aptitude', 1.0)
        h.setdefault('horse_aptitude', 1.0)
        h.setdefault('jockey_aptitude', 1.0)
        h.setdefault('track_condition_factor', 1.0)
        h.setdefault('content_factor', 1.0)
    
    return horses


@app.get("/")
async def root():
    """メインページ"""
    html_path = Path(__file__).parent / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding='utf-8'))
    return HTMLResponse(content="<h1>競馬期待値計算アプリ</h1>")


@app.get("/manifest.json")
async def get_manifest():
    """PWA マニフェスト"""
    manifest_path = Path(__file__).parent / "manifest.json"
    if manifest_path.exists():
        return JSONResponse(
            content=json.loads(manifest_path.read_text(encoding='utf-8')),
            media_type="application/manifest+json"
        )
    return JSONResponse(content={})


@app.get("/sw.js")
async def get_service_worker():
    """Service Worker"""
    sw_path = Path(__file__).parent / "sw.js"
    if sw_path.exists():
        from fastapi.responses import Response
        return Response(
            content=sw_path.read_text(encoding='utf-8'),
            media_type="application/javascript"
        )
    return Response(content="", media_type="application/javascript")


@app.get("/icon-192.png")
@app.get("/icon-512.png")
async def get_icon():
    """アプリアイコン（SVGをPNG代わりに使用）"""
    # シンプルなSVGアイコンを返す
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
        <rect width="100" height="100" rx="20" fill="#6366f1"/>
        <text x="50" y="65" font-size="50" text-anchor="middle" fill="white">🏇</text>
    </svg>'''
    from fastapi.responses import Response
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/api/races")
async def get_races():
    """今日のレース一覧を取得（リアルタイム）"""
    try:
        races = scraper.get_today_races()
        
        # レース名からレース番号を抽出して整理
        for race in races:
            name = race.get('race_name', '')
            # 競馬場とレース番号を抽出
            # 例: "中山1R" や "阪神11R" のパターン
            race['display_name'] = name
        
        return {
            "races": races, 
            "count": len(races),
            "updated_at": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "races": [],
            "count": 0,
            "error": str(e)
        }


@app.get("/api/race/{race_id}")
async def get_race_details(race_id: str):
    """レース詳細を取得"""
    details = scraper.get_race_details(race_id)
    if not details:
        raise HTTPException(status_code=404, detail="Race not found")
    return details


@app.get("/api/ev/{race_id}")
async def calculate_ev(race_id: str, min_ev: float = 1.0, bankroll: float = 100000):
    """期待値を計算（改良版エンジン）"""
    # レース詳細を取得
    details = scraper.get_race_details(race_id)
    if not details:
        raise HTTPException(status_code=404, detail="Race not found")
    
    horses = details.get('horses', [])
    if not horses:
        raise HTTPException(status_code=400, detail="No horses found")
    
    # オッズ情報を取得
    odds_data = scraper.get_odds(race_id)
    place_odds = odds_data.get('place', {})
    
    # 複勝オッズがない場合は単勝オッズから推定
    if not place_odds:
        place_odds = {h['number']: h.get('odds', 10) * 0.35 for h in horses}
    
    # コース情報を抽出
    race_name = details.get('name', '')
    race_info = details.get('time', '')
    
    # 距離を推定（レース名やIDから）
    distance = 2000  # デフォルト
    if '2500' in race_name or '有馬記念' in race_name:
        distance = 2500
    elif '1600' in race_name or 'マイル' in race_name:
        distance = 1600
    
    # 改良版補正を適用
    horses = apply_improved_factors(horses, race_name, distance)
    
    # 期待値計算
    recommendations = ev_engine.get_recommendations(
        horses, 
        place_odds=place_odds,
        min_ev=min_ev
    )
    
    # ケリー基準で賭け金計算
    for bet_type in ['win', 'place', 'trifecta']:
        for rec in recommendations[bet_type]:
            rec['kelly_bet'] = ev_engine.calculate_kelly_bet(
                rec['ev'], rec['odds'], bankroll
            )
    
    return {
        'race_id': race_id,
        'race_name': race_name,
        'horse_count': len(horses),
        'recommendations': recommendations,
        'bankroll': bankroll,
        'updated_at': datetime.now().isoformat()
    }


@app.get("/api/recommend")
async def get_all_recommendations(min_ev: float = 1.0, bankroll: float = 100000):
    """全レースの推奨馬券を取得"""
    all_recommendations = []
    
    try:
        races = scraper.get_today_races()
    except Exception as e:
        return {
            'recommendations': [],
            'count': 0,
            'error': str(e)
        }
    
    for race in races:
        try:
            race_id = race['race_id']
            race_name = race.get('race_name', '')
            
            details = scraper.get_race_details(race_id)
            if not details or not details.get('horses'):
                continue
            
            horses = details['horses']
            
            # オッズ取得
            odds_data = scraper.get_odds(race_id)
            place_odds = odds_data.get('place', {})
            if not place_odds:
                place_odds = {h['number']: h.get('odds', 10) * 0.35 for h in horses}
            
            # 距離推定
            distance = 2000
            if '2500' in race_name or '有馬' in race_name:
                distance = 2500
            elif '1600' in race_name or 'マイル' in race_name:
                distance = 1600
            
            # 改良版補正
            horses = apply_improved_factors(horses, race_name, distance)
            
            # 期待値計算
            recs = ev_engine.get_recommendations(
                horses,
                place_odds=place_odds,
                min_ev=min_ev
            )
            
            for bet_type in ['win', 'place', 'trifecta']:
                for rec in recs[bet_type]:
                    rec['kelly_bet'] = ev_engine.calculate_kelly_bet(
                        rec['ev'], rec['odds'], bankroll
                    )
                    rec['race_name'] = race_name
                    rec['race_id'] = race_id
                    all_recommendations.append(rec)
                    
        except Exception as e:
            print(f"Error processing race {race.get('race_id', 'unknown')}: {e}")
            continue
    
    # EV降順でソート
    all_recommendations.sort(key=lambda x: -x['ev'])
    
    return {
        'recommendations': all_recommendations,
        'count': len(all_recommendations),
        'bankroll': bankroll,
        'updated_at': datetime.now().isoformat()
    }


@app.get("/api/health")
async def health_check():
    """ヘルスチェック"""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8080))
    print("=" * 60)
    print("競馬期待値計算アプリ - リアルタイム版")
    print("=" * 60)
    print("改良版期待値エンジン搭載")
    print("  - 枠順補正（内枠有利コース対応）")
    print("  - 馬場適性")
    print("  - 人気馬保険ロジック")
    print("=" * 60)
    print(f"Starting server at http://localhost:{port}")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=port)
