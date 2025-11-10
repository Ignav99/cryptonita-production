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
    Gestor dinámico de riesgo para posiciones
    """

    def __init__(self):
        """Initialize dynamic risk manager"""

        # TP/SL base desde config
        self.base_tp_pct = settings.TAKE_PROFIT_PCT  # 0.15 (15%)
        self.base_sl_pct = settings.STOP_LOSS_PCT    # 0.05 (5%)

        # Niveles de Take Profit parcial
        self.tp_levels = [
            {'name': 'TP1', 'pct': 0.10, 'size': 0.30},  # 30% a +10%
            {'name': 'TP2', 'pct': 0.20, 'size': 0.40},  # 40% a +20%
            {'name': 'TP3', 'pct': 0.40, 'size': 0.30},  # 30% a +40%
        ]

        # Configuración de Trailing Stop Loss
        self.trailing_stop_activation = 0.05  # Activa TSL cuando ganancia > 5%
        self.trailing_stop_distance_atr_mult = 1.5  # Distancia = 1.5 * ATR

        logger.info("✅ Dynamic Risk Manager initialized")

    def calculate_dynamic_tp_sl(
        self,
        entry_price: float,
        ticker: str,
        features: Dict[str, float],
        market_conditions: Optional[Dict] = None
    ) -> Dict[str, float]:
        """
        Calcula TP/SL dinámicos basados en features y condiciones del mercado

        Args:
            entry_price: Precio de entrada
            ticker: Símbolo del ticker
            features: Dict con features calculadas (ATR, momentum, etc)
            market_conditions: Dict con Fear&Greed, VIX, etc

        Returns:
            Dict con stop_loss, tp1, tp2, tp3, y distancias
        """

        # Extraer ATR (volatilidad)
        atr_pct = features.get('atr_pct', 0.03)  # Default 3%

        # Extraer momentum
        momentum_3d = features.get('momentum_3d', 0.0)
        momentum_strength = features.get('momentum_strength', 0.0)

        # Ajustar multiplicadores según volatilidad
        # Más volátil → TP/SL más amplios
        volatility_multiplier = self._calculate_volatility_multiplier(atr_pct)

        # Ajustar según momentum
        # Más momentum → TP más amplio, SL más ajustado
        momentum_multiplier = self._calculate_momentum_multiplier(
            momentum_3d,
            momentum_strength
        )

        # Ajustar según condiciones de mercado
        market_multiplier = self._calculate_market_multiplier(market_conditions)

        # Calcular Stop Loss dinámico
        # SL base ajustado por volatilidad (más volátil = SL más amplio para evitar stop out prematuro)
        dynamic_sl_pct = self.base_sl_pct * volatility_multiplier
        dynamic_sl_pct = max(0.03, min(0.10, dynamic_sl_pct))  # Entre 3% y 10%

        stop_loss = entry_price * (1 - dynamic_sl_pct)

        # Calcular Take Profits dinámicos
        # TP ajustados por volatilidad, momentum y mercado
        tp_multiplier = volatility_multiplier * momentum_multiplier * market_multiplier

        tp1_pct = self.tp_levels[0]['pct'] * tp_multiplier
        tp2_pct = self.tp_levels[1]['pct'] * tp_multiplier
        tp3_pct = self.tp_levels[2]['pct'] * tp_multiplier

        # Límites razonables
        tp1_pct = max(0.08, min(0.20, tp1_pct))   # Entre 8% y 20%
        tp2_pct = max(0.15, min(0.35, tp2_pct))   # Entre 15% y 35%
        tp3_pct = max(0.30, min(0.60, tp3_pct))   # Entre 30% y 60%

        tp1 = entry_price * (1 + tp1_pct)
        tp2 = entry_price * (1 + tp2_pct)
        tp3 = entry_price * (1 + tp3_pct)

        logger.info(
            f"📊 {ticker} | SL: -{dynamic_sl_pct*100:.1f}% | "
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
            'atr_pct': atr_pct,
            'volatility_mult': volatility_multiplier,
            'momentum_mult': momentum_multiplier,
            'market_mult': market_multiplier
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
        atr_pct: float
    ) -> Tuple[float, bool]:
        """
        Calcula Trailing Stop Loss

        El TSL sube con el precio pero nunca baja.
        Se activa cuando ganancia > 5%

        Args:
            entry_price: Precio de entrada
            current_price: Precio actual
            current_stop_loss: SL actual
            atr_pct: ATR como % del precio (volatilidad)

        Returns:
            (nuevo_stop_loss, activado)
        """
        # Calcular ganancia actual
        profit_pct = (current_price - entry_price) / entry_price

        # Solo activar TSL si ganancia > umbral
        if profit_pct < self.trailing_stop_activation:
            return current_stop_loss, False

        # Calcular distancia del TSL basada en ATR
        # Más volátil → más distancia (evitar stop out por volatilidad normal)
        trailing_distance_pct = atr_pct * self.trailing_stop_distance_atr_mult
        trailing_distance_pct = max(0.02, min(0.08, trailing_distance_pct))  # Entre 2% y 8%

        # Nuevo TSL = precio actual - distancia
        new_trailing_stop = current_price * (1 - trailing_distance_pct)

        # El TSL nunca baja, solo sube
        new_stop_loss = max(current_stop_loss, new_trailing_stop)

        # Asegurar que TSL esté por encima del precio de entrada (lock profit)
        new_stop_loss = max(new_stop_loss, entry_price * 1.01)  # Mínimo +1% profit locked

        activated = new_stop_loss > current_stop_loss

        if activated:
            logger.info(
                f"🔼 Trailing Stop updated: ${current_stop_loss:.4f} → ${new_stop_loss:.4f} "
                f"(Distance: {trailing_distance_pct*100:.1f}%, Profit: +{profit_pct*100:.1f}%)"
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

        # TP3
        if current_price >= tp_levels['tp3'] and not tp_levels.get('tp3_hit', False):
            quantity = position_size * tp_levels['tp3_size']
            return {
                'action': 'exit_partial',
                'reason': 'tp3_hit',
                'quantity': quantity,
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
