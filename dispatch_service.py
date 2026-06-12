from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from enum import Enum
from math import sqrt
from datetime import datetime


class RepairType(str, Enum):
    PLUMBING = "plumbing"
    ELECTRICAL = "electrical"
    CARPENTRY = "carpentry"
    PAINTING = "painting"
    HVAC = "hvac"
    DOOR_LOCK = "door_lock"
    WINDOW = "window"


@dataclass
class Location:
    x: float
    y: float

    def distance_to(self, other: "Location") -> float:
        return sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)


@dataclass
class Worker:
    worker_id: str
    name: str
    skills: List[RepairType]
    location: Location
    current_tasks: int = 0
    max_tasks: int = 5
    is_online: bool = True
    rating: float = 5.0


@dataclass
class RepairOrder:
    order_id: str
    repair_type: RepairType
    description: str
    location: Location
    priority: int = 1
    created_at: datetime = field(default_factory=datetime.now)
    assigned_worker: Optional[str] = None
    status: str = "pending"


@dataclass
class AssignmentResult:
    worker: Optional[Worker]
    score: float
    skill_match: bool
    distance: float
    task_load_ratio: float
    reason: str


class DispatchService:
    def __init__(
        self,
        workers: Optional[List[Worker]] = None,
        skill_weight: float = 0.4,
        distance_weight: float = 0.35,
        load_weight: float = 0.2,
        rating_weight: float = 0.05,
        max_distance: float = 10.0,
    ):
        self.workers: List[Worker] = workers or []
        self.orders: Dict[str, RepairOrder] = {}
        self.skill_weight = skill_weight
        self.distance_weight = distance_weight
        self.load_weight = load_weight
        self.rating_weight = rating_weight
        self.max_distance = max_distance
        self._worker_orders: Dict[str, List[str]] = {}

    def add_worker(self, worker: Worker) -> None:
        self.workers.append(worker)
        self._worker_orders[worker.worker_id] = []

    def add_order(self, order: RepairOrder) -> RepairOrder:
        self.orders[order.order_id] = order
        return order

    def _calculate_skill_score(self, worker: Worker, order: RepairOrder) -> float:
        if order.repair_type in worker.skills:
            return 1.0
        return 0.0

    def _calculate_distance_score(self, worker: Worker, order: RepairOrder) -> float:
        distance = worker.location.distance_to(order.location)
        if distance > self.max_distance:
            return 0.0
        return 1.0 - (distance / self.max_distance)

    def _calculate_load_score(self, worker: Worker) -> float:
        if worker.max_tasks <= 0:
            return 0.0
        load_ratio = worker.current_tasks / worker.max_tasks
        return 1.0 - load_ratio

    def _calculate_rating_score(self, worker: Worker) -> float:
        return max(0.0, min(worker.rating, 5.0)) / 5.0

    def _calculate_total_score(
        self, worker: Worker, order: RepairOrder
    ) -> Tuple[float, float, float, float, float]:
        skill_score = self._calculate_skill_score(worker, order)
        distance_score = self._calculate_distance_score(worker, order)
        load_score = self._calculate_load_score(worker)
        rating_score = self._calculate_rating_score(worker)

        total_score = (
            skill_score * self.skill_weight
            + distance_score * self.distance_weight
            + load_score * self.load_weight
            + rating_score * self.rating_weight
        )

        return total_score, skill_score, distance_score, load_score, rating_score

    def _get_eligible_workers(self, order: RepairOrder) -> List[Worker]:
        return [
            w
            for w in self.workers
            if w.is_online and w.current_tasks < w.max_tasks
        ]

    def assign_order(self, order_id: str) -> AssignmentResult:
        if order_id not in self.orders:
            return AssignmentResult(
                worker=None,
                score=0.0,
                skill_match=False,
                distance=0.0,
                task_load_ratio=0.0,
                reason=f"订单 {order_id} 不存在",
            )

        order = self.orders[order_id]

        if order.status != "pending" or order.assigned_worker:
            return AssignmentResult(
                worker=None,
                score=0.0,
                skill_match=False,
                distance=0.0,
                task_load_ratio=0.0,
                reason=f"订单 {order_id} 已被分配或处理中",
            )

        eligible_workers = self._get_eligible_workers(order)
        if not eligible_workers:
            return AssignmentResult(
                worker=None,
                score=0.0,
                skill_match=False,
                distance=0.0,
                task_load_ratio=0.0,
                reason="当前没有可用的在线维修工",
            )

        candidates: List[Tuple[Worker, AssignmentResult]] = []
        best_skill_match = False

        for worker in eligible_workers:
            total_score, skill_score, distance_score, load_score, rating_score = (
                self._calculate_total_score(worker, order)
            )
            distance = worker.location.distance_to(order.location)
            skill_match = skill_score > 0

            if skill_match:
                best_skill_match = True

            result = AssignmentResult(
                worker=worker,
                score=round(total_score, 4),
                skill_match=skill_match,
                distance=round(distance, 2),
                task_load_ratio=round(
                    worker.current_tasks / max(worker.max_tasks, 1), 2
                ),
                reason=(
                    f"技能匹配:{skill_score:.0%}, "
                    f"距离得分:{distance_score:.0%}, "
                    f"负载得分:{load_score:.0%}, "
                    f"评分得分:{rating_score:.0%}"
                ),
            )
            candidates.append((worker, result))

        if not best_skill_match:
            return AssignmentResult(
                worker=None,
                score=0.0,
                skill_match=False,
                distance=0.0,
                task_load_ratio=0.0,
                reason="没有找到具备对应技能的维修工",
            )

        candidates = [(w, r) for w, r in candidates if r.skill_match]

        if not candidates:
            return AssignmentResult(
                worker=None,
                score=0.0,
                skill_match=False,
                distance=0.0,
                task_load_ratio=0.0,
                reason="没有找到技能匹配的维修工",
            )

        candidates.sort(key=lambda x: x[1].score, reverse=True)

        best_worker, best_result = candidates[0]
        order.assigned_worker = best_worker.worker_id
        order.status = "assigned"
        best_worker.current_tasks += 1
        self._worker_orders[best_worker.worker_id].append(order_id)

        return best_result

    def complete_order(self, order_id: str, rating: Optional[float] = None) -> bool:
        if order_id not in self.orders:
            return False

        order = self.orders[order_id]
        if order.status != "assigned":
            return False

        if order.assigned_worker:
            for w in self.workers:
                if w.worker_id == order.assigned_worker:
                    if w.current_tasks > 0:
                        w.current_tasks -= 1
                    if rating is not None and 1.0 <= rating <= 5.0:
                        w.rating = round((w.rating + rating) / 2, 2)
                    break

        order.status = "completed"
        return True

    def get_worker_orders(self, worker_id: str) -> List[RepairOrder]:
        return [
            self.orders[oid]
            for oid in self._worker_orders.get(worker_id, [])
        ]

    def rank_all_candidates(self, order_id: str) -> List[AssignmentResult]:
        if order_id not in self.orders:
            return []

        order = self.orders[order_id]
        eligible_workers = self._get_eligible_workers(order)

        results = []
        for worker in eligible_workers:
            total_score, skill_score, distance_score, load_score, rating_score = (
                self._calculate_total_score(worker, order)
            )
            distance = worker.location.distance_to(order.location)
            results.append(
                AssignmentResult(
                    worker=worker,
                    score=round(total_score, 4),
                    skill_match=skill_score > 0,
                    distance=round(distance, 2),
                    task_load_ratio=round(
                        worker.current_tasks / max(worker.max_tasks, 1), 2
                    ),
                    reason=(
                        f"技能匹配:{skill_score:.0%}, "
                        f"距离得分:{distance_score:.0%}, "
                        f"负载得分:{load_score:.0%}, "
                        f"评分得分:{rating_score:.0%}"
                    ),
                )
            )

        results.sort(key=lambda x: x.score, reverse=True)
        return results
