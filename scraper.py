"""
競馬データスクレイパー
netkeiba.comからレース情報を取得
"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
from typing import List, Dict, Optional
import time


class RaceScraper:
    """netkeiba.comからレース情報を取得"""
    
    BASE_URL = "https://race.netkeiba.com"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def get_today_races(self) -> List[Dict]:
        """今日のレース一覧を取得"""
        today = datetime.now().strftime('%Y%m%d')
        url = f"{self.BASE_URL}/top/race_list.html?kaisai_date={today}"
        
        try:
            resp = self.session.get(url, timeout=10)
            resp.encoding = 'EUC-JP'
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            races = []
            race_links = soup.select('a[href*="/race/"]')
            
            for link in race_links:
                href = link.get('href', '')
                match = re.search(r'/race/(\d+)', href)
                if match:
                    race_id = match.group(1)
                    race_name = link.text.strip()
                    if race_name and len(race_id) > 8:
                        races.append({
                            'race_id': race_id,
                            'race_name': race_name,
                            'url': f"{self.BASE_URL}/race/{race_id}"
                        })
            
            # 重複除去
            seen = set()
            unique_races = []
            for r in races:
                if r['race_id'] not in seen:
                    seen.add(r['race_id'])
                    unique_races.append(r)
            
            return unique_races
            
        except Exception as e:
            print(f"Error fetching races: {e}")
            return []
    
    def get_race_details(self, race_id: str) -> Optional[Dict]:
        """レース詳細（出走馬、オッズ）を取得"""
        url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
        
        try:
            resp = self.session.get(url, timeout=10)
            resp.encoding = 'EUC-JP'
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # レース情報
            race_info = {
                'race_id': race_id,
                'horses': []
            }
            
            # レース名
            title = soup.select_one('.RaceName')
            if title:
                race_info['name'] = title.text.strip()
            
            # 発走時刻
            time_elem = soup.select_one('.RaceData01')
            if time_elem:
                race_info['time'] = time_elem.text.strip()
            
            # 出走馬情報
            rows = soup.select('tr.HorseList')
            for row in rows:
                horse = {}
                
                # 馬番
                num = row.select_one('.Umaban')
                if num:
                    horse['number'] = int(num.text.strip())
                
                # 馬名
                name = row.select_one('.HorseName a')
                if name:
                    horse['name'] = name.text.strip()
                
                # 騎手
                jockey = row.select_one('.Jockey a')
                if jockey:
                    horse['jockey'] = jockey.text.strip()
                
                # オッズ（単勝）
                odds = row.select_one('.Odds span')
                if odds:
                    try:
                        horse['odds'] = float(odds.text.strip())
                    except:
                        horse['odds'] = None
                
                # 人気
                pop = row.select_one('.Popular span')
                if pop:
                    try:
                        horse['popularity'] = int(pop.text.strip())
                    except:
                        horse['popularity'] = None
                
                if horse.get('number') and horse.get('name'):
                    race_info['horses'].append(horse)
            
            return race_info
            
        except Exception as e:
            print(f"Error fetching race {race_id}: {e}")
            return None
    
    def get_odds(self, race_id: str) -> Dict:
        """オッズ情報を取得"""
        url = f"https://race.netkeiba.com/odds/index.html?race_id={race_id}"
        
        try:
            resp = self.session.get(url, timeout=10)
            resp.encoding = 'EUC-JP'
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            odds_data = {'win': {}, 'place': {}}
            
            # 単勝オッズ
            win_rows = soup.select('#odds_tan_block tr')
            for row in win_rows:
                num = row.select_one('.Num')
                odds = row.select_one('.Odds')
                if num and odds:
                    try:
                        horse_num = int(num.text.strip())
                        odds_val = float(odds.text.strip())
                        odds_data['win'][horse_num] = odds_val
                    except:
                        pass
            
            # 複勝オッズ
            place_rows = soup.select('#odds_fuku_block tr')
            for row in place_rows:
                num = row.select_one('.Num')
                odds = row.select_one('.Odds')
                if num and odds:
                    try:
                        horse_num = int(num.text.strip())
                        odds_text = odds.text.strip()
                        # 複勝は範囲で表示されることがある
                        if '-' in odds_text:
                            parts = odds_text.split('-')
                            odds_val = (float(parts[0]) + float(parts[1])) / 2
                        else:
                            odds_val = float(odds_text)
                        odds_data['place'][horse_num] = odds_val
                    except:
                        pass
            
            return odds_data
            
        except Exception as e:
            print(f"Error fetching odds for {race_id}: {e}")
            return {'win': {}, 'place': {}}


# テスト
if __name__ == "__main__":
    scraper = RaceScraper()
    print("Fetching today's races...")
    races = scraper.get_today_races()
    print(f"Found {len(races)} races")
    
    if races:
        print(f"\nFirst race: {races[0]}")
        details = scraper.get_race_details(races[0]['race_id'])
        if details:
            print(f"Race name: {details.get('name')}")
            print(f"Horses: {len(details.get('horses', []))}")
