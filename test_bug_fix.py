from dispatch_service import (
    DispatchService,
    Worker,
    RepairOrder,
    Location,
    RepairType,
    AssignmentResult,
    AdminAlert,
    AlertSeverity,
)


def test_no_workers_at_all():
    print("=" * 60)
    print("Bug修复验证1: 无任何维修工 → 入队 + 告警不误报'无对应技能'")
    print("=" * 60)
    ds = DispatchService()

    order = RepairOrder(
        order_id="O001",
        repair_type=RepairType.PLUMBING,
        description="厨房漏水",
        location=Location(1, 1),
    )
    ds.add_order(order)
    result = ds.assign_order(order.order_id)

    assert result.queued is True, "订单应进入等待队列"
    assert result.worker is None, "不应分配维修工"
    assert order.status == "waiting", f"状态应为waiting，实际: {order.status}"

    alerts = ds.get_alerts()
    alert_titles = [a.title for a in alerts]

    assert "所有维修工离线" in alert_titles, "应触发'所有维修工离线'告警"
    assert "无对应技能维修工" not in alert_titles, (
        "Bug修复: 无工人时不应误报'无对应技能维修工'"
    )
    assert "工单进入等待队列" in alert_titles, "应触发'工单进入等待队列'告警"

    print(f"  ✓ 订单状态: {order.status}, queued={result.queued}")
    print(f"  ✓ 告警数量: {len(alerts)}")
    for a in alerts:
        print(f"    [{a.severity.value}] {a.title}: {a.message}")
    print(f"  ✓ 确认'无对应技能维修工'告警已消除 (原Bug)")
    print()


def test_offline_workers_with_skill():
    print("=" * 60)
    print("Bug修复验证2: 有技能的工人全部离线 → 精准告警'对应技能维修工全部不可用'")
    print("=" * 60)
    ds = DispatchService()
    ds.add_worker(
        Worker(
            worker_id="W001",
            name="张师傅",
            skills=[RepairType.PLUMBING],
            location=Location(1, 1),
            is_online=False,
        )
    )

    order = RepairOrder(
        order_id="O002",
        repair_type=RepairType.PLUMBING,
        description="水管爆裂",
        location=Location(1, 1),
    )
    ds.add_order(order)
    result = ds.assign_order(order.order_id)

    assert result.queued is True
    assert order.status == "waiting"

    alerts = ds.get_alerts()
    alert_titles = [a.title for a in alerts]

    assert "对应技能维修工全部不可用" in alert_titles, (
        "Bug修复: 技能工人离线时应触发'对应技能维修工全部不可用'告警"
    )
    assert "无对应技能维修工" not in alert_titles, (
        "不应误报'无对应技能维修工'(因为系统中存在该技能工人)"
    )

    print(f"  ✓ 订单状态: {order.status}, queued={result.queued}")
    for a in alerts:
        print(f"    [{a.severity.value}] {a.title}: {a.message}")
    print(f"  ✓ 确认精准告警: '对应技能维修工全部不可用' (原Bug: 误报或漏报)")
    print()


def test_online_workers_full_load_with_skill():
    print("=" * 60)
    print("Bug修复验证3: 有技能的工人在线但满载 → 精准告警'对应技能维修工全部不可用'")
    print("=" * 60)
    ds = DispatchService()
    ds.add_worker(
        Worker(
            worker_id="W001",
            name="张师傅",
            skills=[RepairType.PLUMBING],
            location=Location(1, 1),
            current_tasks=5,
            max_tasks=5,
            is_online=True,
        )
    )

    order = RepairOrder(
        order_id="O003",
        repair_type=RepairType.PLUMBING,
        description="马桶堵塞",
        location=Location(1, 1),
    )
    ds.add_order(order)
    result = ds.assign_order(order.order_id)

    assert result.queued is True
    alerts = ds.get_alerts()
    alert_titles = [a.title for a in alerts]

    assert "对应技能维修工全部不可用" in alert_titles, (
        "Bug修复: 技能工人满载时应触发'对应技能维修工全部不可用'"
    )

    print(f"  ✓ 订单状态: {order.status}, queued={result.queued}")
    for a in alerts:
        print(f"    [{a.severity.value}] {a.title}: {a.message}")
    print()


def test_no_skill_match_at_all():
    print("=" * 60)
    print("验证4: 系统中确实无人具备该技能 → 正确触发'无对应技能维修工'")
    print("=" * 60)
    ds = DispatchService()
    ds.add_worker(
        Worker(
            worker_id="W001",
            name="张师傅",
            skills=[RepairType.ELECTRICAL],
            location=Location(1, 1),
        )
    )

    order = RepairOrder(
        order_id="O004",
        repair_type=RepairType.HVAC,
        description="空调故障",
        location=Location(1, 1),
    )
    ds.add_order(order)
    result = ds.assign_order(order.order_id)

    assert result.queued is True
    alerts = ds.get_alerts()
    alert_titles = [a.title for a in alerts]

    assert "无对应技能维修工" in alert_titles, "确实无人具备技能时应触发该告警"

    print(f"  ✓ 订单状态: {order.status}, queued={result.queued}")
    for a in alerts:
        print(f"    [{a.severity.value}] {a.title}: {a.message}")
    print()


def test_retry_single_order_cleans_queue():
    print("=" * 60)
    print("Bug修复验证5: retry_single_order 正确清理等待队列")
    print("=" * 60)
    ds = DispatchService()
    order = RepairOrder(
        order_id="O005",
        repair_type=RepairType.PLUMBING,
        description="水龙头漏水",
        location=Location(1, 1),
    )
    ds.add_order(order)
    ds.assign_order(order.order_id)

    assert order.status == "waiting", f"应为waiting，实际: {order.status}"
    assert "O005" in ds._waiting_set, "应在等待集合中"
    assert any(item[2] == "O005" for item in ds._waiting_queue), "应在等待队列中"

    ds.add_worker(
        Worker(
            worker_id="W001",
            name="李师傅",
            skills=[RepairType.PLUMBING],
            location=Location(1, 1),
        )
    )

    assert order.status == "assigned", f"添加工人后应自动分配，实际: {order.status}"
    assert order.assigned_worker == "W001"
    assert "O005" not in ds._waiting_set, "分配后应从等待集合移除"
    assert not any(item[2] == "O005" for item in ds._waiting_queue), (
        "Bug修复: 分配后应从等待队列移除"
    )

    print(f"  ✓ 订单自动分配: {order.assigned_worker}")
    print(f"  ✓ 等待集合已清理: O005 not in set")
    print(f"  ✓ 等待队列已清理: O005 not in queue")
    print()


def test_retry_single_order_manual():
    print("=" * 60)
    print("Bug修复验证6: 手动 retry_single_order 正确工作")
    print("=" * 60)
    ds = DispatchService()
    ds.add_worker(
        Worker(
            worker_id="W001",
            name="张师傅",
            skills=[RepairType.ELECTRICAL],
            location=Location(1, 1),
        )
    )

    order = RepairOrder(
        order_id="O006",
        repair_type=RepairType.PLUMBING,
        description="管道堵塞",
        location=Location(1, 1),
    )
    ds.add_order(order)
    ds.assign_order(order.order_id)

    assert order.status == "waiting"

    ds.add_worker(
        Worker(
            worker_id="W002",
            name="赵师傅",
            skills=[RepairType.PLUMBING],
            location=Location(1, 1),
        )
    )

    assert order.status == "assigned", f"应已自动分配，实际: {order.status}"
    assert order.assigned_worker == "W002"

    retry_result = ds.retry_single_order(order.order_id)
    assert "已被分配" in retry_result.reason or "状态为 assigned" in retry_result.reason, (
        "已分配的订单应提示状态不允许重试"
    )

    print(f"  ✓ 自动分配成功: {order.assigned_worker}")
    print(f"  ✓ 重复重试被正确拒绝: {retry_result.reason}")
    print()


def test_complete_order_auto_retry():
    print("=" * 60)
    print("验证7: 完成工单后自动重试等待队列")
    print("=" * 60)
    ds = DispatchService()
    ds.add_worker(
        Worker(
            worker_id="W001",
            name="张师傅",
            skills=[RepairType.PLUMBING],
            location=Location(1, 1),
            current_tasks=5,
            max_tasks=5,
        )
    )

    order1 = RepairOrder(
        order_id="O101",
        repair_type=RepairType.PLUMBING,
        description="已分配工单",
        location=Location(1, 1),
    )
    order1.status = "assigned"
    order1.assigned_worker = "W001"
    ds.add_order(order1)
    ds._worker_orders["W001"] = ["O101"]

    order2 = RepairOrder(
        order_id="O102",
        repair_type=RepairType.PLUMBING,
        description="等待中工单",
        location=Location(1, 1),
    )
    ds.add_order(order2)
    ds.assign_order("O102")

    assert order2.status == "waiting", "任务满时应入队等待"

    ds.complete_order("O101", rating=5.0)

    assert order2.status == "assigned", f"完成工单后应自动分配等待工单，实际: {order2.status}"
    assert order2.assigned_worker == "W001"

    print(f"  ✓ 完成O101后，O102自动分配给 W001")
    print()


def test_set_worker_online_auto_retry():
    print("=" * 60)
    print("验证8: 维修工上线后自动重试等待队列")
    print("=" * 60)
    ds = DispatchService()
    ds.add_worker(
        Worker(
            worker_id="W001",
            name="张师傅",
            skills=[RepairType.PLUMBING],
            location=Location(1, 1),
            is_online=False,
        )
    )

    order = RepairOrder(
        order_id="O201",
        repair_type=RepairType.PLUMBING,
        description="下水道堵塞",
        location=Location(1, 1),
    )
    ds.add_order(order)
    ds.assign_order(order.order_id)

    assert order.status == "waiting"

    ds.set_worker_online("W001", True)

    assert order.status == "assigned", f"工人上线后应自动分配，实际: {order.status}"
    assert order.assigned_worker == "W001"

    alerts = ds.get_alerts()
    online_alert = [a for a in alerts if a.title == "维修工上线"]
    assert len(online_alert) > 0, "应触发'维修工上线'告警"

    print(f"  ✓ 工人上线后自动分配: {order.assigned_worker}")
    print(f"  ✓ 上线告警已触发")
    print()


def test_alert_callback():
    print("=" * 60)
    print("验证9: 告警回调函数正确调用")
    print("=" * 60)
    received_alerts = []

    def on_alert(alert: AdminAlert):
        received_alerts.append(alert)

    ds = DispatchService(alert_callback=on_alert)
    order = RepairOrder(
        order_id="O301",
        repair_type=RepairType.PLUMBING,
        description="测试回调",
        location=Location(1, 1),
    )
    ds.add_order(order)
    ds.assign_order(order.order_id)

    assert len(received_alerts) > 0, "告警回调应被调用"
    assert all(isinstance(a, AdminAlert) for a in received_alerts)

    print(f"  ✓ 回调被调用 {len(received_alerts)} 次")
    for a in received_alerts:
        print(f"    [{a.severity.value}] {a.title}")
    print()


def test_resolve_alerts():
    print("=" * 60)
    print("验证10: 告警解决与过滤")
    print("=" * 60)
    ds = DispatchService()
    order = RepairOrder(
        order_id="O401",
        repair_type=RepairType.PLUMBING,
        description="测试告警解决",
        location=Location(1, 1),
    )
    ds.add_order(order)
    ds.assign_order(order.order_id)

    all_alerts = ds.get_alerts()
    assert len(all_alerts) > 0

    critical_alerts = ds.get_alerts(severity=AlertSeverity.CRITICAL)
    assert len(critical_alerts) > 0, "应有CRITICAL级别告警"

    first_alert = all_alerts[0]
    assert first_alert.resolved is False

    ds.resolve_alert(first_alert.alert_id)
    assert first_alert.resolved is True

    unresolved = ds.get_alerts(unresolved_only=True)
    assert all(a.resolved is False for a in unresolved)

    print(f"  ✓ 总告警: {len(all_alerts)}, CRITICAL: {len(critical_alerts)}")
    print(f"  ✓ 告警解决后过滤正确")
    print()


def run_all():
    test_no_workers_at_all()
    test_offline_workers_with_skill()
    test_online_workers_full_load_with_skill()
    test_no_skill_match_at_all()
    test_retry_single_order_cleans_queue()
    test_retry_single_order_manual()
    test_complete_order_auto_retry()
    test_set_worker_online_auto_retry()
    test_alert_callback()
    test_resolve_alerts()

    print("=" * 60)
    print("全部 10 个测试通过 ✓")
    print("=" * 60)


if __name__ == "__main__":
    run_all()
