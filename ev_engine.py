"""
期待値計算エンジン
"""
import numpy as np
from typing import List, Dict, Tuple
from itertools import permutations


class EVEngine:
    """期待値計算エンジン"""
    
    def __init__(self, min_ev: float = 1.0):
        """
        Args:
            min_ev: 推奨する最低期待値（デフォルト100%）
        """
        self.min_ev = min_ev
    
    # === 補正係数ヘルパー関数（有馬記念での教訓を反映） ===
    
    @staticmethod
    def calc_gate_factor(gate_number: int, total_horses: int = 16, 
                         course_type: str = 'nakayama_2500') -> float:
        """
        枠順補正係数を計算
        
        Args:
            gate_number: 馬番（1-18）
            total_horses: 出走頭数
            course_type: コースタイプ（内枠有利/外枠有利）
        
        Returns:
            補正係数（0.85-1.15）
        """
        if course_type in ['nakayama_2500', 'nakayama_2000', 'hanshin_2200']:
            # 内枠有利コース
            if gate_number <= 4:
                return 1.15
            elif gate_number <= 8:
                return 1.05
            elif gate_number <= 12:
                return 0.95
            else:
                return 0.85
        elif course_type in ['tokyo_1600', 'tokyo_2400']:
            # 比較的フラット
            return 1.0
        else:
            return 1.0
    
    @staticmethod
    def calc_track_factor(horse_type: str, track_condition: str) -> float:
        """
        馬場適性補正係数を計算
        
        Args:
            horse_type: 馬のタイプ（'power', 'speed', 'stamina', 'balanced'）
            track_condition: 馬場状態（'firm', 'good', 'yielding', 'soft'）
        
        Returns:
            補正係数（0.85-1.20）
        """
        # タフな馬場（荒れた良馬場、重馬場）
        if track_condition in ['yielding', 'soft']:
            if horse_type in ['power', 'stamina']:
                return 1.15
            elif horse_type == 'speed':
                return 0.85
            else:
                return 1.0
        # 軽い馬場（高速馬場）
        elif track_condition == 'firm':
            if horse_type == 'speed':
                return 1.10
            elif horse_type in ['power', 'stamina']:
                return 0.95
            else:
                return 1.0
        else:
            return 1.0
    
    @staticmethod
    def calc_content_factor(time_gap: float, rival_next_result: str = None) -> float:
        """
        レース内容評価補正係数を計算
        着順ではなく「勝ち馬とのタイム差」「相手のその後の活躍」で評価
        
        Args:
            time_gap: 勝ち馬とのタイム差（秒）。小さいほど良い
            rival_next_result: 相手（勝ち馬）のその後の成績
                              'g1_win': G1優勝, 'g1_place': G1連対, 'good': 重賞好走, None: 不明
        
        Returns:
            補正係数（0.9-1.35）
        """
        factor = 1.0
        
        # タイム差補正
        if time_gap <= 0.2:
            factor *= 1.20  # 0.2秒以内は互角
        elif time_gap <= 0.5:
            factor *= 1.10  # 0.5秒以内は実力伯仲
        elif time_gap <= 1.0:
            factor *= 1.0
        else:
            factor *= 0.90  # 1秒以上離されたら減点
        
        # 相手関係ボーナス
        if rival_next_result == 'g1_win':
            factor *= 1.15  # 相手がその後G1勝ちなら自分も高評価
        elif rival_next_result == 'g1_place':
            factor *= 1.08
        elif rival_next_result == 'good':
            factor *= 1.05
        
        return round(factor, 2)
    
    def calculate_win_probabilities(self, horses: List[Dict]) -> List[Dict]:
        """
        各馬の勝率を計算
        穴馬バイアスを補正
        """
        # オッズから市場確率を計算
        for h in horses:
            if h.get('odds') and h['odds'] > 0:
                h['market_prob'] = 1 / h['odds']
            else:
                h['market_prob'] = 0.01
        
        # 正規化
        total = sum(h['market_prob'] for h in horses)
        for h in horses:
            h['market_prob'] /= total
        
        # 穴馬バイアス補正 + 適性補正
        for h in horses:
            odds = h.get('odds', 10)
            if odds > 50:
                h['adj_factor'] = 2.0  # 大穴を上方修正
            elif odds > 20:
                h['adj_factor'] = 1.5
            elif odds > 10:
                h['adj_factor'] = 1.2
            elif odds > 5:
                h['adj_factor'] = 1.0
            else:
                h['adj_factor'] = 0.8  # 人気馬を下方修正
            
            # 詳細な適性・状態補正
            # condition: 1.1(好調), 1.0(普通), 0.9(不調)
            # course_aptitude: 1.1(得意), 1.0(普通), 0.9(苦手)
            cond = h.get('condition_factor', 1.0)
            h_course = h.get('horse_course_aptitude', 1.0)
            j_course = h.get('jockey_course_aptitude', 1.0)
            
            # 従来の汎用的な適性（互換性のため）
            horse_apt = h.get('horse_aptitude', 1.0)
            jockey_apt = h.get('jockey_aptitude', 1.0)
            
            # === 新規追加：有馬記念での教訓を反映 ===
            
            # 枠順補正 (gate_factor)
            # 中山2500mなど内枠有利なコースで使用
            # 内枠(1-4番): 1.15, 中枠(5-12番): 1.0, 外枠(13-16番): 0.85
            gate_factor = h.get('gate_factor', 1.0)
            
            # 馬場適性 (track_condition_factor)
            # タフな馬場向き: 1.15, 普通: 1.0, 軽い馬場向き: 0.9
            track_factor = h.get('track_condition_factor', 1.0)
            
            # レース内容評価 (content_factor)
            # 着順ではなく「タイム差」「相手関係」で評価
            # - rivals_bonus: 強い相手と僅差なら加点 (1.0-1.3)
            # - time_gap_adj: 勝ち馬との0.3秒差以内なら加点
            content_factor = h.get('content_factor', 1.0)
            
            h['pred_prob'] = (h['market_prob'] * h['adj_factor'] * 
                             cond * h_course * j_course * 
                             horse_apt * jockey_apt *
                             gate_factor * track_factor * content_factor)
        
        # 再正規化
        total = sum(h['pred_prob'] for h in horses)
        for h in horses:
            h['pred_prob'] /= total
        
        return horses
    
    def calculate_win_ev(self, horses: List[Dict]) -> List[Dict]:
        """単勝の期待値を計算"""
        horses = self.calculate_win_probabilities(horses)
        
        results = []
        for h in horses:
            odds = h.get('odds', 0)
            if odds > 0:
                ev = h['pred_prob'] * odds
                results.append({
                    'type': 'win',
                    'number': h.get('number'),
                    'name': h.get('name'),
                    'popularity': h.get('popularity'),
                    'odds': odds,
                    'predicted_prob': h['pred_prob'],
                    'ev': ev,
                    'ev_percent': ev * 100,
                    'condition_factor': h.get('condition_factor', 1.0),
                    'horse_course_aptitude': h.get('horse_course_aptitude', 1.0),
                    'jockey_course_aptitude': h.get('jockey_course_aptitude', 1.0),
                    'horse_aptitude': h.get('horse_aptitude', 1.0),
                    'jockey_aptitude': h.get('jockey_aptitude', 1.0)
                })
        
        # EV順でソート
        results.sort(key=lambda x: -x['ev'])
        return results
    
    def calculate_place_ev(self, horses: List[Dict], place_odds: Dict) -> List[Dict]:
        """複勝の期待値を計算"""
        horses = self.calculate_win_probabilities(horses)
        n = len(horses)
        
        results = []
        for h in horses:
            num = h.get('number')
            if num in place_odds:
                odds = place_odds[num]
                # 複勝率 = 勝率 * 約3倍（簡易計算）
                place_prob = min(h['pred_prob'] * 3, 0.8)
                ev = place_prob * odds
                
                results.append({
                    'type': 'place',
                    'number': num,
                    'name': h.get('name'),
                    'odds': odds,
                    'predicted_prob': place_prob,
                    'ev': ev,
                    'ev_percent': ev * 100
                })
        
        results.sort(key=lambda x: -x['ev'])
        return results
    
    def calculate_trifecta_ev(self, horses: List[Dict], top_n: int = 6, 
                               include_favorites: int = 3) -> List[Dict]:
        """
        3連単の期待値を計算
        計算量削減のため上位候補のみ
        
        Args:
            horses: 出走馬リスト
            top_n: 予測確率上位から選ぶ頭数
            include_favorites: 人気上位から強制的に含める頭数（保険）
        """
        horses = self.calculate_win_probabilities(horses)
        n = len(horses)
        
        if n < 3:
            return []
        
        # 予測確率上位
        top_by_prob = sorted(horses, key=lambda x: -x['pred_prob'])[:top_n]
        
        # 人気上位（低オッズ）も強制的に含める（保険ロジック）
        # 期待値が低くても「消し」にしない
        top_by_odds = sorted(horses, key=lambda x: x.get('odds', 999))[:include_favorites]
        
        # 重複を除いて統合
        seen_numbers = set()
        top_horses = []
        for h in top_by_prob + top_by_odds:
            if h['number'] not in seen_numbers:
                seen_numbers.add(h['number'])
                top_horses.append(h)
        
        results = []
        for h1 in top_horses:
            for h2 in top_horses:
                if h2['number'] == h1['number']:
                    continue
                for h3 in top_horses:
                    if h3['number'] in [h1['number'], h2['number']]:
                        continue
                    
                    # 条件付き確率で計算
                    p1 = h1['pred_prob']
                    p2 = h2['pred_prob'] / (1 - h1['pred_prob'])
                    p3 = h3['pred_prob'] / (1 - h1['pred_prob'] - h2['pred_prob'])
                    
                    tri_prob = p1 * p2 * p3
                    
                    # 3連単オッズを推定（単勝オッズの積 × 係数）
                    o1 = h1.get('odds', 10)
                    o2 = h2.get('odds', 10)
                    o3 = h3.get('odds', 10)
                    tri_odds = o1 * o2 * o3 * 0.08
                    tri_odds = max(10, min(tri_odds, 100000))
                    
                    ev = tri_prob * tri_odds
                    
                    results.append({
                        'type': 'trifecta',
                        'combination': f"{h1['number']}-{h2['number']}-{h3['number']}",
                        'horses': [h1['name'], h2['name'], h3['name']],
                        'odds': tri_odds,
                        'predicted_prob': tri_prob,
                        'ev': ev,
                        'ev_percent': ev * 100
                    })
        
        results.sort(key=lambda x: -x['ev'])
        return results[:20]  # 上位20組み合わせのみ
    
    def get_recommendations(self, horses: List[Dict], 
                           place_odds: Dict = None,
                           min_ev: float = None) -> Dict:
        """
        期待値100%超の推奨馬券を取得
        """
        if min_ev is None:
            min_ev = self.min_ev
        
        recommendations = {
            'win': [],
            'place': [],
            'trifecta': []
        }
        
        # 単勝
        win_evs = self.calculate_win_ev(horses)
        recommendations['win'] = [r for r in win_evs if r['ev'] >= min_ev]
        
        # 複勝
        if place_odds:
            place_evs = self.calculate_place_ev(horses, place_odds)
            recommendations['place'] = [r for r in place_evs if r['ev'] >= min_ev]
        
        # 3連単
        tri_evs = self.calculate_trifecta_ev(horses)
        recommendations['trifecta'] = [r for r in tri_evs if r['ev'] >= min_ev]
        
        return recommendations
    
    def calculate_kelly_bet(self, ev: float, odds: float, 
                           bankroll: float = 100000,
                           fraction: float = 0.25) -> float:
        """
        ケリー基準で最適賭け金を計算
        
        Args:
            ev: 期待値
            odds: オッズ
            bankroll: 資金
            fraction: ケリー係数（デフォルト1/4）
        
        Returns:
            推奨賭け金
        """
        if ev <= 1 or odds <= 1:
            return 0
        
        # ケリー基準: f = (p*b - q) / b
        # p = 予測勝率, b = odds - 1, q = 1 - p
        p = ev / odds  # 予測勝率を逆算
        b = odds - 1
        q = 1 - p
        
        kelly = (p * b - q) / b
        
        # フラクショナルケリー
        kelly = max(0, kelly * fraction)
        
        # 最大5%までに制限
        kelly = min(kelly, 0.05)
        
        return round(bankroll * kelly, -2)  # 100円単位に丸め


# テスト
if __name__ == "__main__":
    engine = EVEngine()
    
    # テストデータ
    horses = [
        {'number': 1, 'name': 'Horse A', 'odds': 3.5},
        {'number': 2, 'name': 'Horse B', 'odds': 5.0},
        {'number': 3, 'name': 'Horse C', 'odds': 8.0},
        {'number': 4, 'name': 'Horse D', 'odds': 15.0},
        {'number': 5, 'name': 'Horse E', 'odds': 25.0},
        {'number': 6, 'name': 'Horse F', 'odds': 50.0},
    ]
    
    print("Win EVs:")
    for r in engine.calculate_win_ev(horses)[:3]:
        print(f"  #{r['number']} {r['name']}: {r['ev_percent']:.0f}%")
    
    print("\nRecommendations (EV >= 100%):")
    recs = engine.get_recommendations(horses)
    print(f"  Win: {len(recs['win'])} bets")
    print(f"  Trifecta: {len(recs['trifecta'])} bets")
