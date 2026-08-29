from __future__ import annotations

from functools import lru_cache
from typing import Any

BOARD_SIZE = 15
EMPTY = 0
BLACK = 1
WHITE = 2
DIRECTIONS = ((1, 0), (0, 1), (1, 1), (1, -1))
MAX_FORBIDDEN_DEPTH = 2
PLAYER_LABELS = {BLACK: "黑方", WHITE: "白方"}
FORBIDDEN_LABELS = {
    "OVERLINE": "长连禁手",
    "DOUBLE_FOUR": "四四禁手",
    "DOUBLE_THREE": "三三禁手",
}


def board_index(row: int, col: int) -> int:
    return row * BOARD_SIZE + col


def in_bounds(row: int, col: int) -> bool:
    return 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE


def value_at(board: list[int], row: int, col: int) -> int:
    if not in_bounds(row, col):
        return -1
    return board[board_index(row, col)]


def line_coordinates(row: int, col: int, dr: int, dc: int) -> list[tuple[int, int]]:
    start_row, start_col = row, col
    while in_bounds(start_row - dr, start_col - dc):
        start_row -= dr
        start_col -= dc
    result = []
    while in_bounds(start_row, start_col):
        result.append((start_row, start_col))
        start_row += dr
        start_col += dc
    return result


def contiguous_length(board: list[int], row: int, col: int, color: int, dr: int, dc: int) -> int:
    total = 1
    for sign in (-1, 1):
        step = 1
        while value_at(board, row + sign * dr * step, col + sign * dc * step) == color:
            total += 1
            step += 1
    return total


def line_lengths(board: list[int], row: int, col: int, color: int) -> list[int]:
    return [contiguous_length(board, row, col, color, dr, dc) for dr, dc in DIRECTIONS]


def collect_fours(board: list[int], row: int, col: int) -> set[frozenset[tuple[int, int]]]:
    fours: set[frozenset[tuple[int, int]]] = set()
    for dr, dc in DIRECTIONS:
        line = line_coordinates(row, col, dr, dc)
        anchor = line.index((row, col))
        for start in range(max(0, anchor - 4), min(anchor, len(line) - 5) + 1):
            window = line[start : start + 5]
            values = [value_at(board, item_row, item_col) for item_row, item_col in window]
            if values.count(BLACK) != 4 or values.count(EMPTY) != 1:
                continue
            stones = frozenset(window[index] for index, value in enumerate(values) if value == BLACK)
            if (row, col) not in stones:
                continue
            empty_index = values.index(EMPTY)
            win_row, win_col = window[empty_index]
            trial = board.copy()
            trial[board_index(win_row, win_col)] = BLACK
            if contiguous_length(trial, win_row, win_col, BLACK, dr, dc) == 5:
                fours.add(stones)
    return fours


def straight_fours_containing(
    board: list[int],
    anchor: tuple[int, int],
    added: tuple[int, int],
    dr: int,
    dc: int,
) -> set[frozenset[tuple[int, int]]]:
    line = line_coordinates(anchor[0], anchor[1], dr, dc)
    result: set[frozenset[tuple[int, int]]] = set()
    for start in range(len(line) - 3):
        stones = line[start : start + 4]
        if anchor not in stones or added not in stones:
            continue
        if any(value_at(board, row, col) != BLACK for row, col in stones):
            continue
        before = (stones[0][0] - dr, stones[0][1] - dc)
        after = (stones[-1][0] + dr, stones[-1][1] + dc)
        if value_at(board, before[0], before[1]) != EMPTY or value_at(board, after[0], after[1]) != EMPTY:
            continue
        before_trial = board.copy()
        before_trial[board_index(before[0], before[1])] = BLACK
        after_trial = board.copy()
        after_trial[board_index(after[0], after[1])] = BLACK
        if (
            contiguous_length(before_trial, before[0], before[1], BLACK, dr, dc) == 5
            and contiguous_length(after_trial, after[0], after[1], BLACK, dr, dc) == 5
        ):
            result.add(frozenset(stones))
    return result


@lru_cache(maxsize=32768)
def cached_forbidden(board_key: tuple[int, ...], row: int, col: int, depth: int) -> str | None:
    return forbidden_reason(list(board_key), row, col, depth)


def collect_open_threes(
    board: list[int], row: int, col: int, depth: int
) -> set[frozenset[tuple[int, int]]]:
    threes: set[frozenset[tuple[int, int]]] = set()
    anchor = (row, col)
    for dr, dc in DIRECTIONS:
        line = line_coordinates(row, col, dr, dc)
        anchor_index = line.index(anchor)
        for candidate_index in range(max(0, anchor_index - 4), min(len(line), anchor_index + 5)):
            candidate = line[candidate_index]
            if value_at(board, candidate[0], candidate[1]) != EMPTY:
                continue
            trial = board.copy()
            trial[board_index(candidate[0], candidate[1])] = BLACK
            if cached_forbidden(tuple(trial), candidate[0], candidate[1], depth + 1):
                continue
            for straight_four in straight_fours_containing(trial, anchor, candidate, dr, dc):
                triple = frozenset(point for point in straight_four if point != candidate)
                if len(triple) == 3 and anchor in triple:
                    threes.add(triple)
    return threes


def forbidden_reason(board: list[int], row: int, col: int, depth: int = 0) -> str | None:
    lengths = line_lengths(board, row, col, BLACK)
    if 5 in lengths:
        return None
    if any(length >= 6 for length in lengths):
        return "OVERLINE"
    if len(collect_fours(board, row, col)) >= 2:
        return "DOUBLE_FOUR"
    # RIF double-three judgment is recursive: a three only counts when it can
    # legally become a straight four. The guard protects hostile positions from
    # unbounded analysis while retaining the recursive rule in practical play.
    if depth < MAX_FORBIDDEN_DEPTH and len(collect_open_threes(board, row, col, depth)) >= 2:
        return "DOUBLE_THREE"
    return None


def analyze_move(board: list[int], row: int, col: int, color: int, mode: str) -> dict[str, Any]:
    if not in_bounds(row, col):
        return {"legal": False, "code": "OUT_OF_BOUNDS", "message": "落点超出棋盘。"}
    if value_at(board, row, col) != EMPTY:
        return {"legal": False, "code": "OCCUPIED", "message": "这里已经有棋子。"}
    if mode == "professional" and color == BLACK and not any(board) and (row, col) != (7, 7):
        return {"legal": False, "code": "CENTER_REQUIRED", "message": "专业模式黑方首手必须落在天元。"}

    trial = board.copy()
    trial[board_index(row, col)] = color
    lengths = line_lengths(trial, row, col, color)
    if mode == "professional" and color == BLACK:
        forbidden = forbidden_reason(trial, row, col)
        if forbidden:
            return {
                "legal": False,
                "code": forbidden,
                "message": f"这是{FORBIDDEN_LABELS[forbidden]}，黑方不能落在这里。",
            }
        wins = 5 in lengths
    else:
        wins = any(length >= 5 for length in lengths)

    return {"legal": True, "code": "LEGAL", "message": "再次点击确认落子。", "wins": wins}


def create_game(mode: str) -> dict[str, Any]:
    if mode not in {"normal", "professional"}:
        raise ValueError("未知规则模式")
    return {
        "mode": mode,
        "boardSize": BOARD_SIZE,
        "board": [EMPTY] * (BOARD_SIZE * BOARD_SIZE),
        "currentColor": BLACK,
        "turn": 1,
        "status": "playing",
        "winnerColor": None,
        "resultReason": None,
        "lastMove": None,
        "moveHistory": [],
    }


def place_stone(game: dict[str, Any], color: int, row: int, col: int) -> tuple[bool, str]:
    if game["status"] != "playing":
        return False, "本局已经结束。"
    if color != game["currentColor"]:
        return False, "还没有轮到你。"
    analysis = analyze_move(game["board"], row, col, color, game["mode"])
    if not analysis["legal"]:
        return False, analysis["message"]

    game["board"][board_index(row, col)] = color
    game["lastMove"] = [row, col]
    game["moveHistory"].append({"turn": game["turn"], "color": color, "row": row, "col": col})
    if analysis.get("wins"):
        game["status"] = "finished"
        game["winnerColor"] = color
        game["resultReason"] = "FIVE_IN_A_ROW"
        return True, f"{PLAYER_LABELS[color]}连成五子，获得胜利。"
    if all(value != EMPTY for value in game["board"]):
        game["status"] = "finished"
        game["resultReason"] = "BOARD_FULL"
        return True, "棋盘已满，本局和棋。"

    game["currentColor"] = WHITE if color == BLACK else BLACK
    game["turn"] += 1
    return True, "落子成功"


def resign(game: dict[str, Any], color: int) -> tuple[bool, str]:
    if game["status"] != "playing":
        return False, "本局已经结束。"
    game["status"] = "finished"
    game["winnerColor"] = WHITE if color == BLACK else BLACK
    game["resultReason"] = "RESIGN"
    return True, f"{PLAYER_LABELS[color]}已认输。"


def public_game(game: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": game["mode"],
        "boardSize": game["boardSize"],
        "board": list(game["board"]),
        "currentColor": game["currentColor"],
        "turn": game["turn"],
        "status": game["status"],
        "winnerColor": game["winnerColor"],
        "resultReason": game["resultReason"],
        "lastMove": game["lastMove"],
        "moveHistory": list(game["moveHistory"]),
    }
