"""
PEG Processing Service

??ëª¨ë“ˆ?€ PEG ?°ì´?°ì˜ ì¡°íšŒ, ?„í„°ë§? ì²˜ë¦¬ë¥??´ë‹¹?˜ëŠ”
PEGProcessingService ?´ë˜?¤ë? ?œê³µ?©ë‹ˆ??

ê¸°ì¡´ AnalysisService?ì„œ PEG ê´€??ë¡œì§??ë¶„ë¦¬?˜ì—¬
?¨ì¼ ì±…ì„ ?ì¹™??ê°•í™”?˜ê³  ?¬ì‚¬?©ì„±???’ì…?ˆë‹¤.
"""

from __future__ import annotations

import logging
import os

# ?„ì‹œë¡??ˆë? import ?¬ìš© (?˜ì¤‘???¨í‚¤ì§€ êµ¬ì¡° ?•ë¦¬ ???˜ì •)
import sys
from datetime import datetime
from typing import Any, Dict, Optional, Tuple, Union

import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from exceptions import ServiceError
from repositories import DatabaseRepository
from .peg_service import PEGCalculator

# ë¡œê¹… ?¤ì •
logger = logging.getLogger(__name__)


class PEGProcessingError(ServiceError):
    """
    PEG ì²˜ë¦¬ ?œë¹„??ê´€???¤ë¥˜ ?ˆì™¸ ?´ë˜??

    PEG ?°ì´??ì¡°íšŒ, ?„í„°ë§? ì²˜ë¦¬?ì„œ ë°œìƒ?˜ëŠ” ?¤ë¥˜ë¥?ì²˜ë¦¬?©ë‹ˆ??
    """

    def __init__(
        self,
        message: str,
        details: Optional[Union[str, Dict[str, Any]]] = None,
        processing_step: Optional[str] = None,
        data_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        PEGProcessingError ì´ˆê¸°??

        Args:
            message (str): ?¤ë¥˜ ë©”ì‹œì§€
            details (Optional[Union[str, Dict[str, Any]]]): ì¶”ê? ?ì„¸ ?•ë³´
            processing_step (Optional[str]): ?¤íŒ¨??ì²˜ë¦¬ ?¨ê³„
            data_context (Optional[Dict[str, Any]]): ?°ì´??ì»¨í…?¤íŠ¸
        """
        super().__init__(
            message=message, details=details, service_name="PEGProcessingService", operation="process_peg_data"
        )
        self.processing_step = processing_step
        self.data_context = data_context

        logger.error("PEGProcessingError ë°œìƒ: %s (?¨ê³„: %s)", message, processing_step)

    def to_dict(self) -> Dict[str, Any]:
        """?•ì…”?ˆë¦¬ ?•íƒœë¡?ë³€??""
        data = super().to_dict()
        data.update({"processing_step": self.processing_step, "data_context": self.data_context})
        return data


class PEGProcessingService:
    """
    PEG ?°ì´??ì²˜ë¦¬ ?œë¹„???´ë˜??

    ?°ì´?°ë² ?´ìŠ¤?ì„œ PEG ?°ì´?°ë? ì¡°íšŒ?˜ê³ , ?„í„°ë¥??ìš©?˜ë©°,
    PEGCalculatorë¥??¬ìš©?˜ì—¬ ì§‘ê³„ ë°??Œìƒ PEGë¥?ê³„ì‚°?©ë‹ˆ??

    AnalysisService?ì„œ PEG ê´€??ë¡œì§??ë¶„ë¦¬?˜ì—¬ ?¨ì¼ ì±…ì„ ?ì¹™??ê°•í™”?˜ê³ 
    ?¬ì‚¬?©ì„±???’ì´??ê²ƒì´ ëª©í‘œ?…ë‹ˆ??

    ì£¼ìš” ê¸°ëŠ¥:
    1. DatabaseRepositoryë¥??µí•œ ?ì‹œ PEG ?°ì´??ì¡°íšŒ
    2. ?œê°„ ë²”ìœ„ ë°??„í„° ì¡°ê±´ ?ìš©
    3. PEGCalculatorë¥??µí•œ ì§‘ê³„ ë°??Œìƒ PEG ê³„ì‚°
    4. ProcessedPEGData ?•íƒœë¡?ê²°ê³¼ ë°˜í™˜
    """

    def __init__(self, database_repository: DatabaseRepository, peg_calculator: Optional[PEGCalculator] = None):
        """
        PEGProcessingService ì´ˆê¸°??

        Args:
            database_repository (DatabaseRepository): ?°ì´?°ë² ?´ìŠ¤ Repository
            peg_calculator (Optional[PEGCalculator]): PEG ê³„ì‚°ê¸?
        """
        self.database_repository = database_repository
        self.peg_calculator = peg_calculator or PEGCalculator()

        # ì²˜ë¦¬ ?¨ê³„ ?•ì˜
        self.processing_steps = [
            "data_retrieval",
            "data_validation",
            "aggregation",
            "derived_calculation",
            "result_formatting",
        ]

        logger.info("PEGProcessingService ì´ˆê¸°???„ë£Œ: calculator=%s", type(self.peg_calculator).__name__)

    def get_service_info(self) -> Dict[str, Any]:
        """?œë¹„???•ë³´ ë°˜í™˜"""
        return {
            "service_name": "PEGProcessingService",
            "processing_steps": self.processing_steps,
            "dependencies": {
                "database_repository": type(self.database_repository).__name__,
                "peg_calculator": type(self.peg_calculator).__name__,
            },
        }

    def _validate_time_ranges(self, time_ranges: Tuple[datetime, datetime, datetime, datetime]) -> None:
        """
        ?œê°„ ë²”ìœ„ ? íš¨??ê²€ì¦?

        Args:
            time_ranges (Tuple): (n1_start, n1_end, n_start, n_end)

        Raises:
            PEGProcessingError: ?œê°„ ë²”ìœ„ê°€ ? íš¨?˜ì? ?Šì? ê²½ìš°
        """
        logger.debug("_validate_time_ranges() ?¸ì¶œ: ?œê°„ ë²”ìœ„ ê²€ì¦?)

        n1_start, n1_end, n_start, n_end = time_ranges

        # ê°?ê¸°ê°„ ?´ì—???œì‘ < ??ê²€ì¦?
        if n1_start >= n1_end:
            raise PEGProcessingError(
                "N-1 ê¸°ê°„???œì‘ ?œê°„?????œê°„ë³´ë‹¤ ??±°??ê°™ìŠµ?ˆë‹¤",
                processing_step="data_validation",
                data_context={"n1_start": n1_start, "n1_end": n1_end},
            )

        if n_start >= n_end:
            raise PEGProcessingError(
                "N ê¸°ê°„???œì‘ ?œê°„?????œê°„ë³´ë‹¤ ??±°??ê°™ìŠµ?ˆë‹¤",
                processing_step="data_validation",
                data_context={"n_start": n_start, "n_end": n_end},
            )

        logger.info("?œê°„ ë²”ìœ„ ê²€ì¦??µê³¼: N-1(%s~%s), N(%s~%s)", n1_start, n1_end, n_start, n_end)

    def _retrieve_raw_peg_data(
        self,
        time_ranges: Tuple[datetime, datetime, datetime, datetime],
        table_config: Dict[str, Any],
        filters: Dict[str, Any],
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        ?°ì´?°ë² ?´ìŠ¤?ì„œ ?ì‹œ PEG ?°ì´??ì¡°íšŒ

        Args:
            time_ranges (Tuple): (n1_start, n1_end, n_start, n_end)
            table_config (Dict[str, Any]): ?Œì´ë¸?ë°?ì»¬ëŸ¼ ?¤ì •
            filters (Dict[str, Any]): ?„í„° ì¡°ê±´

        Returns:
            Tuple[pd.DataFrame, pd.DataFrame]: (n1_df, n_df)

        Raises:
            PEGProcessingError: ?°ì´??ì¡°íšŒ ?¤íŒ¨ ??
        """
        logger.debug("_retrieve_raw_peg_data() ?¸ì¶œ: ?ì‹œ ?°ì´??ì¡°íšŒ ?œì‘")

        try:
            n1_start, n1_end, n_start, n_end = time_ranges

            table_name = table_config.get("table", "summary")
            columns = table_config.get(
                "columns",
                {
                    "time": "datetime",
                    "peg_name": "peg_name",
                    "value": "value",
                    "ne": "ne",
                    "cellid": "cellid",
                    "host": "host",
                },
            )
            data_limit = table_config.get("data_limit")

            # N-1 ê¸°ê°„ ?°ì´??ì¡°íšŒ
            logger.info("N-1 ê¸°ê°„ ?°ì´??ì¡°íšŒ: %s ~ %s", n1_start, n1_end)
            n1_data = self.database_repository.fetch_peg_data(
                table_name=table_name, columns=columns, time_range=(n1_start, n1_end), filters=filters, limit=data_limit
            )

            # N ê¸°ê°„ ?°ì´??ì¡°íšŒ
            logger.info("N ê¸°ê°„ ?°ì´??ì¡°íšŒ: %s ~ %s", n_start, n_end)
            n_data = self.database_repository.fetch_peg_data(
                table_name=table_name, columns=columns, time_range=(n_start, n_end), filters=filters, limit=data_limit
            )

            # DataFrame ë³€??
            n1_df = pd.DataFrame(n1_data)
            n_df = pd.DataFrame(n_data)

            logger.info("?ì‹œ ?°ì´??ì¡°íšŒ ?„ë£Œ: N-1=%d?? N=%d??, len(n1_df), len(n_df))
            return n1_df, n_df

        except Exception as e:
            raise PEGProcessingError(
                f"?ì‹œ PEG ?°ì´??ì¡°íšŒ ?¤íŒ¨: {e}",
                processing_step="data_retrieval",
                data_context={
                    "table_name": table_name,
                    "time_ranges": str(time_ranges)[:100],
                    "filters": str(filters)[:100],
                },
            ) from e

    def _validate_raw_data(self, n1_df: pd.DataFrame, n_df: pd.DataFrame) -> None:
        """
        ?ì‹œ ?°ì´??? íš¨??ê²€ì¦?

        Args:
            n1_df (pd.DataFrame): N-1 ê¸°ê°„ ?°ì´??
            n_df (pd.DataFrame): N ê¸°ê°„ ?°ì´??

        Raises:
            PEGProcessingError: ?°ì´?°ê? ? íš¨?˜ì? ?Šì? ê²½ìš°
        """
        logger.debug("_validate_raw_data() ?¸ì¶œ: ?ì‹œ ?°ì´??ê²€ì¦?)

        # ë¹??°ì´??ê²½ê³ 
        if len(n1_df) == 0 or len(n_df) == 0:
            logger.warning(
                "?œìª½ ê¸°ê°„ ?°ì´?°ê? ë¹„ì–´?ˆìŒ: N-1=%d?? N=%d??- ë¶„ì„ ? ë¢°?„ê? ??•„ì§????ˆìŒ", len(n1_df), len(n_df)
            )

        # ?„ìˆ˜ ì»¬ëŸ¼ ?•ì¸
        required_columns = ["peg_name", "value"]

        for df_name, df in [("N-1", n1_df), ("N", n_df)]:
            if not df.empty:
                missing_columns = [col for col in required_columns if col not in df.columns]
                if missing_columns:
                    raise PEGProcessingError(
                        f"{df_name} ?°ì´?°ì— ?„ìˆ˜ ì»¬ëŸ¼???„ë½?˜ì—ˆ?µë‹ˆ?? {missing_columns}",
                        processing_step="data_validation",
                        data_context={"period": df_name, "columns": list(df.columns)},
                    )

        logger.info("?ì‹œ ?°ì´??ê²€ì¦??„ë£Œ: N-1=%d?? N=%d??, len(n1_df), len(n_df))

    def _process_with_calculator(
        self, n1_df: pd.DataFrame, n_df: pd.DataFrame, peg_config: Dict[str, Any]
    ) -> pd.DataFrame:
        """
        PEGCalculatorë¥??¬ìš©???°ì´??ì²˜ë¦¬

        Args:
            n1_df (pd.DataFrame): N-1 ê¸°ê°„ ?°ì´??
            n_df (pd.DataFrame): N ê¸°ê°„ ?°ì´??
            peg_config (Dict[str, Any]): PEG ?¤ì •

        Returns:
            pd.DataFrame: ì²˜ë¦¬??PEG ?°ì´??

        Raises:
            PEGProcessingError: PEG ì²˜ë¦¬ ?¤íŒ¨ ??
        """
        logger.debug("_process_with_calculator() ?¸ì¶œ: PEGCalculator ì²˜ë¦¬ ?œì‘")

        try:
            # ?„ì¬??ê°„ë‹¨??ì§‘ê³„ ë¡œì§ (PEGCalculator ?„ì „ ?µí•©?€ ì¶”í›„)
            # N-1 ê¸°ê°„ ì§‘ê³„
            if not n1_df.empty:
                n1_aggregated = n1_df.groupby("peg_name")["value"].mean().reset_index()
                n1_aggregated["period"] = "N-1"
            else:
                n1_aggregated = pd.DataFrame(columns=["peg_name", "value", "period"])

            # N ê¸°ê°„ ì§‘ê³„
            if not n_df.empty:
                n_aggregated = n_df.groupby("peg_name")["value"].mean().reset_index()
                n_aggregated["period"] = "N"
            else:
                n_aggregated = pd.DataFrame(columns=["peg_name", "value", "period"])

            # ê²°í•© ë°?ë³€?”ìœ¨ ê³„ì‚°
            combined_df = pd.concat([n1_aggregated, n_aggregated], ignore_index=True)

            # ë³€?”ìœ¨ ê³„ì‚° ë¡œì§
            if not combined_df.empty:
                # pivot?¼ë¡œ N-1, N ê¸°ê°„??ì»¬ëŸ¼?¼ë¡œ ë³€??
                pivot_df = combined_df.pivot(index="peg_name", columns="period", values="value").fillna(0)

                if "N-1" in pivot_df.columns and "N" in pivot_df.columns:
                    pivot_df["change_pct"] = ((pivot_df["N"] - pivot_df["N-1"]) / pivot_df["N-1"] * 100).fillna(0)
                else:
                    pivot_df["change_pct"] = 0

                # ìµœì¢… ?•íƒœë¡?ë³€??
                processed_df = pivot_df.reset_index()
                processed_df = processed_df.melt(
                    id_vars=["peg_name", "change_pct"],
                    value_vars=["N-1", "N"],
                    var_name="period",
                    value_name="avg_value",
                )
            else:
                processed_df = pd.DataFrame(columns=["peg_name", "period", "avg_value", "change_pct"])

            logger.info("PEGCalculator ì²˜ë¦¬ ?„ë£Œ: %d??, len(processed_df))
            return processed_df

        except Exception as e:
            raise PEGProcessingError(
                f"PEGCalculator ì²˜ë¦¬ ?¤íŒ¨: {e}",
                processing_step="aggregation",
                data_context={"n1_rows": len(n1_df), "n_rows": len(n_df)},
            ) from e

    def process_peg_data(
        self,
        time_ranges: Tuple[datetime, datetime, datetime, datetime],
        table_config: Dict[str, Any],
        filters: Dict[str, Any],
        peg_config: Optional[Dict[str, Any]] = None,
    ) -> pd.DataFrame:
        """
        ?„ì²´ PEG ?°ì´??ì²˜ë¦¬ ?Œí¬?Œë¡œ???¤í–‰

        Args:
            time_ranges (Tuple): (n1_start, n1_end, n_start, n_end)
            table_config (Dict[str, Any]): ?Œì´ë¸?ë°?ì»¬ëŸ¼ ?¤ì •
            filters (Dict[str, Any]): ?„í„° ì¡°ê±´
            peg_config (Optional[Dict[str, Any]]): PEG ?¤ì •

        Returns:
            pd.DataFrame: ì²˜ë¦¬??PEG ?°ì´??

        Raises:
            PEGProcessingError: ì²˜ë¦¬ ?¤íŒ¨ ??
        """
        logger.info("process_peg_data() ?¸ì¶œ: PEG ?°ì´??ì²˜ë¦¬ ?Œí¬?Œë¡œ???œì‘")

        try:
            # 1?¨ê³„: ?œê°„ ë²”ìœ„ ê²€ì¦?
            logger.info("1?¨ê³„: ?œê°„ ë²”ìœ„ ê²€ì¦?)
            self._validate_time_ranges(time_ranges)

            # 2?¨ê³„: ?ì‹œ ?°ì´??ì¡°íšŒ
            logger.info("2?¨ê³„: ?ì‹œ ?°ì´??ì¡°íšŒ")
            n1_df, n_df = self._retrieve_raw_peg_data(time_ranges, table_config, filters)

            # 3?¨ê³„: ?ì‹œ ?°ì´??ê²€ì¦?
            logger.info("3?¨ê³„: ?ì‹œ ?°ì´??ê²€ì¦?)
            self._validate_raw_data(n1_df, n_df)

            # 4?¨ê³„: PEGCalculator ì²˜ë¦¬
            logger.info("4?¨ê³„: PEGCalculator ì²˜ë¦¬")
            processed_df = self._process_with_calculator(n1_df, n_df, peg_config or {})

            logger.info("PEG ?°ì´??ì²˜ë¦¬ ?Œí¬?Œë¡œ???„ë£Œ: %d??, len(processed_df))
            return processed_df

        except PEGProcessingError:
            # ?´ë? PEGProcessingError??ê²½ìš° ê·¸ë?ë¡??„íŒŒ
            raise

        except Exception as e:
            # ?ˆìƒì¹?ëª»í•œ ?¤ë¥˜ë¥?PEGProcessingErrorë¡?ë³€??
            raise PEGProcessingError(
                f"PEG ?°ì´??ì²˜ë¦¬ ì¤??ˆìƒì¹?ëª»í•œ ?¤ë¥˜: {e}",
                processing_step="unknown",
                data_context={"time_ranges": str(time_ranges)[:100]},
            ) from e

    def get_processing_status(self) -> Dict[str, Any]:
        """ì²˜ë¦¬ ?íƒœ ?•ë³´ ë°˜í™˜"""
        return {
            "processing_steps": self.processing_steps,
            "step_count": len(self.processing_steps),
            "dependencies_ready": {
                "database_repository": self.database_repository is not None,
                "peg_calculator": self.peg_calculator is not None,
            },
        }

    def close(self) -> None:
        """ë¦¬ì†Œ???•ë¦¬"""
        if hasattr(self.database_repository, "disconnect"):
            self.database_repository.disconnect()

        logger.info("PEGProcessingService ë¦¬ì†Œ???•ë¦¬ ?„ë£Œ")

    def __enter__(self):
        """ì»¨í…?¤íŠ¸ ë§¤ë‹ˆ?€ ì§„ì…"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """ì»¨í…?¤íŠ¸ ë§¤ë‹ˆ?€ ì¢…ë£Œ"""
        self.close()

        # ?ˆì™¸ ë°œìƒ ??ë¡œê·¸ ê¸°ë¡
        if exc_type:
            logger.error("PEGProcessingService ì»¨í…?¤íŠ¸?ì„œ ?ˆì™¸ ë°œìƒ: %s", exc_val)

        return False  # ?ˆì™¸ë¥??¤ì‹œ ë°œìƒ?œí‚´
