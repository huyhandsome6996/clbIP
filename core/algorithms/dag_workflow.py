"""
DSA 4: Directed Acyclic Graph (DAG) & Topological Sort — Kahn's Algorithm
=========================================================================
Nghiệp vụ: Sắp xếp tiến trình chuẩn bị sự kiện (Checklist Tasks).
Task B chỉ bắt đầu khi Task A hoàn thành. Phát hiện phụ thuộc vòng tròn
(Deadlock Cycle Detection) bằng thuật toán Kahn (BFS).

Độ phức tạp: O(V + E) với V số task, E số cạnh phụ thuộc.
"""
from collections import deque
from typing import DefaultDict, Dict, Hashable, List, Optional, Sequence, Set, Tuple


class TaskDependencyEngine:
    """Engine phân tích đồ thị phụ thuộc task sự kiện."""

    @staticmethod
    def resolve_task_order(
        tasks: Sequence[Hashable],
        dependencies: Sequence[Tuple[Hashable, Hashable]],
    ) -> Tuple[bool, List[Hashable]]:
        """
        Sắp xếp topo theo thuật toán Kahn (BFS).

        Args:
            tasks: danh sách ID task (hashable — thường là int PK).
            dependencies: danh sách cặp (task_truoc, task_sau) — cạnh u → v.

        Returns:
            (is_valid_dag, execution_order)
            - is_valid_dag=True:  execution_order là thứ tự thực thi hợp lệ.
            - is_valid_dag=False: phát hiện chu trình, execution_order rỗng.
        """
        in_degree: Dict[Hashable, int] = {task: 0 for task in tasks}
        adj_list: DefaultDict[Hashable, List[Hashable]] = DefaultDict(list)
        task_set: Set[Hashable] = set(tasks)

        for u, v in dependencies:
            if u not in task_set or v not in task_set:
                # Cạnh trỏ tới task không tồn tại → coi là dữ liệu lỗi, bỏ qua
                continue
            adj_list[u].append(v)
            in_degree[v] += 1

        queue: deque = deque([t for t, deg in in_degree.items() if deg == 0])
        order: List[Hashable] = []

        while queue:
            curr: Hashable = queue.popleft()
            order.append(curr)
            for neighbor in adj_list[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) == len(tasks):
            return True, order  # Không có chu trình — thứ tự thực hiện hợp lệ
        return False, []        # Phát hiện chu trình (Deadlock phụ thuộc)

    @staticmethod
    def find_cycle(
        tasks: Sequence[Hashable],
        dependencies: Sequence[Tuple[Hashable, Hashable]],
    ) -> Optional[List[Hashable]]:
        """
        Tìm và trả về MỘT chu trình cụ thể (nếu có) để hiển thị cảnh báo deadlock.
        Thuật toán: DFS với màu trắng/xám/đen, truy vết đường đi.

        Returns:
            Danh sách task tạo thành chu trình, hoặc None nếu DAG hợp lệ.
        """
        task_set: Set[Hashable] = set(tasks)
        adj: DefaultDict[Hashable, List[Hashable]] = DefaultDict(list)
        for u, v in dependencies:
            if u in task_set and v in task_set:
                adj[u].append(v)

        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[Hashable, int] = {t: WHITE for t in task_set}
        parent: Dict[Hashable, Optional[Hashable]] = {}

        cycle_start: Optional[Hashable] = None
        cycle_end: Optional[Hashable] = None

        def dfs(node: Hashable) -> bool:
            """Trả True nếu tìm thấy chu trình."""
            nonlocal cycle_start, cycle_end
            color[node] = GRAY
            for nxt in adj[node]:
                if color[nxt] == GRAY:
                    cycle_start, cycle_end = nxt, node
                    return True
                if color[nxt] == WHITE:
                    parent[nxt] = node
                    if dfs(nxt):
                        return True
            color[node] = BLACK
            return False

        for task in task_set:
            if color[task] == WHITE:
                parent[task] = None
                if dfs(task):
                    # Truy vết ngược từ cycle_end về cycle_start
                    cycle: List[Hashable] = [cycle_start]
                    node: Optional[Hashable] = cycle_end
                    while node is not None and node != cycle_start:
                        cycle.append(node)
                        node = parent.get(node)
                    cycle.append(cycle_start)  # đóng vòng
                    cycle.reverse()
                    return cycle
        return None

    @staticmethod
    def would_create_cycle(
        tasks: Sequence[Hashable],
        dependencies: Sequence[Tuple[Hashable, Hashable]],
        from_task: Hashable,
        to_task: Hashable,
    ) -> bool:
        """
        Kiểm tra thêm cạnh (from_task → to_task) có tạo chu trình không
        (dùng trước khi lưu task mới — chống deadlock proactive).
        """
        return TaskDependencyEngine.resolve_task_order(
            list(tasks) + [], list(dependencies) + [(from_task, to_task)]
        )[0] is False

    @staticmethod
    def find_executable_now(
        tasks: Sequence[Hashable],
        dependencies: Sequence[Tuple[Hashable, Hashable]],
        completed: Set[Hashable],
    ) -> List[Hashable]:
        """
        Trả về danh sách task có thể bắt đầu NGAY:
        chưa hoàn thành + mọi task tiền nhiệm đã hoàn thành.
        """
        pending: Set[Hashable] = set(tasks) - completed
        executable: List[Hashable] = []
        for t in pending:
            predecessors = [u for (u, v) in dependencies if v == t]
            if all(p in completed for p in predecessors):
                executable.append(t)
        return executable
