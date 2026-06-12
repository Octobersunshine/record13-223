from dispatch_service import (
    DispatchService,
    Worker,
    RepairOrder,
    Location,
    RepairType,
    AssignmentResult,
)


def build_sample_service() -> DispatchService:
    service = DispatchService(
        skill_weight=0.4,
        distance_weight=0.35,
        load_weight=0.2,
        rating_weight=0.05,
        max_distance=10.0,
    )

    service.add_worker(
        Worker(
            worker_id="W001",
            name="张师傅",
            skills=[RepairType.PLUMBING, RepairType.DOOR_LOCK],
            location=Location(2.0, 3.0),
            current_tasks=1,
            max_tasks=5,
            rating=4.8,
        )
    )
    service.add_worker(
        Worker(
            worker_id="W002",
            name="李师傅",
            skills=[RepairType.ELECTRICAL, RepairType.HVAC],
            location=Location(5.0, 5.0),
            current_tasks=0,
            max_tasks=5,
            rating=4.5,
        )
    )
    service.add_worker(
        Worker(
            worker_id="W003",
            name="王师傅",
            skills=[RepairType.CARPENTRY, RepairType.WINDOW, RepairType.DOOR_LOCK],
            location=Location(8.0, 2.0),
            current_tasks=3,
            max_tasks=5,
            rating=4.9,
        )
    )
    service.add_worker(
        Worker(
            worker_id="W004",
            name="赵师傅",
            skills=[RepairType.PLUMBING, RepairType.PAINTING, RepairType.WINDOW],
            location=Location(1.0, 8.0),
            current_tasks=0,
            max_tasks=5,
            rating=4.2,
        )
    )
    service.add_worker(
        Worker(
            worker_id="W005",
            name="钱师傅",
            skills=[RepairType.ELECTRICAL, RepairType.PLUMBING],
            location=Location(6.0, 1.0),
            current_tasks=0,
            max_tasks=5,
            rating=4.7,
            is_online=False,
        )
    )

    return service


def demo_basic_assignment():
    print("=" * 60)
    print("【示例1】基础派单：水管维修")
    print("=" * 60)
    service = build_sample_service()

    order = RepairOrder(
        order_id="O2025001",
        repair_type=RepairType.PLUMBING,
        description="厨房水龙头漏水严重",
        location=Location(3.0, 4.0),
        priority=2,
    )
    service.add_order(order)

    print(f"\n订单信息: {order.order_id} - {order.description}")
    print(f"报修类型: {order.repair_type.value}, 位置: ({order.location.x}, {order.location.y})")

    print("\n--- 维修工综合得分排名 ---")
    rankings = service.rank_all_candidates(order.order_id)
    for i, r in enumerate(rankings, 1):
        w = r.worker
        print(
            f"{i}. {w.name}({w.worker_id}) | 得分:{r.score:.4f} | "
            f"技能匹配:{'✓' if r.skill_match else '✗'} | "
            f"距离:{r.distance} | 任务负载:{w.current_tasks}/{w.max_tasks} | "
            f"在线:{'是' if w.is_online else '否'}"
        )
        print(f"   详情: {r.reason}")

    result = service.assign_order(order.order_id)
    print(f"\n>>> 最终派单结果:")
    if result.worker:
        print(
            f"分配给: {result.worker.name}({result.worker.worker_id}) | "
            f"综合得分: {result.score:.4f}"
        )
    else:
        print(f"派单失败: {result.reason}")
    print()


def demo_load_balancing():
    print("=" * 60)
    print("【示例2】负载均衡：同技能不同任务量")
    print("=" * 60)
    service = build_sample_service()

    order = RepairOrder(
        order_id="O2025002",
        repair_type=RepairType.DOOR_LOCK,
        description="住户家门锁损坏无法打开",
        location=Location(5.0, 5.0),
        priority=3,
    )
    service.add_order(order)

    print(f"\n订单: {order.order_id} - {order.description}")
    print(f"位置: ({order.location.x}, {order.location.y})")

    print("\n--- 候选排名 (门锁维修) ---")
    rankings = service.rank_all_candidates(order.order_id)
    for i, r in enumerate(rankings, 1):
        w = r.worker
        print(
            f"{i}. {w.name} | 得分:{r.score:.4f} | "
            f"技能:{'✓' if r.skill_match else '✗'} | "
            f"距离:{r.distance} | 当前任务:{w.current_tasks} | {r.reason}"
        )

    result = service.assign_order(order.order_id)
    print(f"\n>>> 分配给: {result.worker.name if result.worker else '无'}")
    print()


def demo_distance_priority():
    print("=" * 60)
    print("【示例3】距离优先：远距离维修工被过滤")
    print("=" * 60)
    service = build_sample_service()

    order = RepairOrder(
        order_id="O2025003",
        repair_type=RepairType.PAINTING,
        description="客厅墙面重新刷漆",
        location=Location(0.5, 0.5),
        priority=1,
    )
    service.add_order(order)

    print(f"\n订单: {order.order_id} - {order.description}")
    print(f"位置: ({order.location.x}, {order.location.y})")

    print("\n--- 所有维修工与报修点距离 ---")
    for w in service.workers:
        d = round(w.location.distance_to(order.location), 2)
        eligible = w.is_online and w.current_tasks < w.max_tasks and d <= service.max_distance
        print(
            f"  {w.name}: 距离={d}, 技能包含刷漆={RepairType.PAINTING in w.skills}, "
            f"可用={'是' if eligible else '否'}"
        )

    result = service.assign_order(order.order_id)
    print(f"\n>>> 分配给: {result.worker.name if result.worker else '无' }")
    if result.worker:
        print(f"    距离: {result.distance}, 得分: {result.score:.4f}")
    print()


def demo_no_eligible_workers():
    print("=" * 60)
    print("【示例4】无可用维修工：HVAC维修无对应技能人员")
    print("=" * 60)
    service = DispatchService()
    service.add_worker(
        Worker(
            worker_id="W001",
            name="张师傅",
            skills=[RepairType.PLUMBING],
            location=Location(0, 0),
        )
    )
    order = RepairOrder(
        order_id="O2025004",
        repair_type=RepairType.HVAC,
        description="中央空调故障",
        location=Location(1, 1),
    )
    service.add_order(order)

    result = service.assign_order(order.order_id)
    print(f"派单结果: {result.reason}")
    print()


def demo_workflow_lifecycle():
    print("=" * 60)
    print("【示例5】完整工单生命周期：派单→完成→评分")
    print("=" * 60)
    service = build_sample_service()

    order1 = RepairOrder(
        order_id="O2025101",
        repair_type=RepairType.ELECTRICAL,
        description="卧室插座短路",
        location=Location(4.5, 4.5),
    )
    order2 = RepairOrder(
        order_id="O2025102",
        repair_type=RepairType.ELECTRICAL,
        description="客厅灯具不亮",
        location=Location(5.5, 5.5),
    )
    service.add_order(order1)
    service.add_order(order2)

    print("\n[步骤1] 派发第一个电工工单")
    r1 = service.assign_order(order1.order_id)
    print(f"  分配给: {r1.worker.name} | 派发前任务数: {r1.worker.current_tasks - 1} | 派发后: {r1.worker.current_tasks}")

    print("\n[步骤2] 派发第二个电工工单")
    r2 = service.assign_order(order2.order_id)
    print(f"  分配给: {r2.worker.name} | 当前任务数: {r2.worker.current_tasks}")

    print("\n[步骤3] 完成第一个工单，用户评分 5.0")
    success = service.complete_order(order1.order_id, rating=5.0)
    worker = next(w for w in service.workers if w.worker_id == order1.assigned_worker)
    print(f"  完成成功: {success} | {worker.name} 当前任务数: {worker.current_tasks}, 最新评分: {worker.rating}")

    print("\n[步骤4] 查看该维修工历史工单")
    history = service.get_worker_orders(worker.worker_id)
    for o in history:
        print(f"  - {o.order_id}: {o.description} [状态: {o.status}]")
    print()


def run_tests():
    print("=" * 60)
    print("【单元测试】")
    print("=" * 60)
    passed = 0
    total = 0

    def assert_equal(actual, expected, msg):
        nonlocal passed, total
        total += 1
        if actual == expected:
            passed += 1
            print(f"  ✓ {msg}")
        else:
            print(f"  ✗ {msg} (期望 {expected}, 实际 {actual})")

    def assert_true(cond, msg):
        nonlocal passed, total
        total += 1
        if cond:
            passed += 1
            print(f"  ✓ {msg}")
        else:
            print(f"  ✗ {msg}")

    print("\n1. Location 距离计算")
    p1 = Location(0, 0)
    p2 = Location(3, 4)
    assert_equal(p1.distance_to(p2), 5.0, "两点距离应为5")

    print("\n2. 技能匹配测试")
    service = build_sample_service()
    w_plumbing = [w for w in service.workers if RepairType.PLUMBING in w.skills]
    assert_true(len(w_plumbing) >= 3, "至少3名管道维修工")

    print("\n3. 派单后任务数+1")
    order = RepairOrder(
        order_id="T001",
        repair_type=RepairType.WINDOW,
        description="玻璃碎裂",
        location=Location(8.5, 2.5),
    )
    service.add_order(order)
    result = service.assign_order(order.order_id)
    target = result.worker
    assert_equal(target.current_tasks, 4, f"{target.name}任务数应为4")

    print("\n4. 重复派单应被拒绝")
    dup = service.assign_order(order.order_id)
    assert_true(dup.worker is None, "已分配订单不可再次分派")

    print("\n5. 完成订单后任务数-1，评分更新")
    before = target.current_tasks
    ok = service.complete_order(order.order_id, rating=4.5)
    assert_true(ok, "完成订单应返回True")
    assert_equal(target.current_tasks, before - 1, "完成后任务数应-1")
    assert_true(4.0 <= target.rating <= 5.0, f"评分应在合理区间({target.rating})")

    print("\n6. 离线维修工不参与派单")
    order2 = RepairOrder(
        order_id="T002",
        repair_type=RepairType.ELECTRICAL,
        description="测试离线",
        location=Location(6.0, 1.0),
    )
    service.add_order(order2)
    ranks = service.rank_all_candidates(order2.order_id)
    offline_ids = [r.worker.worker_id for r in ranks if not r.worker.is_online]
    assert_true("W005" not in offline_ids, "离线维修工不应出现在候选列表")

    print("\n7. 不存在的订单")
    result_bad = service.assign_order("NOT_EXIST")
    assert_true("不存在" in result_bad.reason, "应提示订单不存在")

    print(f"\n测试结果: {passed}/{total} 通过")
    assert_true(passed == total, "全部测试通过")
    print()


if __name__ == "__main__":
    demo_basic_assignment()
    demo_load_balancing()
    demo_distance_priority()
    demo_no_eligible_workers()
    demo_workflow_lifecycle()
    run_tests()
