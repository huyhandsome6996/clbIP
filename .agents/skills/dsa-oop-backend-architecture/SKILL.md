---
name: dsa-oop-backend-architecture
description: Hướng dẫn chuyên sâu và bắt buộc để áp dụng triệt để Cấu trúc dữ liệu & Giải thuật (DSA) và Lập trình Hướng đối tượng (OOP) vào hệ thống Backend Django REST Framework. Bắt buộc tuân thủ SOLID, Clean Architecture, và các thuật toán tối ưu hóa (Haversine Geofencing, PriorityQueue Ranking, Trie Search, DAG Topological Sort).
---

# 🧠 SKILL: DSA & OOP Backend Architecture Guide (Django / Python)

Skill này cung cấp các nguyên tắc kiến trúc và tiêu chuẩn kỹ thuật bắt buộc khi xây dựng hệ thống Backend API bằng Python/Django, nhằm biến hệ thống thành một sản phẩm mẫu mực về **Lập trình Hướng Đối Tượng (OOP)** và **Cấu trúc Dữ liệu & Giải thuật (DSA)** thực chiến.

---

## PHẦN 1: CÁC NGUYÊN TẮC VÀ PATTERNS OOP BẮT BUỘC

### 1. Nguyên tắc SOLID trong Django
1. **Single Responsibility Principle (SRP):**
   - Django Models: CHỈ định nghĩa schema, quan hệ và validation thuộc tính cơ bản. KHÔNG nhồi nhét nghiệp vụ tính toán phức tạp.
   - Django Serializers: CHỈ làm nhiệm vụ chuyển đổi dữ liệu (parsing, validating formats, transforming JSON). KHÔNG viết logic lưu database phức tạp.
   - Django Views / ViewSets: CHỈ làm Controller tiếp nhận HTTP Request, gọi Service Layer tương ứng và trả về HTTP Response.
   - **Service Layer (`services/`):** Nơi DUY NHẤT chứa toàn bộ business logic và các thuật toán.

2. **Open/Closed Principle (OCP):**
   - Mở rộng qua kế thừa hoặc composition mà không sửa đổi code lõi. Ví dụ: Các chính sách tính điểm thưởng XP (`RewardStrategy`) hay các loại giao dịch quỹ (`TransactionTypeHandler`).

3. **Liskov Substitution Principle (LSP):**
   - Các class kế thừa từ Base Class hoặc Interface phải có khả năng thay thế nhau mà không làm hỏng tính đúng đắn của chương trình.

4. **Interface Segregation Principle (ISP):**
   - Tách nhỏ các Python `Protocol` hoặc `ABC` (Abstract Base Class). Không ép một class phải implement các method nó không cần.

5. **Dependency Inversion Principle (DIP):**
   - Module cấp cao (Services) không phụ thuộc trực tiếp vào module cấp thấp (External APIs, third-party libs) mà phụ thuộc vào trừu tượng (Interfaces / Abstractions).

---

### 2. Các Mẫu Thiết Kế (Design Patterns) Trọng Yếu

#### A. Repository Pattern
Tách biệt tầng truy vấn CSDL khỏi tầng nghiệp vụ:
```python
# repositories/member_repository.py
from abc import ABC, abstractmethod
from typing import List, Optional
from core.domain.entities import MemberEntity

class IMemberRepository(ABC):
    @abstractmethod
    def get_by_id(self, member_id: int) -> Optional[MemberEntity]:
        pass

    @abstractmethod
    def get_active_members(self) -> List[MemberEntity]:
        pass

    @abstractmethod
    def save(self, member: MemberEntity) -> MemberEntity:
        pass
```

#### B. Strategy Pattern cho Hệ Thống Tính Điểm & Xếp Hạng (Gamification)
Tách rời các thuật toán tính điểm thưởng:
```python
# services/strategies/reward_strategy.py
from abc import ABC, abstractmethod

class IRewardStrategy(ABC):
    @abstractmethod
    def calculate_xp(self, context: dict) -> int:
        pass

class EarlyAttendanceStrategy(IRewardStrategy):
    """Điểm danh sớm trước 15 phút: +50 XP + 20 XP bonus"""
    def calculate_xp(self, context: dict) -> int:
        minutes_early = context.get('minutes_early', 0)
        base = 50
        bonus = 20 if minutes_early >= 15 else (10 if minutes_early > 0 else 0)
        return base + bonus

class EventContributionStrategy(IRewardStrategy):
    """Tham gia ban tổ chức sự kiện: +100 XP"""
    def calculate_xp(self, context: dict) -> int:
        role = context.get('role', 'PARTICIPANT')
        return 150 if role == 'ORGANIZER' else 50
```

#### C. Factory Pattern cho Khởi Tạo Giao Dịch & Sự Kiện
```python
# services/factories/transaction_factory.py
class TransactionFactory:
    @staticmethod
    def create_transaction(trans_type: str, amount: int, actor: str, note: str):
        if trans_type == 'THU':
            return IncomeTransaction(amount=amount, actor=actor, note=note)
        elif trans_type == 'CHI':
            return ExpenseTransaction(amount=amount, actor=actor, note=note)
        raise ValueError(f"Loại giao dịch không hợp lệ: {trans_type}")
```

#### D. Observer / Event-Driven Pattern (Domain Events)
Khi một sự kiện xảy ra (ví dụ: Thành viên điểm danh thành công), phát sinh Domain Event để:
- Tăng chuỗi Streak 🔥
- Cộng XP
- Kiểm tra điều kiện mở khóa Huy hiệu (Badge Unlock)
- Gửi thông báo WebSocket / Email

---

## PHẦN 2: CẤU TRÚC DỮ LIỆU & GIẢI THUẬT (DSA) ỨNG DỤNG THỰC TẾ

### 1. DSA 1: Haversine & Spatial Bounding Box Geofencing
**Nghiệp vụ:** Điểm danh GPS cho thành viên với độ trễ tối thiểu và độ chính xác cao.
- **Vấn đề:** Tính toán khoảng cách tọa độ Trái Đất (mặt cầu) và tránh tính toán $O(N)$ lãng phí trên toàn bộ dữ liệu.
- **Giải pháp:**
  1. *Bounding Box Pre-filter ($O(1)$):* Tính toán ô bao chữ nhật $(\text{min\_lat}, \text{max\_lat}, \text{min\_lon}, \text{max\_lon})$ từ tâm bán kính $R$.
  2. *Công thức Haversine chuẩn ($O(1)$):*
  $$d = 2r \arcsin\left(\sqrt{\sin^2\left(\frac{\Delta \phi}{2}\right) + \cos(\phi_1)\cos(\phi_2)\sin^2\left(\frac{\Delta \lambda}{2}\right)}\right)$$

```python
# algorithms/geo_haversine.py
import math

class GeoSpatialService:
    EARTH_RADIUS_METERS = 6371000  # Bán kính Trái Đất (mét)

    @classmethod
    def haversine_distance(cls, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Tính khoảng cách chính xác theo mét giữa 2 điểm GPS"""
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (math.sin(delta_phi / 2) ** 2 +
             math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return cls.EARTH_RADIUS_METERS * c

    @classmethod
    def is_within_radius(cls, center_lat: float, center_lon: float,
                          target_lat: float, target_lon: float,
                          radius_meters: float) -> tuple[bool, float]:
        distance = cls.haversine_distance(center_lat, center_lon, target_lat, target_lon)
        return distance <= radius_meters, round(distance, 2)
```

---

### 2. DSA 2: Priority Queue / Max-Heap Leaderboard ($O(\log K)$)
**Nghiệp vụ:** Bảng xếp hạng Top $K$ thành viên xuất sắc nhất và tra cứu thứ hạng tức thì.
- **Cấu trúc:** Sử dụng `heapq` (Min-Heap kích thước $K$ để tìm Top $K$ lớn nhất trong $O(N \log K)$) kết hợp Hash Map (`dict`) tra cứu thứ tự người dùng trong $O(1)$.

```python
# algorithms/leaderboard_heap.py
import heapq
from dataclasses import dataclass, field
from typing import List, Dict

@dataclass(order=True)
class LeaderboardEntry:
    xp: int
    member_id: int = field(compare=False)
    name: str = field(compare=False)
    avatar: str = field(compare=False)

class LeaderboardEngine:
    def __init__(self, top_k: int = 10):
        self.top_k = top_k

    def compute_top_k(self, members: List[dict]) -> List[dict]:
        """Sử dụng Min-Heap kích thước K để trích xuất Top K với chi phí O(N log K)"""
        # heapq trong python là min-heap
        heap = []
        for m in members:
            entry = (m['xp'], m['id'], m['name'], m['avatar'])
            if len(heap) < self.top_k:
                heapq.heappush(heap, entry)
            else:
                if entry[0] > heap[0][0]:
                    heapq.heappushpop(heap, entry)

        # Sắp xếp lại Top K giảm dần
        top_sorted = sorted(heap, key=lambda x: x[0], reverse=True)
        return [
            {"rank": idx + 1, "id": item[1], "name": item[2], "xp": item[0], "avatar": item[3]}
            for idx, item in enumerate(top_sorted)
        ]
```

---

### 3. DSA 3: Trie & Inverted Index Cho Tìm Kiếm Nhanh ($O(L)$)
**Nghiệp vụ:** Tìm kiếm nhanh thành viên theo MSSV / Tên không dấu, gợi ý tức thời (autocomplete).
- **Cấu trúc:** Cây tiền tố (Trie) cho chuỗi ký tự độ dài $L$. Thời gian tìm kiếm $O(L)$, độc lập với số lượng thành viên $N$.

```python
# algorithms/trie_search.py
class TrieNode:
    def __init__(self):
        self.children = {}
        self.is_end_of_word = False
        self.data_ids = set()

class PrefixSearchTrie:
    def __init__(self):
        self.root = TrieNode()

    def insert(self, word: str, data_id: int):
        node = self.root
        word = word.lower().strip()
        for char in word:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
            node.data_ids.add(data_id)
        node.is_end_of_word = True

    def search_prefix(self, prefix: str) -> set:
        node = self.root
        prefix = prefix.lower().strip()
        for char in prefix:
            if char not in node.children:
                return set()
            node = node.children[char]
        return node.data_ids
```

---

### 4. DSA 4: Directed Acyclic Graph (DAG) & Topological Sort Cho Checklist Sự Kiện
**Nghiệp vụ:** Quản lý quy trình chuẩn bị sự kiện phức tạp (Task B chỉ bắt đầu khi Task A đã hoàn thành). Phát hiện lỗi phụ thuộc vòng tròn (Circular Dependency) và tìm thứ tự thực thi hợp lệ.
- **Thuật toán:** Kahn's Algorithm (BFS) hoặc DFS Topological Sort.

```python
# algorithms/dag_workflow.py
from collections import deque, defaultdict
from typing import List, Dict

class TaskDependencyEngine:
    @staticmethod
    def resolve_task_order(tasks: List[int], dependencies: List[tuple[int, int]]) -> tuple[bool, List[int]]:
        """
        dependencies: danh sách (task_truoc, task_sau)
        Trả về (is_valid_dag, execution_order)
        """
        in_degree = {task: 0 for task in tasks}
        adj_list = defaultdict(list)

        for u, v in dependencies:
            adj_list[u].append(v)
            in_degree[v] += 1

        queue = deque([task for task, deg in in_degree.items() if deg == 0])
        order = []

        while queue:
            curr = queue.popleft()
            order.append(curr)
            for neighbor in adj_list[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) == len(tasks):
            return True, order  # Không có chu trình, thứ tự thực hiện hợp lệ
        return False, []  # Phát hiện chu trình (Deadlock phụ thuộc)
```

---

### 5. DSA 5: Bất Biến Tài Chính & Kiểm Soát Quỹ (Invariants & Concurrency)
**Nghiệp vụ:** Quỹ CLB phải bảo đảm tính toàn vẹn tuyệt đối.
- **Quy tắc:**
  * Mọi biến động quỹ phải nằm trong Database Transaction với pessimistic lock (`select_for_update()`).
  * Invariant: $\text{Số dư hiện tại} = \sum \text{Khoản thu} - \sum \text{Khoản chi}$.
  * Trạng thái khóa sổ (`is_locked`) ngăn chặn mọi sửa đổi lịch sử.

---

## PHẦN 3: CHECKLIST KIỂM ĐỊNH CHO CODING AGENT

Khi review code do Agent viết, bắt buộc đạt các tiêu chí sau:
- [ ] KHÔNG viết logic tính toán nặng hoặc truy vấn ORM trong `views.py` hay `serializers.py`. Phải chuyển vào `services/`.
- [ ] Có thư mục `core/algorithms/` chứa các module giải thuật (Haversine, LeaderboardHeap, TrieSearch, TaskDAG).
- [ ] Mỗi thuật toán DSA đều có ít nhất 3 Unit Tests kiểm tra trường hợp bình thường, trường hợp biên (edge cases) và độ phức tạp.
- [ ] Các class đều có Type Annotations (`typing`) đầy đủ và docstrings giải thích rõ ràng.
- [ ] Tối ưu truy vấn ORM với `select_related` và `prefetch_related`, nghiêm cấm phát sinh N+1 query.
