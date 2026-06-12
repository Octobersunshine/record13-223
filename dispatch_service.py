from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple, Callable
from enum import Enum
from math import sqrt
from datetime import datetime
import heapq


class RepairType(str, Enum):
    PLUMBING = "plumbing"
    ELECTRICAL = "electrical"
    CARPENTRY = "carpentry"
    PAINTING = "painting"
    HVAC = "hvac"
    DOOR_LOCK = "door_lock"
    WINDOW = "window"


class AlertSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class UrgencyLevel(int, Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


DEFAULT_URGENCY_MAP: Dict[RepairType, UrgencyLevel] = {
    RepairType.PLUMBING: UrgencyLevel.CRITICAL,
    RepairType.ELECTRICAL: UrgencyLevel.CRITICAL,
    RepairType.DOOR_LOCK: UrgencyLevel.HIGH,
    RepairType.HVAC: UrgencyLevel.MEDIUM,
    RepairType.WINDOW: UrgencyLevel.MEDIUM,
    RepairType.CARPENTRY: UrgencyLevel.LOW,
    RepairType.PAINTING: UrgencyLevel.LOW,
}


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
    urgency: Optional[UrgencyLevel] = None
    created_at: datetime = field(default_factory=datetime.now)
    assigned_worker: Optional[str] = None
    status: str = "pending"
    queue_wait_since: Optional[datetime] = None

    def get_urgency(self, urgency_map: Optional[Dict[RepairType, UrgencyLevel]] = None) -> UrgencyLevel:
        if self.urgency is not None:
            return self.urgency
        if urgency_map and self.repair_type in urgency_map:
            return urgency_map[self.repair_type]
        return UrgencyLevel.MEDIUM


@dataclass
class AssignmentResult:
    worker: Optional[Worker] = None
    score: float = 0.0
    skill_match: bool = False
    distance: float = 0.0
    task_load_ratio: float = 0.0
    reason: str = ""
    queued: bool = False


@dataclass
class AdminAlert:
    alert_id: str
    timestamp: datetime
    severity: AlertSeverity
    title: str
    message: str
    order_id: Optional[str] = None
    worker_id: Optional[str] = None
    resolved: bool = False


class DispatchService:
    def __init__(
        self,
        workers: Optional[List[Worker]] = None,
        skill_weight: float = 0.35,
        distance_weight: float = 0.30,
        load_weight: float = 0.15,
        rating_weight: float = 0.05,
        urgency_weight: float = 0.15,
        max_distance: float = 10.0,
        alert_callback: Optional[Callable[[AdminAlert], None]] = None,
        urgency_map: Optional[Dict[RepairType, UrgencyLevel]] = None,
    ):
        self.workers: List[Worker] = workers if workers else []
        self.orders: Dict[str, RepairOrder] = {}
        self.skill_weight = skill_weight
        self.distance_weight = distance_weight
        self.load_weight = load_weight
        self.rating_weight = rating_weight
        self.urgency_weight = urgency_weight
        self.max_distance = max_distance
        self.alert_callback = alert_callback
        self.urgency_map: Dict[RepairType, UrgencyLevel] = urgency_map if urgency_map else dict(DEFAULT_URGENCY_MAP)
        self._worker_orders: Dict[str, List[str]] = {}
        self._waiting_queue: List[Tuple] = []
        self._waiting_set: set = set()
        self._alerts: List[AdminAlert] = []
        self._alert_counter: int = 0

    def add_worker(self, worker: Worker) -> None:
        self.workers.append(worker)
        self._worker_orders[worker.worker_id] = []
        self._retry_waiting_queue()

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

    def _calculate_urgency_score(self, order: RepairOrder) -> float:
        urgency = order.get_urgency(self.urgency_map)
        return urgency.value / UrgencyLevel.CRITICAL.value

    def _get_effective_priority(self, order: RepairOrder) -> float:
        urgency = order.get_urgency(self.urgency_map)
        return order.priority * urgency.value

    def _calculate_total_score(
        self, worker: Worker, order: RepairOrder
    ) -> Tuple[float, float, float, float, float, float]:
        skill_score = self._calculate_skill_score(worker, order)
        distance_score = self._calculate_distance_score(worker, order)
        load_score = self._calculate_load_score(worker)
        rating_score = self._calculate_rating_score(worker)
        urgency_score = self._calculate_urgency_score(order)

        total_score = (
            skill_score * self.skill_weight
            + distance_score * self.distance_weight
            + load_score * self.load_weight
            + rating_score * self.rating_weight
            + urgency_score * self.urgency_weight
        )

        return total_score, skill_score, distance_score, load_score, rating_score, urgency_score

    def _get_eligible_workers(self, order: RepairOrder) -> List[Worker]:
        return [
            w
            for w in self.workers
            if w.is_online and w.current_tasks < w.max_tasks
        ]

    def _raise_alert(
        self,
        severity: AlertSeverity,
        title: str,
        message: str,
        order_id: Optional[str] = None,
        worker_id: Optional[str] = None,
    ) -> Optional[AdminAlert]:
        self._alert_counter += 1
        alert = AdminAlert(
            alert_id=f"ALT{self._alert_counter:06d}",
            timestamp=datetime.now(),
            severity=severity,
            title=title,
            message=message,
            order_id=order_id,
            worker_id=worker_id,
        )
        self._alerts.append(alert)

        if self.alert_callback:
            try:
                self.alert_callback(alert)
            except Exception as e:
                print(f"[告警回调执行失败] {alert.alert_id}: {e}")

        return alert

    def _has_any_online_skill_match(self, order: RepairOrder) -> bool:
        return any(
            order.repair_type in w.skills
            and w.is_online
            and w.current_tasks < w.max_tasks
            for w in self.workers
        )

    def _has_any_skill_match(self, order: RepairOrder) -> bool:
        return any(order.repair_type in w.skills for w in self.workers)

    def _has_online_workers(self) -> bool:
        return any(w.is_online for w in self.workers)

    def _enqueue_waiting(self, order: RepairOrder, reason: str) -> None:
        if order.order_id in self._waiting_set:
            return

        order.status = "waiting"
        order.queue_wait_since = datetime.now()
        effective_priority = self._get_effective_priority(order)
        heapq.heappush(
            self._waiting_queue,
            (-effective_priority, order.created_at.timestamp(), order.order_id),
        )
        self._waiting_set.add(order.order_id)

        urgency = order.get_urgency(self.urgency_map)
        if urgency.value >= UrgencyLevel.CRITICAL.value or effective_priority >= 8:
            alert_severity = AlertSeverity.CRITICAL
        elif urgency.value >= UrgencyLevel.HIGH.value or effective_priority >= 4:
            alert_severity = AlertSeverity.HIGH
        else:
            alert_severity = AlertSeverity.MEDIUM

        self._raise_alert(
            alert_severity,
            "工单进入等待队列",
            f"订单 {order.order_id} ({order.description}) 因【{reason}】进入等待队列，"
            f"优先级 {order.priority}，紧急程度 {urgency.name}，"
            f"综合优先级 {effective_priority:.0f}，当前队列长度 {len(self._waiting_queue)}",
            order_id=order.order_id,
        )

        if not self._has_online_workers():
            self._raise_alert(
                AlertSeverity.CRITICAL,
                "所有维修工离线",
                f"当前没有任何在线维修工，{len(self._waiting_queue)} 个工单正在等待",
            )
            if self._has_any_skill_match(order):
                self._raise_alert(
                    AlertSeverity.HIGH,
                    "对应技能维修工全部不可用",
                    f"订单 {order.order_id} 的报修类型 {order.repair_type.value} "
                    f"存在具备该技能的维修工，但当前均离线或任务已满，请协调上线或释放任务",
                    order_id=order.order_id,
                )
        elif not self._has_any_online_skill_match(order):
            if self._has_any_skill_match(order):
                self._raise_alert(
                    AlertSeverity.HIGH,
                    "对应技能维修工全部不可用",
                    f"订单 {order.order_id} 的报修类型 {order.repair_type.value} "
                    f"存在具备该技能的维修工，但当前均离线或任务已满，请协调上线或释放任务",
                    order_id=order.order_id,
                )
            else:
                self._raise_alert(
                    AlertSeverity.CRITICAL,
                    "无对应技能维修工",
                    f"订单 {order.order_id} 的报修类型 {order.repair_type.value} "
                    f"目前没有任何维修工具备该技能，请紧急协调",
                    order_id=order.order_id,
                )

    def _try_assign_internal(
        self, order: RepairOrder
    ) -> Tuple[Optional[Worker], AssignmentResult]:
        eligible_workers = self._get_eligible_workers(order)

        if not eligible_workers:
            reason = "当前没有可用的在线维修工"
            return None, AssignmentResult(
                worker=None,
                score=0.0,
                skill_match=False,
                distance=0.0,
                task_load_ratio=0.0,
                reason=reason,
                queued=True,
            )

        candidates: List[Tuple[Worker, AssignmentResult]] = []
        best_skill_match = False
        urgency = order.get_urgency(self.urgency_map)

        for worker in eligible_workers:
            total_score, skill_score, distance_score, load_score, rating_score, urgency_score = (
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
                    f"评分得分:{rating_score:.0%}, "
                    f"紧急程度:{urgency.name}({urgency_score:.0%})"
                ),
            )
            candidates.append((worker, result))

        if not best_skill_match:
            reason = "没有找到具备对应技能的维修工"
            return None, AssignmentResult(
                worker=None,
                score=0.0,
                skill_match=False,
                distance=0.0,
                task_load_ratio=0.0,
                reason=reason,
                queued=True,
            )

        candidates = [(w, r) for w, r in candidates if r.skill_match]

        if not candidates:
            reason = "没有找到技能匹配的维修工"
            return None, AssignmentResult(
                worker=None,
                score=0.0,
                skill_match=False,
                distance=0.0,
                task_load_ratio=0.0,
                reason=reason,
                queued=True,
            )

        candidates.sort(key=lambda x: x[1].score, reverse=True)

        best_worker, best_result = candidates[0]
        order.assigned_worker = best_worker.worker_id
        order.status = "assigned"
        best_worker.current_tasks += 1
        self._worker_orders[best_worker.worker_id].append(order.order_id)

        return best_worker, best_result

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

        if order.status == "waiting":
            return AssignmentResult(
                worker=None,
                score=0.0,
                skill_match=False,
                distance=0.0,
                task_load_ratio=0.0,
                reason=f"订单 {order_id} 已在等待队列中",
                queued=True,
            )

        if order.status != "pending" or order.assigned_worker:
            return AssignmentResult(
                worker=None,
                score=0.0,
                skill_match=False,
                distance=0.0,
                task_load_ratio=0.0,
                reason=f"订单 {order_id} 已被分配或处理中",
            )

        best_worker, result = self._try_assign_internal(order)

        if best_worker is None:
            self._enqueue_waiting(order, result.reason)
            result.queued = True

        return result

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
        self._retry_waiting_queue()
        return True

    def set_worker_online(self, worker_id: str, online: bool) -> bool:
        for w in self.workers:
            if w.worker_id == worker_id:
                was_online = w.is_online
                w.is_online = online

                if online and not was_online:
                    self._raise_alert(
                        AlertSeverity.LOW,
                        "维修工上线",
                        f"维修工 {w.name}({worker_id}) 已上线",
                        worker_id=worker_id,
                    )
                    self._retry_waiting_queue()

                elif not online and was_online:
                    self._raise_alert(
                        AlertSeverity.MEDIUM,
                        "维修工离线",
                        f"维修工 {w.name}({worker_id}) 已离线，当前任务数 {w.current_tasks}",
                        worker_id=worker_id,
                    )
                    if w.current_tasks > 0:
                        self._raise_alert(
                            AlertSeverity.HIGH,
                            "离线维修工有待处理工单",
                            f"维修工 {w.name}({worker_id}) 离线时仍有 "
                            f"{w.current_tasks} 个工单未完成，请及时协调转派",
                            worker_id=worker_id,
                        )

                return True
        return False

    def _retry_waiting_queue(self) -> List[AssignmentResult]:
        results = []
        to_retry = []

        while self._waiting_queue:
            _, _, order_id = heapq.heappop(self._waiting_queue)
            self._waiting_set.discard(order_id)

            if order_id not in self.orders:
                continue
            if self.orders[order_id].status != "waiting":
                continue

            order = self.orders[order_id]
            order.status = "pending"
            order.queue_wait_since = None
            to_retry.append(order)

        for order in to_retry:
            result = self.assign_order(order.order_id)
            results.append(result)

        return results

    def retry_single_order(self, order_id: str) -> AssignmentResult:
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

        try:
            if order.status == "waiting":
                order.status = "pending"
                order.queue_wait_since = None
                self._waiting_set.discard(order_id)
                self._waiting_queue = [
                    item for item in self._waiting_queue if item[2] != order_id
                ]
                heapq.heapify(self._waiting_queue)
                return self.assign_order(order_id)

            if order.status == "pending":
                return self.assign_order(order_id)

            return AssignmentResult(
                worker=None,
                score=0.0,
                skill_match=False,
                distance=0.0,
                task_load_ratio=0.0,
                reason=f"订单 {order_id} 状态为 {order.status}，无法重试",
            )
        except Exception as e:
            return AssignmentResult(
                worker=None,
                score=0.0,
                skill_match=False,
                distance=0.0,
                task_load_ratio=0.0,
                reason=f"重试订单 {order_id} 时发生异常: {e}",
            )

    def retry_waiting_queue(self) -> List[AssignmentResult]:
        return self._retry_waiting_queue()

    def get_waiting_orders(self) -> List[RepairOrder]:
        waiting = []
        for _, _, order_id in self._waiting_queue:
            if order_id in self.orders and self.orders[order_id].status == "waiting":
                waiting.append(self.orders[order_id])
        return waiting

    def get_alerts(
        self,
        severity: Optional[AlertSeverity] = None,
        unresolved_only: bool = False,
        limit: int = 50,
    ) -> List[AdminAlert]:
        alerts = reversed(self._alerts)
        if severity:
            alerts = (a for a in alerts if a.severity == severity)
        if unresolved_only:
            alerts = (a for a in alerts if not a.resolved)
        return list(alerts)[:limit]

    def resolve_alert(self, alert_id: str) -> bool:
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.resolved = True
                return True
        return False

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
        urgency = order.get_urgency(self.urgency_map)

        results = []
        for worker in eligible_workers:
            total_score, skill_score, distance_score, load_score, rating_score, urgency_score = (
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
                        f"评分得分:{rating_score:.0%}, "
                        f"紧急程度:{urgency.name}({urgency_score:.0%})"
                    ),
                )
            )

        results.sort(key=lambda x: x.score, reverse=True)
        return results
