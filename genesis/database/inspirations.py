import logging
import random
from abc import ABC, abstractmethod
from typing import Optional, Callable, Any, List, Set

logger = logging.getLogger(__name__)


class ContextSelectorStrategy(ABC):
    def __init__(
        self,
        client: Any,
        config: Any,
        get_program_func: Callable,
        best_program_id=None,
        get_island_idx_func=None,
    ):
        self.client = client
        self.config = config
        self.get_program = get_program_func
        self.best_program_id = best_program_id
        self.get_island_idx = get_island_idx_func

    @abstractmethod
    def sample_context(self, parent: Any, n: int) -> List[Any]:
        pass


class ArchiveInspirationSelector(ContextSelectorStrategy):
    def sample_context(self, parent: Any, n: int) -> List[Any]:
        if n <= 0:
            return []

        parent_island_idx = (
            self.get_island_idx(parent.id) if self.get_island_idx else None
        )
        inspirations = []
        insp_ids = {parent.id}

        enforce_separation = getattr(self.config, "enforce_island_separation", False)

        # 1. Best program
        if self.best_program_id and self.best_program_id not in insp_ids:
            prog = self.get_program(self.best_program_id)
            if prog and prog.correct:
                if enforce_separation:
                    if prog.island_idx == parent_island_idx:
                        inspirations.append(prog)
                        insp_ids.add(prog.id)
                else:
                    inspirations.append(prog)
                    insp_ids.add(prog.id)

        # 2. Elites from parent's island
        num_elites = max(0, int(n * getattr(self.config, "elite_selection_ratio", 0.3)))
        if num_elites > 0 and len(inspirations) < n and parent_island_idx is not None:
            query = f"""
                SELECT p.id FROM programs p
                JOIN archive a ON p.id = a.program_id
                WHERE p.island_idx = {parent_island_idx} AND p.correct = 1
                ORDER BY p.combined_score DESC LIMIT {num_elites + len(insp_ids)}
            """
            res = self.client.query(query)
            for row in res.result_rows:
                if len(inspirations) >= n:
                    break
                pid = row[0]
                if pid not in insp_ids:
                    prog = self.get_program(pid)
                    if prog:
                        inspirations.append(prog)
                        insp_ids.add(pid)

        # 3. Random correct from parent's island
        if len(inspirations) < n and parent_island_idx is not None:
            needed = n - len(inspirations)
            exclude_ids = ", ".join([f"'{pid}'" for pid in insp_ids])
            query = f"""
                SELECT p.id FROM programs p
                JOIN archive a ON p.id = a.program_id
                WHERE p.island_idx = {parent_island_idx} AND p.correct = 1
                AND p.id NOT IN ({exclude_ids})
                ORDER BY rand() LIMIT {needed}
            """
            res = self.client.query(query)
            for row in res.result_rows:
                prog = self.get_program(row[0])
                if prog:
                    inspirations.append(prog)

        # 4. Fallback global
        if len(inspirations) < n and not enforce_separation:
            needed = n - len(inspirations)
            exclude_ids = ", ".join([f"'{pid}'" for pid in insp_ids])
            query = f"""
                SELECT p.id FROM programs p
                JOIN archive a ON p.id = a.program_id
                WHERE p.correct = 1 AND p.id NOT IN ({exclude_ids})
                ORDER BY rand() LIMIT {needed}
            """
            res = self.client.query(query)
            for row in res.result_rows:
                prog = self.get_program(row[0])
                if prog:
                    inspirations.append(prog)

        return inspirations


class TopKInspirationSelector(ContextSelectorStrategy):
    def sample_context(
        self, parent: Any, excluded_programs: List[Any], k: int
    ) -> List[Any]:
        if k <= 0:
            return []

        parent_island_idx = parent.island_idx
        enforce_separation = getattr(self.config, "enforce_island_separation", False)

        if enforce_separation and parent_island_idx is None:
            return []

        excluded_ids = {parent.id}
        excluded_ids.update(p.id for p in excluded_programs)
        exclude_str = ", ".join([f"'{pid}'" for pid in excluded_ids])

        query = "SELECT p.id FROM programs p JOIN archive a ON p.id = a.program_id WHERE p.correct = 1"
        if enforce_separation and parent_island_idx is not None:
            query += f" AND p.island_idx = {parent_island_idx}"

        if exclude_str:
            query += f" AND p.id NOT IN ({exclude_str})"

        query += " ORDER BY p.combined_score DESC LIMIT 20"  # fetch more to filter

        res = self.client.query(query)
        candidates = []
        for row in res.result_rows:
            prog = self.get_program(row[0])
            if prog:
                candidates.append(prog)

        # Sort in python (already sorted by score, but verify)
        candidates.sort(key=lambda p: p.combined_score or 0.0, reverse=True)
        return candidates[:k]


class CombinedContextSelector:
    def __init__(
        self,
        client,
        config,
        get_program_func,
        best_program_id=None,
        get_island_idx_func=None,
        program_from_row_func=None,
    ):
        self.archive_selector = ArchiveInspirationSelector(
            client, config, get_program_func, best_program_id, get_island_idx_func
        )
        self.topk_selector = TopKInspirationSelector(
            client, config, get_program_func, best_program_id, get_island_idx_func
        )

    def sample_context(self, parent, num_archive, num_topk):
        archive_insp = self.archive_selector.sample_context(parent, num_archive)
        top_k_insp = self.topk_selector.sample_context(parent, archive_insp, num_topk)
        return archive_insp, top_k_insp
