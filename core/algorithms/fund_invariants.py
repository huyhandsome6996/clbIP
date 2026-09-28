"""
DSA 5: Bất Biến Tài Chính & Kiểm Soát Quỹ (Fund Invariants)
===========================================================
Nghiệp vụ: Quỹ CLB phải bảo đảm tính toàn vẹn tuyệt đối.

Quy tắc bất biến (Invariants):
    I1: Số dư hiện tại = Σ Khoản thu − Σ Khoản chi
    I2: so_du_sau của giao dịch liên tiếp = so_du_sau trước + (THU: +x, CHI: −x)
    I3: Số dư KHÔNG BAO GIỜ âm
    I4: Giao dịch thuộc kỳ khóa sổ (is_locked=True) là bất biến
"""
from typing import Iterable, List, Sequence


class FundInvariantsEngine:
    """Engine kiểm chứng tính toàn vẹn số liệu quỹ."""

    @staticmethod
    def verify_balance_invariant(transactions: Sequence[dict]) -> bool:
        """
        Kiểm chứng I1: so_du_sau cuối cùng phải bằng Σ(THU) − Σ(CHI).

        Args:
            transactions: danh sách dict có ít nhất
                {"loai_gd": "THU"|"CHI", "so_tien": int, "so_du_sau": int}
                sắp xếp theo thời gian tăng dần.

        Returns:
            True nếu bất biến được bảo toàn, False nếu dữ liệu bị phá vỡ.
        """
        if not transactions:
            return True
        expected: int = 0
        for tx in transactions:
            amount: int = int(tx["so_tien"])
            expected += amount if tx["loai_gd"] == "THU" else -amount
        final_balance: int = int(transactions[-1]["so_du_sau"])
        return final_balance == expected

    @staticmethod
    def verify_balance_chain(transactions: Sequence[dict], opening_balance: int = 0) -> bool:
        """
        Kiểm chứng I2: chuỗi so_du_sau liên tục giữa các giao dịch.

        so_du_sau[i] = so_du_sau[i-1] + (THU: +so_tien | CHI: −so_tien)
        """
        current: int = opening_balance
        for tx in transactions:
            amount: int = int(tx["so_tien"])
            delta: int = amount if tx["loai_gd"] == "THU" else -amount
            current += delta
            if int(tx["so_du_sau"]) != current:
                return False
        return True

    @staticmethod
    def check_non_negative(balance: int) -> bool:
        """Kiểm chứng I3: số dư không được âm."""
        return balance >= 0

    @staticmethod
    def compute_totals(transactions: Iterable[dict]) -> dict:
        """
        Tính tổng thu / tổng chi / số dư từ danh sách giao dịch.

        Returns:
            {"total_income": int, "total_expense": int, "balance": int}
        """
        total_income: int = 0
        total_expense: int = 0
        for tx in transactions:
            amount: int = int(tx["so_tien"])
            if tx["loai_gd"] == "THU":
                total_income += amount
            else:
                total_expense += amount
        return {
            "total_income": total_income,
            "total_expense": total_expense,
            "balance": total_income - total_expense,
        }

    @staticmethod
    def validate_new_transaction(current_balance: int, loai_gd: str, so_tien: int) -> None:
        """
        Kiểm chứng trước khi ghi giao dịch mới — raise nếu vi phạm bất biến I3.

        Args:
            current_balance: số dư hiện tại (đã khóa bi).
            loai_gd: 'THU' hoặc 'CHI'.
            so_tien: số tiền (phải > 0).

        Raises:
            ValueError: nếu so_tien <= 0 hoặc loai_gd không hợp lệ.
            AssertionError: nếu khoản chi làm số dư âm.
        """
        if so_tien <= 0:
            raise ValueError("Số tiền giao dịch phải lớn hơn 0.")
        if loai_gd not in ("THU", "CHI"):
            raise ValueError(f"Loại giao dịch không hợp lệ: {loai_gd}")
        if loai_gd == "CHI":
            assert (
                current_balance - so_tien >= 0
            ), "Khoản chi này sẽ làm số dư quỹ âm — vi phạm bất biến I3!"
