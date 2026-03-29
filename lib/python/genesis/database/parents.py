import json
import logging
import numpy as np
from abc import ABC, abstractmethod
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)


def sample_with_powerlaw(items: list, alpha: float = 1.0) -> int:
    if not items:
        raise ValueError("Empty items list for power-law sampling")
    probs = np.array([(i + 1) ** (-alpha) for i in range(len(items))])
    if np.sum(probs) == 0:
        probs = np.ones(len(items))
    probs = probs / probs.sum()
    return np.random.choice(len(items), p=probs)


def stable_sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + np.exp(-x))
    else:
        return np.exp(x) / (1.0 + np.exp(x))


class ParentSamplingStrategy(ABC):
    def __init__(
        self,
        client: Any,
        config: Any,
        get_program_func: Callable,
        best_program_id=None,
        island_idx=None,
    ):
        self.client = client
        self.config = config
        self.get_program = get_program_func
        self.best_program_id = best_program_id
        self.island_idx = island_idx

    @abstractmethod
    def sample_parent(self) -> Any:
        pass


class PowerLawSamplingStrategy(ParentSamplingStrategy):
    def sample_parent(self) -> Any:
        pid = None

        # Exploitation from archive
        if (
            hasattr(self.config, "exploitation_ratio")
            and np.random.random() < self.config.exploitation_ratio
        ):
            query = "SELECT program_id FROM archive"
            if self.island_idx is not None:
                # Need to join with programs to filter by island
                query = f"""
                    SELECT a.program_id FROM archive a 
                    JOIN programs p ON a.program_id = p.id 
                    WHERE p.island_idx = {self.island_idx}
                """
            res = self.client.query(query)
            archived_ids = [row[0] for row in res.result_rows]

            archived_programs = []
            for pid in archived_ids:
                p = self.get_program(pid)
                if p:
                    archived_programs.append(p)

            if archived_programs:
                archived_programs.sort(
                    key=lambda p: p.combined_score or 0.0, reverse=True
                )
                idx = sample_with_powerlaw(
                    archived_programs, getattr(self.config, "exploitation_alpha", 1.0)
                )
                pid = archived_programs[idx].id

        # Exploration from correct programs
        if not pid:
            query = "SELECT id FROM programs WHERE correct = 1"
            if self.island_idx is not None:
                query += f" AND island_idx = {self.island_idx}"
            query += " ORDER BY combined_score DESC"

            res = self.client.query(query)
            correct_ids = [row[0] for row in res.result_rows]

            correct_programs = []
            for pid in correct_ids:
                p = self.get_program(pid)
                if p:
                    correct_programs.append(p)

            if correct_programs:
                idx = sample_with_powerlaw(
                    correct_programs, getattr(self.config, "exploitation_alpha", 1.0)
                )
                pid = correct_programs[idx].id

        # Exploration from other islands
        if not pid and self.island_idx is None:
            # Pick random island
            res = self.client.query("SELECT DISTINCT island_idx FROM programs")
            islands = [row[0] for row in res.result_rows]
            if islands:
                idx = np.random.choice(islands)
                res = self.client.query(
                    f"SELECT id FROM programs WHERE island_idx = {idx} AND correct = 1 ORDER BY rand() LIMIT 1"
                )
                if res.result_rows:
                    pid = res.result_rows[0][0]

        # Fallbacks
        if not pid and self.best_program_id:
            p = self.get_program(self.best_program_id)
            if p and (self.island_idx is None or p.island_idx == self.island_idx):
                pid = self.best_program_id

        if not pid:
            query = "SELECT id FROM programs WHERE correct = 1"
            if self.island_idx is not None:
                query += f" AND island_idx = {self.island_idx}"
            query += " ORDER BY rand() LIMIT 1"
            res = self.client.query(query)
            if res.result_rows:
                pid = res.result_rows[0][0]

        return self.get_program(pid) if pid else None


class CombinedParentSelector:
    def __init__(
        self,
        client,
        config,
        get_program_func,
        best_program_id=None,
        beam_search_parent_id=None,
        last_iteration=0,
        update_metadata_func=None,
        get_best_program_func=None,
    ):
        self.client = client
        self.config = config
        self.get_program = get_program_func
        self.best_program_id = best_program_id
        # Other params unused in this simplified impl but kept for signature compat

    def sample_parent(self, island_idx=None):
        # Defaulting to PowerLaw for now to save space, logic can be expanded
        strategy = PowerLawSamplingStrategy(
            self.client, self.config, self.get_program, self.best_program_id, island_idx
        )
        parent = strategy.sample_parent()

        if not parent:
            # Fallback
            query = "SELECT id FROM programs WHERE correct = 1 ORDER BY rand() LIMIT 1"
            res = self.client.query(query)
            if res.result_rows:
                return self.get_program(res.result_rows[0][0])
            raise ValueError("No parent found")

        return parent
