"""
DYNAMIC RISK MANAGER
====================
Sistema inteligente de gestión de riesgo con:
- Trailing Stop Loss (TSL)
- Take Profit parcial por niveles
- Ajuste dinámico según volatilidad y momentum
- Condiciones de salida inteligente
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional, List
from loguru import logger
from datetime import datetime

from config import settings


class DynamicRiskManager:
    """
    Gestor dinámico de riesgo para posiciones.
    Tier-aware: adapta TP/SL/trailing según el perfil de riesgo de cada moneda.
    """

    def __init__(self):
        """Initialize dynamic risk manager"""

        # TP/SL base desde config
        self.base_tp_pct = settings.TAKE_PROFIT_PCT  # 0.20 (20%)
        self.base_sl_pct = settings.STOP_LOSS_PCT    # 0.05 (5%)

        # Niveles de Take Profit parcial (optimized by Monte Carlo simulation)
        # TP1: sell 25% — lock early profit
        # TP2: sell 35% — substantial gain secured
        # TP3: sell 100% remaining — let winner run to max
        self.tp_levels = [
            {'name': 'TP1', 'pct': 0.12, 'size': 0.25},
            {'name': 'TP2', 'pct': 0.25, 'size': 0.35},
            {'name': 'TP3', 'pct': 0.50, 'size': 1.00},
        ]

        # Tier-specific TP/SL adjustments
        # Tier 1 (Blue Chip): wider TP, let winners run longer
        # Tier 4 (Meme): tighter SL, take profit faster
        self.tier_adjustments = {
            1: {'sl_mult': 1.2, 'tp_mult': 1.3, 'trailing_activation': 0.04, 'trailing_atr_mult': 1.2},
            2: {'sl_mult': 1.0, 'tp_mult': 1.1, 'trailing_activation': 0.05, 'trailing_atr_mult': 1.5},
            3: {'sl_mult': 1.0, 'tp_mult': 1.0, 'trailing_activation': 0.05, 'trailing_atr_mult': 1.5},
            4: {'sl_mult': 0.7, 'tp_mult': 0.8, 'trailing_activation': 0.03, 'trailing_atr_mult': 2.0},
        }

        # Configuración de Trailing Stop Loss
        self.trailing_stop_activation = 0.05  # Activa TSL cuando ganancia > 5%
        self.trailing_stop_distance_atr_mult = 1.5  # Distancia = 1.5 * ATR

        logger.info("Dynamic Risk Manager initialized (tier-aware, TP 12/25/50%)")

    def _get_tier(self, ticker: str) -> int:
        """Get tier number for a ticker"""
        profile = settings.COIN_RISK_PROFILES.get(ticker, settings.DEFAULT_RISK_PROFILE)
        return profile["tier"]

    def calculate_dynamic_tp_sl(
        self,
        entry_price: float,
        ticker: str,
        features: Dict[str, float],
        market_conditions: Optional[Dict] = None,
        confidence: str = "high",
    ) -> Dict[str, float]:
        """
        Calcula TP/SL dinámicos con tier-awareness.

        Tier 1 (Blue Chip): SL más ancho (+20%), TP más amplio (+30%), trailing temprano
        Tier 4 (Meme):      SL más ajustado (-30%), TP más rápido (-20%), trailing agresivo
        """
        # Get tier adjustments
        tier = self._get_tier(ticker)
        tier_adj = self.tier_adjustments.get(tier, self.tier_adjustments[3])

        # Extraer ATR (volatilidad)
        atr_pct = features.get('atr_pct', 0.03)

        # Extraer momentum
        momentum_3d = features.get('momentum_3d', 0.0)
        momentum_strength = features.get('momentum_strength', 0.0)

        # Multiplicadores
        volatility_multiplier = self._calculate_volatility_multiplier(atr_pct)
        momentum_multiplier = self._calculate_momentum_multiplier(momentum_3d, momentum_strength)
        market_multiplier = self._calculate_market_multiplier(market_conditions)

        # Confidence-level multipliers (tighter TP/SL for lower confidence)
        conf_config = settings.CONFIDENCE_LEVELS.get(confidence, settings.CONFIDENCE_LEVELS["exploratory"])
        conf_tp_mult = conf_config.get("tp_mult", 1.0)
        conf_sl_mult = conf_config.get("sl_mult", 1.0)

        # Calcular Stop Loss dinámico (tier + confidence adjusted)
        dynamic_sl_pct = self.base_sl_pct * volatility_multiplier * tier_adj['sl_mult'] * conf_sl_mult
        dynamic_sl_pct = max(0.02, min(0.12, dynamic_sl_pct))

        stop_loss = entry_price * (1 - dynamic_sl_pct)

        # Calcular Take Profits dinámicos (tier + confidence adjusted)
        tp_multiplier = volatility_multiplier * momentum_multiplier * market_multiplier * tier_adj['tp_mult'] * conf_tp_mult

        tp1_pct = self.tp_levels[0]['pct'] * tp_multiplier
        tp2_pct = self.tp_levels[1]['pct'] * tp_multiplier
        tp3_pct = self.tp_levels[2]['pct'] * tp_multiplier

        # Límites razonables (adjusted for confidence level)
        tp1_pct = max(0.03, min(0.25, tp1_pct))
        tp2_pct = max(0.06, min(0.45, tp2_pct))
        tp3_pct = max(0.12, min(0.80, tp3_pct))

        tp1 = entry_price * (1 + tp1_pct)
        tp2 = entry_price * (1 + tp2_pct)
        tp3 = entry_price * (1 + tp3_pct)

        logger.info(
            f"[T{tier}/{confidence}] {ticker} | SL: -{dynamic_sl_pct*100:.1f}% | "
            f"TP1: +{tp1_pct*100:.1f}% | TP2: +{tp2_pct*100:.1f}% | TP3: +{tp3_pct*100:.1f}% | "
            f"Vol: {volatility_multiplier:.2f}x | Mom: {momentum_multiplier:.2f}x"
        )

        return {
            'stop_loss': stop_loss,
            'stop_loss_pct': dynamic_sl_pct,
            'tp1': tp1,
            'tp1_pct': tp1_pct,
            'tp1_size': self.tp_levels[0]['size'],
            'tp2': tp2,
            'tp2_pct': tp2_pct,
            'tp2_size': self.tp_levels[1]['size'],
            'tp3': tp3,
            'tp3_pct': tp3_pct,
            'tp3_size': self.tp_levels[2]['size'],
            'trailing_stop_enabled': True,
            'trailing_activation': tier_adj['trailing_activation'],
            'trailing_atr_mult': tier_adj['trailing_atr_mult'],
            'atr_pct': atr_pct,
            'tier': tier,
            'volatility_mult': volatility_multiplier,
            'momentum_mult': momentum_multiplier,
            'market_mult': market_multiplier,
        }

    def _calculate_volatility_multiplier(self, atr_pct: float) -> float:
        """
        Calcula multiplicador basado en volatilidad (ATR)

        Alta volatilidad → TP/SL más amplios
        Baja volatilidad → TP/SL más ajustados
        """
        # ATR típico en crypto: 2-5%
        # Normalizar a rango [0.8, 1.5]

        if atr_pct < 0.02:  # Volatilidad muy baja
            return 0.8
        elif atr_pct < 0.03:  # Volatilidad baja
            return 0.9
        elif atr_pct < 0.05:  # Volatilidad normal
            return 1.0
        elif atr_pct < 0.08:  # Volatilidad alta
            return 1.2
        else:  # Volatilidad muy alta
            return 1.5

    def _calculate_momentum_multiplier(
        self,
        momentum_3d: float,
        momentum_strength: float
    ) -> float:
        """
        Calcula multiplicador basado en momentum

        Momentum fuerte → TP más amplio (esperar más)
        Momentum débil → TP más cercano (tomar ganancias rápido)
        """
        # Momentum fuerte positivo → multiplicador alto
        # Momentum débil → multiplicador bajo

        if momentum_3d > 0.05 and momentum_strength > 0.5:  # Momentum muy fuerte
            return 1.3
        elif momentum_3d > 0.02 and momentum_strength > 0.3:  # Momentum fuerte
            return 1.15
        elif momentum_3d > 0:  # Momentum positivo normal
            return 1.0
        elif momentum_3d > -0.02:  # Momentum débil
            return 0.9
        else:  # Momentum negativo
            return 0.8

    def _calculate_market_multiplier(
        self,
        market_conditions: Optional[Dict]
    ) -> float:
        """
        Calcula multiplicador basado en condiciones del mercado

        Fear & Greed extremo → ajustar agresividad
        VIX alto → más conservador
        """
        if market_conditions is None:
            return 1.0

        fear_greed = market_conditions.get('fear_greed', 50)
        vix = market_conditions.get('vix', 20)

        multiplier = 1.0

        # Fear & Greed
        if fear_greed > 75:  # Extreme Greed → TP más cercano (tomar ganancias)
            multiplier *= 0.85
        elif fear_greed > 60:  # Greed
            multiplier *= 0.95
        elif fear_greed < 25:  # Extreme Fear → TP más amplio (aprovechar rebote)
            multiplier *= 1.15
        elif fear_greed < 40:  # Fear
            multiplier *= 1.05

        # VIX (volatilidad del S&P 500)
        if vix > 30:  # Alta incertidumbre → más conservador
            multiplier *= 0.9
        elif vix > 25:
            multiplier *= 0.95

        return multiplier

    def calculate_trailing_stop(
        self,
        entry_price: float,
        current_price: float,
        current_stop_loss: float,
        atr_pct: float,
        tp_levels: Optional[Dict] = None,
    ) -> Tuple[float, bool]:
        """
        Trailing Stop Loss — tier-aware, progressive tightening.

        Behavior:
        - Activates when profit > tier activation threshold (3-5%)
        - Distance shrinks as profit grows (lock more profit at higher levels)
        - After TP1 hit: trail tighter (lock gains)
        - After TP2 hit: trail very tight (protect remaining position)

        Args:
            entry_price: Precio de entrada
            current_price: Precio actual
            current_stop_loss: SL actual
            atr_pct: ATR como % del precio (volatilidad)
            tp_levels: Dict with tier, trailing_activation, trailing_atr_mult, tp1_hit, tp2_hit

        Returns:
            (nuevo_stop_loss, activado)
        """
        profit_pct = (current_price - entry_price) / entry_price

        # Get tier-specific params
        activation = self.trailing_stop_activation
        atr_mult = self.trailing_stop_distance_atr_mult
        if tp_levels:
            activation = tp_levels.get('trailing_activation', activation)
            atr_mult = tp_levels.get('trailing_atr_mult', atr_mult)

        if profit_pct < activation:
            return current_stop_loss, False

        # Progressive tightening: as profit grows, trail closer
        # Base distance from ATR
        base_distance = atr_pct * atr_mult

        # Tighten trailing based on profit level
        if tp_levels and tp_levels.get('tp2_hit'):
            # After TP2: very tight trail (lock most profit)
            trailing_distance_pct = base_distance * 0.5
        elif tp_levels and tp_levels.get('tp1_hit'):
            # After TP1: tighter trail
            trailing_distance_pct = base_distance * 0.7
        elif profit_pct > 0.30:
            # Big profit: tighten
            trailing_distance_pct = base_distance * 0.6
        elif profit_pct > 0.15:
            # Good profit: moderate tighten
            trailing_distance_pct = base_distance * 0.8
        else:
            trailing_distance_pct = base_distance

        trailing_distance_pct = max(0.015, min(0.08, trailing_distance_pct))

        new_trailing_stop = current_price * (1 - trailing_distance_pct)
        new_stop_loss = max(current_stop_loss, new_trailing_stop)

        # Lock minimum profit based on current level
        if profit_pct > 0.10:
            min_lock = entry_price * 1.05  # Lock at least 5%
        else:
            min_lock = entry_price * 1.01  # Lock at least 1%
        new_stop_loss = max(new_stop_loss, min_lock)

        activated = new_stop_loss > current_stop_loss

        if activated:
            locked_pct = (new_stop_loss - entry_price) / entry_price * 100
            logger.info(
                f"Trailing Stop: ${current_stop_loss:.4f} -> ${new_stop_loss:.4f} "
                f"(dist={trailing_distance_pct*100:.1f}%, profit=+{profit_pct*100:.1f}%, locked=+{locked_pct:.1f}%)"
            )

        return new_stop_loss, activated

    def check_exit_conditions(
        self,
        ticker: str,
        entry_price: float,
        current_price: float,
        position_size: float,
        tp_levels: Dict,
        stop_loss: float,
        features: Dict[str, float],
        entry_features: Dict[str, float]
    ) -> Dict:
        """
        Verifica condiciones de salida inteligente

        Además de TP/SL, verifica:
        - Reversión de momentum
        - Caída de volumen
        - Patrones bajistas

        Returns:
            Dict con action ('hold', 'exit_partial', 'exit_full'), reason, quantity
        """

        current_profit_pct = (current_price - entry_price) / entry_price

        # 1. Check Stop Loss
        if current_price <= stop_loss:
            return {
                'action': 'exit_full',
                'reason': 'stop_loss_hit',
                'quantity': position_size,
                'price': stop_loss
            }

        # 2. Check Take Profit levels
        tp_hit = self._check_tp_levels(current_price, tp_levels, position_size)
        if tp_hit:
            return tp_hit

        # 3. Check momentum reversal (salida temprana si momentum se invierte)
        momentum_exit = self._check_momentum_reversal(
            features,
            entry_features,
            current_profit_pct
        )
        if momentum_exit:
            return momentum_exit

        # 4. Check volume collapse (volumen cae drásticamente)
        volume_exit = self._check_volume_collapse(features, entry_features)
        if volume_exit:
            return volume_exit

        # 5. Check bearish patterns
        pattern_exit = self._check_bearish_patterns(features, current_profit_pct)
        if pattern_exit:
            return pattern_exit

        # Si nada se cumple, mantener posición
        return {'action': 'hold'}

    def _check_tp_levels(
        self,
        current_price: float,
        tp_levels: Dict,
        position_size: float
    ) -> Optional[Dict]:
        """Verifica si se alcanzó algún nivel de TP"""

        # TP1
        if current_price >= tp_levels['tp1'] and not tp_levels.get('tp1_hit', False):
            quantity = position_size * tp_levels['tp1_size']
            return {
                'action': 'exit_partial',
                'reason': 'tp1_hit',
                'quantity': quantity,
                'price': tp_levels['tp1'],
                'level': 'TP1'
            }

        # TP2
        if current_price >= tp_levels['tp2'] and not tp_levels.get('tp2_hit', False):
            quantity = position_size * tp_levels['tp2_size']
            return {
                'action': 'exit_partial',
                'reason': 'tp2_hit',
                'quantity': quantity,
                'price': tp_levels['tp2'],
                'level': 'TP2'
            }

        # TP3 - exit all remaining
        if current_price >= tp_levels['tp3'] and not tp_levels.get('tp3_hit', False):
            return {
                'action': 'exit_full',
                'reason': 'tp3_hit',
                'quantity': position_size,
                'price': tp_levels['tp3'],
                'level': 'TP3'
            }

        return None

    def _check_momentum_reversal(
        self,
        current_features: Dict,
        entry_features: Dict,
        current_profit_pct: float
    ) -> Optional[Dict]:
        """
        Detecta reversión de momentum

        Si momentum se invierte fuertemente y estamos en ganancia, salir
        """
        entry_momentum = entry_features.get('momentum_3d', 0)
        current_momentum = current_features.get('momentum_3d', 0)

        momentum_strength_entry = entry_features.get('momentum_strength', 0)
        momentum_strength_current = current_features.get('momentum_strength', 0)

        # Reversión fuerte: momentum positivo → negativo
        if entry_momentum > 0.02 and current_momentum < -0.02:
            # Si estamos en ganancia > 3%, salir
            if current_profit_pct > 0.03:
                return {
                    'action': 'exit_full',
                    'reason': 'momentum_reversal',
                    'quantity': None,  # Full position
                    'details': f'Momentum reversed: {entry_momentum:.3f} → {current_momentum:.3f}'
                }

        # Pérdida de momentum strength
        if momentum_strength_entry > 0.5 and momentum_strength_current < 0.2:
            if current_profit_pct > 0.05:  # Solo si en ganancia > 5%
                return {
                    'action': 'exit_partial',
                    'reason': 'momentum_weakening',
                    'quantity': 0.5,  # Salir 50%
                    'details': f'Momentum strength: {momentum_strength_entry:.2f} → {momentum_strength_current:.2f}'
                }

        return None

    def _check_volume_collapse(
        self,
        current_features: Dict,
        entry_features: Dict
    ) -> Optional[Dict]:
        """
        Detecta colapso de volumen

        Si volumen cae drásticamente, puede indicar fin del pump
        """
        entry_volume_ratio = entry_features.get('volume_ratio_20', 1.0)
        current_volume_ratio = current_features.get('volume_ratio_20', 1.0)

        # Volumen cae más de 70%
        if entry_volume_ratio > 1.5 and current_volume_ratio < 0.5:
            return {
                'action': 'exit_partial',
                'reason': 'volume_collapse',
                'quantity': 0.5,  # Salir 50%
                'details': f'Volume ratio: {entry_volume_ratio:.2f} → {current_volume_ratio:.2f}'
            }

        return None

    def _check_bearish_patterns(
        self,
        current_features: Dict,
        current_profit_pct: float
    ) -> Optional[Dict]:
        """
        Detecta patrones bajistas

        - Velas bajistas consecutivas
        - Lower lows pattern
        """
        green_candles_5d = current_features.get('green_candles_5d', 0)
        higher_lows_5d = current_features.get('higher_lows_5d', 0)

        # Muchas velas rojas (< 20% verdes en 5 días)
        if green_candles_5d < 0.2 and current_profit_pct > 0.02:
            return {
                'action': 'exit_partial',
                'reason': 'bearish_candles',
                'quantity': 0.3,  # Salir 30%
                'details': f'Green candles ratio: {green_candles_5d:.2f}'
            }

        # Pattern de lower lows (bajista)
        if higher_lows_5d < 0.2 and current_profit_pct > 0.03:
            return {
                'action': 'exit_partial',
                'reason': 'lower_lows_pattern',
                'quantity': 0.3,
                'details': f'Higher lows ratio: {higher_lows_5d:.2f}'
            }

        return None
