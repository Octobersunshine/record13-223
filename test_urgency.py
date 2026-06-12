from dispatch_service import (
    DispatchService,
    Worker,
    RepairOrder,
    Location,
    RepairType,
    UrgencyLevel,
    AlertSeverity,
    DEFAULT_URGENCY_MAP,
)


def test_urgency_default_mapping():
    print("=" * 60)
    print("验证1: 默认紧急程度映射 — 漏水/断电为CRITICAL，刷漆为LOW")
    print("=" * 60)

    assert DEFAULT_URGENCY_MAP[RepairType.PLUMBING] == UrgencyLevel.CRITICAL
    assert DEFAULT_URGENCY_MAP[RepairType.ELECTRICAL] == UrgencyLevel.CRITICAL
    assert DEFAULT_URGENCY_MAP[RepairType.DOOR_LOCK] == UrgencyLevel.HIGH
    assert DEFAULT_URGENCY_MAP[RepairType.HVAC] == UrgencyLevel.MEDIUM
    assert DEFAULT_URGENCY_MAP[RepairType.WINDOW] == UrgencyLevel.MEDIUM
    assert DEFAULT_URGENCY_MAP[RepairType.PAINTING] == UrgencyLevel.LOW
    assert DEFAULT_URGENCY_MAP[RepairType.CARPENTRY] == UrgencyLevel.LOW

    print("  ✓ PLUMBING=CRITICAL, ELECTRICAL=CRITICAL")
    print("  ✓ DOOR_LOCK=HIGH")
    print("  ✓ HVAC=MEDIUM, WINDOW=MEDIUM")
    print("  ✓ PAINTING=LOW, CARPENTRY=LOW")
    print()


def test_urgency_auto_derived_from_repair_type():
    print("=" * 60)
    print("验证2: 订单自动从报修类型推导紧急程度")
    print("=" * 60)

    order_plumbing = RepairOrder(
        order_id="O1", repair_type=RepairType.PLUMBING,
        description="漏水", location=Location(0, 0),
    )
    order_painting = RepairOrder(
        order_id="O2", repair_type=RepairType.PAINTING,
        description="刷漆", location=Location(0, 0),
    )

    ds = DispatchService()
    assert order_plumbing.get_urgency(ds.urgency_map) == UrgencyLevel.CRITICAL
    assert order_painting.get_urgency(ds.urgency_map) == UrgencyLevel.LOW

    print(f"  ✓ 漏水工单紧急程度: {order_plumbing.get_urgency(ds.urgency_map).name}")
    print(f"  ✓ 刷漆工单紧急程度: {order_painting.get_urgency(ds.urgency_map).name}")
    print()


def test_urgency_manual_override():
    print("=" * 60)
    print("验证3: 手动指定紧急程度覆盖默认推导")
    print("=" * 60)

    order = RepairOrder(
        order_id="O1", repair_type=RepairType.PAINTING,
        description="特殊刷漆", location=Location(0, 0),
        urgency=UrgencyLevel.HIGH,
    )
    ds = DispatchService()

    assert order.get_urgency(ds.urgency_map) == UrgencyLevel.HIGH

    print(f"  ✓ 手动指定HIGH覆盖默认LOW: {order.get_urgency(ds.urgency_map).name}")
    print()


def test_effective_priority():
    print("=" * 60)
    print("验证4: 综合优先级 = priority × urgency_value")
    print("=" * 60)

    ds = DispatchService()

    order_leak = RepairOrder(
        order_id="O1", repair_type=RepairType.PLUMBING,
        description="漏水", location=Location(0, 0), priority=1,
    )
    order_paint = RepairOrder(
        order_id="O2", repair_type=RepairType.PAINTING,
        description="刷漆", location=Location(0, 0), priority=1,
    )
    order_leak_p2 = RepairOrder(
        order_id="O3", repair_type=RepairType.PLUMBING,
        description="大漏水", location=Location(0, 0), priority=2,
    )

    ep_leak = ds._get_effective_priority(order_leak)
    ep_paint = ds._get_effective_priority(order_paint)
    ep_leak_p2 = ds._get_effective_priority(order_leak_p2)

    assert ep_leak == 1 * 4, "漏水priority=1, urgency=4 → 4"
    assert ep_paint == 1 * 1, "刷漆priority=1, urgency=1 → 1"
    assert ep_leak_p2 == 2 * 4, "漏水priority=2, urgency=4 → 8"

    print(f"  ✓ 漏水(p=1): 综合优先级={ep_leak}")
    print(f"  ✓ 刷漆(p=1): 综合优先级={ep_paint}")
    print(f"  ✓ 漏水(p=2): 综合优先级={ep_leak_p2}")
    print(f"  ✓ 漏水(p=1) 优先于 刷漆(p=1): {ep_leak > ep_paint}")
    print()


def test_queue_ordering_by_urgency():
    print("=" * 60)
    print("验证5: 等待队列按综合优先级排序 — 漏水优先于刷漆")
    print("=" * 60)

    ds = DispatchService()
    ds.add_worker(
        Worker(
            worker_id="W1", name="通用师傅",
            skills=[RepairType.PLUMBING, RepairType.PAINTING, RepairType.ELECTRICAL],
            location=Location(0, 0), current_tasks=1, max_tasks=1,
        )
    )

    order_paint = RepairOrder(
        order_id="P01", repair_type=RepairType.PAINTING,
        description="墙面刷漆", location=Location(0, 0), priority=2,
    )
    order_leak = RepairOrder(
        order_id="L01", repair_type=RepairType.PLUMBING,
        description="水管漏水", location=Location(0, 0), priority=1,
    )

    ds.add_order(order_paint)
    ds.add_order(order_leak)
    ds.assign_order("P01")
    ds.assign_order("L01")

    assert order_paint.status == "waiting"
    assert order_leak.status == "waiting"

    waiting = ds.get_waiting_orders()
    waiting_ids = [o.order_id for o in waiting]

    assert waiting_ids[0] == "L01", (
        f"漏水工单应排在队首，实际队首: {waiting_ids[0]}"
    )
    assert waiting_ids[1] == "P01", (
        f"刷漆工单应排在第二，实际: {waiting_ids[1]}"
    )

    print(f"  ✓ 等待队列顺序: {waiting_ids}")
    print(f"  ✓ 漏水(综合优先级={ds._get_effective_priority(order_leak):.0f})"
          f" > 刷漆(综合优先级={ds._get_effective_priority(order_paint):.0f})")
    print()


def test_queue_urgency_ordering_with_same_priority():
    print("=" * 60)
    print("验证6: 同priority下，CRITICAL紧急程度优先出队")
    print("=" * 60)

    ds = DispatchService()
    ds.add_worker(
        Worker(
            worker_id="W1", name="通用师傅",
            skills=[RepairType.PLUMBING, RepairType.PAINTING, RepairType.ELECTRICAL, RepairType.WINDOW],
            location=Location(0, 0), current_tasks=1, max_tasks=1,
        )
    )

    order1 = RepairOrder(
        order_id="PAINT01", repair_type=RepairType.PAINTING,
        description="刷漆", location=Location(0, 0), priority=1,
    )
    order2 = RepairOrder(
        order_id="WINDOW01", repair_type=RepairType.WINDOW,
        description="窗户维修", location=Location(0, 0), priority=1,
    )
    order3 = RepairOrder(
        order_id="ELEC01", repair_type=RepairType.ELECTRICAL,
        description="电路故障", location=Location(0, 0), priority=1,
    )

    ds.add_order(order1)
    ds.add_order(order2)
    ds.add_order(order3)
    for oid in ["PAINT01", "WINDOW01", "ELEC01"]:
        ds.assign_order(oid)

    assert all(ds.orders[oid].status == "waiting" for oid in ["PAINT01", "WINDOW01", "ELEC01"])

    ds.workers[0].current_tasks = 0
    results = ds.retry_waiting_queue()

    assert results[0].worker is not None, "第一个重试应成功分配"
    assert ds.orders["ELEC01"].status == "assigned", (
        "断电工单(URGENCY=CRITICAL)应第一个被分配"
    )

    print(f"  ✓ 重试顺序:")
    for r in results:
        if r.worker:
            oid = None
            for k, v in ds.orders.items():
                if v.assigned_worker == r.worker.worker_id and v.status == "assigned":
                    oid = k
                    break
            print(f"    {oid}: {r.reason}")
    print()


def test_urgency_in_scoring():
    print("=" * 60)
    print("验证7: 紧急程度影响综合评分 — 同工人对漏水vs刷漆的得分不同")
    print("=" * 60)

    ds = DispatchService()

    order_leak = RepairOrder(
        order_id="L01", repair_type=RepairType.PLUMBING,
        description="漏水", location=Location(1, 1),
    )
    order_paint = RepairOrder(
        order_id="P01", repair_type=RepairType.PAINTING,
        description="刷漆", location=Location(1, 1),
    )

    worker = Worker(
        worker_id="W1", name="全能师傅",
        skills=[RepairType.PLUMBING, RepairType.PAINTING],
        location=Location(0, 0),
    )

    score_leak = ds._calculate_total_score(worker, order_leak)
    score_paint = ds._calculate_total_score(worker, order_paint)

    assert score_leak[0] > score_paint[0], (
        f"漏水工单得分({score_leak[0]:.4f})应高于刷漆({score_paint[0]:.4f})"
    )

    print(f"  ✓ 漏水工单总分: {score_leak[0]:.4f} (urgency_score={score_leak[5]:.2f})")
    print(f"  ✓ 刷漆工单总分: {score_paint[0]:.4f} (urgency_score={score_paint[5]:.2f})")
    print(f"  ✓ 同工人同距离下，漏水得分 > 刷漆得分")
    print()


def test_alert_severity_with_urgency():
    print("=" * 60)
    print("验证8: 告警级别结合紧急程度 — 漏水等待触发CRITICAL，刷漆为MEDIUM")
    print("=" * 60)

    ds1 = DispatchService()
    order_leak = RepairOrder(
        order_id="L01", repair_type=RepairType.PLUMBING,
        description="漏水", location=Location(1, 1),
    )
    ds1.add_order(order_leak)
    ds1.assign_order("L01")

    queue_alerts_leak = [a for a in ds1.get_alerts() if a.title == "工单进入等待队列"]
    assert len(queue_alerts_leak) == 1
    assert queue_alerts_leak[0].severity == AlertSeverity.CRITICAL, (
        f"漏水等待应为CRITICAL，实际: {queue_alerts_leak[0].severity}"
    )

    ds2 = DispatchService()
    order_paint = RepairOrder(
        order_id="P01", repair_type=RepairType.PAINTING,
        description="刷漆", location=Location(1, 1),
    )
    ds2.add_order(order_paint)
    ds2.assign_order("P01")

    queue_alerts_paint = [a for a in ds2.get_alerts() if a.title == "工单进入等待队列"]
    assert len(queue_alerts_paint) == 1
    assert queue_alerts_paint[0].severity == AlertSeverity.MEDIUM, (
        f"刷漆等待应为MEDIUM，实际: {queue_alerts_paint[0].severity}"
    )

    print(f"  ✓ 漏水工单等待告警: {queue_alerts_leak[0].severity.value}")
    print(f"  ✓ 刷漆工单等待告警: {queue_alerts_paint[0].severity.value}")
    print()


def test_custom_urgency_map():
    print("=" * 60)
    print("验证9: 自定义紧急程度映射")
    print("=" * 60)

    custom_map = {
        RepairType.PLUMBING: UrgencyLevel.HIGH,
        RepairType.ELECTRICAL: UrgencyLevel.HIGH,
        RepairType.PAINTING: UrgencyLevel.LOW,
        RepairType.HVAC: UrgencyLevel.CRITICAL,
        RepairType.DOOR_LOCK: UrgencyLevel.MEDIUM,
        RepairType.WINDOW: UrgencyLevel.LOW,
        RepairType.CARPENTRY: UrgencyLevel.LOW,
    }

    ds = DispatchService(urgency_map=custom_map)
    order_hvac = RepairOrder(
        order_id="H01", repair_type=RepairType.HVAC,
        description="空调故障", location=Location(0, 0),
    )
    assert order_hvac.get_urgency(ds.urgency_map) == UrgencyLevel.CRITICAL

    order_leak = RepairOrder(
        order_id="L01", repair_type=RepairType.PLUMBING,
        description="漏水", location=Location(0, 0),
    )
    assert order_leak.get_urgency(ds.urgency_map) == UrgencyLevel.HIGH

    print(f"  ✓ 自定义映射: HVAC→CRITICAL (原MEDIUM)")
    print(f"  ✓ 自定义映射: PLUMBING→HIGH (原CRITICAL)")
    print()


def test_urgency_boosts_low_priority_leak_over_high_priority_paint():
    print("=" * 60)
    print("验证10: 漏水(p=1)优先于刷漆(p=3) — 紧急程度逆转优先级")
    print("=" * 60)

    ds = DispatchService()
    ds.add_worker(
        Worker(
            worker_id="W1", name="通用师傅",
            skills=[RepairType.PLUMBING, RepairType.PAINTING],
            location=Location(0, 0), current_tasks=1, max_tasks=1,
        )
    )

    order_paint_high = RepairOrder(
        order_id="PH01", repair_type=RepairType.PAINTING,
        description="急刷漆", location=Location(0, 0), priority=3,
    )
    order_leak_low = RepairOrder(
        order_id="LL01", repair_type=RepairType.PLUMBING,
        description="小漏水", location=Location(0, 0), priority=1,
    )

    ds.add_order(order_paint_high)
    ds.add_order(order_leak_low)
    ds.assign_order("PH01")
    ds.assign_order("LL01")

    ep_paint = ds._get_effective_priority(order_paint_high)
    ep_leak = ds._get_effective_priority(order_leak_low)

    assert ep_leak > ep_paint, (
        f"漏水综合优先级({ep_leak})应大于刷漆({ep_paint})"
    )

    waiting = ds.get_waiting_orders()
    assert waiting[0].order_id == "LL01", "漏水工单应在队首"

    ds.workers[0].current_tasks = 0
    results = ds.retry_waiting_queue()

    assert ds.orders["LL01"].status == "assigned", "漏水工单应先被分配"
    print(f"  ✓ 刷漆(p=3, urgency=LOW):   综合优先级 = {ep_paint}")
    print(f"  ✓ 漏水(p=1, urgency=CRITICAL): 综合优先级 = {ep_leak}")
    print(f"  ✓ 漏水虽然priority=1，但紧急程度逆转优先级，先被分配")
    print()


def test_reason_includes_urgency():
    print("=" * 60)
    print("验证11: AssignmentResult.reason 包含紧急程度信息")
    print("=" * 60)

    ds = DispatchService()
    ds.add_worker(
        Worker(
            worker_id="W1", name="水电工",
            skills=[RepairType.PLUMBING],
            location=Location(0, 0),
        )
    )
    order = RepairOrder(
        order_id="L01", repair_type=RepairType.PLUMBING,
        description="厨房漏水", location=Location(0, 0),
    )
    ds.add_order(order)
    result = ds.assign_order("L01")

    assert "紧急程度" in result.reason, "reason应包含紧急程度信息"
    assert "CRITICAL" in result.reason, "漏水应为CRITICAL"

    print(f"  ✓ reason: {result.reason}")
    print()


def run_all():
    test_urgency_default_mapping()
    test_urgency_auto_derived_from_repair_type()
    test_urgency_manual_override()
    test_effective_priority()
    test_queue_ordering_by_urgency()
    test_queue_urgency_ordering_with_same_priority()
    test_urgency_in_scoring()
    test_alert_severity_with_urgency()
    test_custom_urgency_map()
    test_urgency_boosts_low_priority_leak_over_high_priority_paint()
    test_reason_includes_urgency()

    print("=" * 60)
    print("全部 11 个紧急程度优先策略测试通过 ✓")
    print("=" * 60)


if __name__ == "__main__":
    run_all()
